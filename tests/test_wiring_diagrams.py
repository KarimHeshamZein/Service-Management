from __future__ import annotations

import io
import zipfile

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.config import settings
from app.models import User, UserDepartmentPermission, WiringDiagram, WiringDiagramCategory
from tests.conftest import ADMIN, CUSTOMER_A, LEADER_A, csrf_of, login, logout, make_image


def _pdf() -> bytes:
    output = io.BytesIO()
    page = canvas.Canvas(output)
    page.drawString(72, 760, "Camera wiring")
    page.showPage(); page.save()
    return output.getvalue()


def _category(client, name: str, parent_id: int | None = None):
    token = csrf_of(client, "/pricing/wiring-diagrams/categories")
    data = {"csrf_token": token, "name": name}
    if parent_id is not None:
        data["parent_id"] = str(parent_id)
    return client.post("/pricing/wiring-diagrams/categories", data=data)


def _diagram(client, category_id: int):
    token = csrf_of(client, "/pricing/wiring-diagrams/new")
    return client.post(
        "/pricing/wiring-diagrams",
        data={"csrf_token": token, "name": "Hikvision Gate Wiring", "project_name": "NEOM Gate 4", "category_id": str(category_id), "notes": "Use protected conduit."},
        files=[("files", ("drawing.pdf", _pdf(), "application/pdf")), ("files", ("panel.jpg", make_image(), "image/jpeg"))],
    )


def test_wiring_diagram_folder_create_preview_search_edit_and_zip(client, db):
    login(client, *ADMIN)
    assert _category(client, "Cameras").status_code == 303
    db.expire_all(); root = db.query(WiringDiagramCategory).filter_by(name="Cameras").one()
    assert _category(client, "Hikvision", root.id).status_code == 303
    db.expire_all(); sub = db.query(WiringDiagramCategory).filter_by(name="Hikvision").one()
    assert _diagram(client, sub.id).status_code == 303
    db.expire_all(); row = db.query(WiringDiagram).one()
    assert len(row.files) == 2

    home = client.get("/pricing/wiring-diagrams")
    assert "Cameras" in home.text and "Hikvision Gate Wiring" not in home.text
    root_page = client.get(f"/pricing/wiring-diagrams?category={root.id}")
    assert "Hikvision" in root_page.text and "Hikvision Gate Wiring" not in root_page.text
    sub_page = client.get(f"/pricing/wiring-diagrams?category={sub.id}")
    assert "Hikvision Gate Wiring" in sub_page.text
    search = client.get("/pricing/wiring-diagrams?q=NEOM")
    assert "Hikvision Gate Wiring" in search.text

    preview = client.get(f"/pricing/wiring-diagrams/{row.id}/preview")
    assert preview.status_code == 200
    assert len(PdfReader(io.BytesIO(preview.content)).pages) == 2
    package = client.get(f"/pricing/wiring-diagrams/{row.id}/download.zip")
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert sorted(archive.namelist()) == ["drawing.pdf", "panel.jpg"]

    first_file = row.files[0]
    old_key = first_file.storage_key
    token = csrf_of(client, f"/pricing/wiring-diagrams/{row.id}/edit")
    edited = client.post(
        f"/pricing/wiring-diagrams/{row.id}/edit",
        data={"csrf_token":token,"name":"Updated Wiring","project_name":"Qiddiya","category_id":str(root.id),"notes":"Updated","remove_file_ids":str(first_file.id)},
        files=[("files", ("replacement.png", make_image(fmt="PNG"), "image/png"))],
    )
    assert edited.status_code == 303
    db.expire_all(); row=db.get(WiringDiagram,row.id)
    assert row.name == "Updated Wiring" and row.category_id == root.id and len(row.files) == 2
    assert not (settings.upload_dir / old_key).exists()


def test_wiring_permissions_and_admin_delete(client, db):
    technical = db.query(User).filter_by(username=LEADER_A[0]).one()
    permission = db.get(UserDepartmentPermission, (technical.id, 1, "wiring.manage"))
    assert permission is not None
    permission.allowed = False
    db.commit()
    login(client, *LEADER_A)
    assert client.get("/pricing/wiring-diagrams").status_code == 200
    assert client.get("/pricing/wiring-diagrams/new").status_code == 403
    logout(client)
    override = db.get(UserDepartmentPermission, (technical.id, 1, "wiring.manage"))
    override.allowed = True
    db.commit()
    login(client, *LEADER_A)
    assert client.get("/pricing/wiring-diagrams/new").status_code == 200
    assert _diagram(client, 0).status_code == 303  # invalid category is rejected safely
    assert db.query(WiringDiagram).count() == 0
    logout(client)
    login(client, *CUSTOMER_A)
    assert client.get("/pricing/wiring-diagrams").status_code == 403


def test_only_admin_deletes_complete_diagram_and_files(client, db):
    login(client, *ADMIN)
    _category(client, "Gates")
    db.expire_all(); category=db.query(WiringDiagramCategory).one()
    _diagram(client,category.id)
    db.expire_all(); row=db.query(WiringDiagram).one(); keys=[entry.storage_key for entry in row.files]
    token=csrf_of(client,f"/pricing/wiring-diagrams/{row.id}")
    response=client.post(f"/pricing/wiring-diagrams/{row.id}/delete",data={"csrf_token":token})
    assert response.status_code == 303
    db.expire_all(); assert db.query(WiringDiagram).count() == 0
    assert all(not (settings.upload_dir / key).exists() for key in keys)
