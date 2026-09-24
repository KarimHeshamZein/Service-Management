"""Product Evaluations and Testing workflow regressions."""
from __future__ import annotations

import io

from pypdf import PdfReader

from app.models import (
    ProductEvaluationDecision,
    ProductEvaluationRequest,
    ProductEvaluationSession,
    ProductEvaluationSessionStatus,
    ProductEvaluationStatus,
    User,
    UserDepartmentPermission,
)
from tests.conftest import (
    ADMIN,
    CUSTOMER_A,
    LEADER_A,
    LEADER_B,
    csrf_of,
    login,
    logout,
    make_image,
)


def _pdf_text(payload: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(payload)).pages)


def _pdf_image_sizes(payload: bytes) -> list[tuple[int, int]]:
    return [image.image.size for page in PdfReader(io.BytesIO(payload)).pages for image in page.images]


def _create_request(client) -> int:
    login(client, *LEADER_A)
    response = client.post(
        "/product-evaluations",
        data={
            "csrf_token": csrf_of(client, "/product-evaluations/new"),
            "device_name": "Solar Controller X",
            "manufacturer": "Future Power",
            "model": "SCX-500",
            "customer_project_name": "Desert Gate Pilot",
            "sales_user_id": "3",
            "sales_external": "",
            "after_sales_user_id": "",
            "after_sales_external": "External Support Engineer",
            "assigned_admin_id": "1",
            "reason": "Evaluate the controller before customer deployment.",
            "requirements": "Test heat tolerance and remote monitoring.",
        },
        files=[("files", ("initial.jpg", make_image(), "image/jpeg"))],
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/product-evaluations/")
    return int(response.headers["location"].rsplit("/", 1)[1])


def _approve_receive_and_schedule(client, request_id: int) -> int:
    logout(client)
    login(client, *ADMIN)
    response = client.post(
        f"/product-evaluations/{request_id}/decision",
        data={"csrf_token": csrf_of(client, f"/product-evaluations/{request_id}"), "action": "approve", "admin_notes": "Approved for purchase."},
    )
    assert response.status_code == 303
    response = client.post(
        f"/product-evaluations/{request_id}/receive",
        data={"csrf_token": csrf_of(client, f"/product-evaluations/{request_id}"), "serial_number": "SCX-SN-2026-001"},
    )
    assert response.status_code == 303
    response = client.post(
        f"/product-evaluations/{request_id}/sessions",
        data={
            "csrf_token": csrf_of(client, f"/product-evaluations/{request_id}"),
            "assigned_user_id": "2",
            "scheduled_start_at": "2026-08-28T09:00",
            "due_at": "2026-08-28T17:00",
            "location": "Lab A",
            "instructions": "Test under representative load.",
        },
    )
    assert response.status_code == 303
    return int(response.headers["location"].split("/")[3])


def test_full_product_evaluation_lifecycle_repeat_session_search_and_reports(client, db):
    request_id = _create_request(client)
    db.expire_all()
    evaluation = db.get(ProductEvaluationRequest, request_id)
    assert evaluation.request_number.startswith("PE-")
    assert evaluation.status == ProductEvaluationStatus.PENDING_APPROVAL
    assert evaluation.sales_contact_name == "Leader Two"
    assert evaluation.after_sales_name == "External Support Engineer"
    assert len(evaluation.attachments) == 1

    session_id = _approve_receive_and_schedule(client, request_id)
    db.expire_all()
    evaluation = db.get(ProductEvaluationRequest, request_id)
    assert evaluation.serial_number == "SCX-SN-2026-001"
    assert evaluation.approved_at is not None
    assert evaluation.received_at is not None
    assert evaluation.status == ProductEvaluationStatus.EVALUATION_SCHEDULED

    logout(client)
    login(client, *LEADER_A)
    response = client.post(
        f"/product-evaluations/sessions/{session_id}/start",
        data={"csrf_token": csrf_of(client, f"/product-evaluations/sessions/{session_id}")},
    )
    assert response.status_code == 303

    incomplete = client.post(
        f"/product-evaluations/sessions/{session_id}/save",
        data={
            "csrf_token": csrf_of(client, f"/product-evaluations/sessions/{session_id}"),
            "action": "complete",
            "tests_performed": "Thermal load test",
        },
    )
    assert incomplete.status_code == 303
    db.expire_all()
    assert db.get(ProductEvaluationSession, session_id).status == ProductEvaluationSessionStatus.IN_PROGRESS

    completed = client.post(
        f"/product-evaluations/sessions/{session_id}/save",
        data={
            "csrf_token": csrf_of(client, f"/product-evaluations/sessions/{session_id}"),
            "action": "complete",
            "tests_performed": "Thermal load and remote monitoring",
            "results": "Stable throughout the test.",
            "strengths": "Clear dashboard",
            "weaknesses": "Large enclosure",
            "issues_found": "No critical issues",
            "compatibility": "Compatible with the pilot project",
            "recommendation": "Approve for the pilot rollout.",
            "performance_rating": "5",
            "quality_rating": "4",
            "installation_rating": "4",
            "compatibility_rating": "5",
            "value_rating": "4",
            "decision": "approved",
            "new_file_description": "Controller during thermal test",
        },
        files=[("files", ("evidence.png", make_image(fmt="PNG"), "image/png"))],
    )
    assert completed.status_code == 303
    db.expire_all()
    first = db.get(ProductEvaluationSession, session_id)
    assert first.status == ProductEvaluationSessionStatus.COMPLETED
    assert first.decision == ProductEvaluationDecision.APPROVED
    assert first.started_at is not None and first.completed_at is not None
    assert len(first.attachments) == 1

    listing = client.get("/product-evaluations?view=my&q=SCX-SN-2026-001")
    assert listing.status_code == 200
    assert "SCX-500" in listing.text

    session_pdf = client.get(f"/product-evaluations/sessions/{session_id}/report.pdf")
    assert session_pdf.status_code == 200
    text = _pdf_text(session_pdf.content)
    assert "Solar Controller X" in text
    assert "SCX-SN-2026-001" in text
    assert "Approve for the pilot rollout" in text
    assert (320, 240) in _pdf_image_sizes(session_pdf.content)

    completed_at = first.completed_at
    edit_page = client.get(f"/product-evaluations/sessions/{session_id}")
    assert edit_page.status_code == 200
    assert "This evaluation is completed" in edit_page.text
    edited = client.post(
        f"/product-evaluations/sessions/{session_id}/save",
        data={
            "csrf_token": csrf_of(client, f"/product-evaluations/sessions/{session_id}"),
            "action": "update",
            "tests_performed": "Thermal load, remote monitoring, and retest",
            "results": "Stable throughout the corrected test.",
            "strengths": "Clear dashboard",
            "weaknesses": "Large enclosure",
            "issues_found": "No critical issues",
            "compatibility": "Compatible with the pilot project",
            "recommendation": "Approve after the corrected retest.",
            "performance_rating": "5",
            "quality_rating": "4",
            "installation_rating": "4",
            "compatibility_rating": "5",
            "value_rating": "4",
            "decision": "approved",
            "new_file_description": "Corrected evaluation evidence",
            "remove_attachment_ids": str(first.attachments[0].id),
        },
        files=[("files", ("corrected-evidence.png", make_image(color=(180, 40, 60), fmt="PNG"), "image/png"))],
    )
    assert edited.status_code == 303
    db.expire_all()
    first = db.get(ProductEvaluationSession, session_id)
    assert first.status == ProductEvaluationSessionStatus.COMPLETED
    assert first.completed_at == completed_at
    assert first.results == "Stable throughout the corrected test."
    assert [attachment.original_filename for attachment in first.attachments] == ["corrected-evidence.png"]
    corrected_pdf = client.get(f"/product-evaluations/sessions/{session_id}/report.pdf")
    assert "Approve after the corrected retest" in _pdf_text(corrected_pdf.content)
    assert (320, 240) in _pdf_image_sizes(corrected_pdf.content)

    logout(client)
    login(client, *ADMIN)
    copy_response = client.get(f"/product-evaluations/{request_id}/add-to-pricing")
    assert copy_response.status_code == 303
    pricing_page = client.get(copy_response.headers["location"])
    assert pricing_page.status_code == 200
    assert 'value="Solar Controller X"' in pricing_page.text
    assert 'value="SCX-500"' in pricing_page.text

    second = client.post(
        f"/product-evaluations/{request_id}/sessions",
        data={
            "csrf_token": csrf_of(client, f"/product-evaluations/{request_id}"),
            "assigned_user_id": "3",
            "scheduled_start_at": "2027-08-28T09:00",
            "due_at": "2027-08-29T09:00",
            "location": "Customer pilot site",
            "instructions": "Repeat the evaluation after long-term use.",
        },
    )
    assert second.status_code == 303
    db.expire_all()
    sessions = list(db.query(ProductEvaluationSession).filter_by(request_id=request_id).order_by(ProductEvaluationSession.sequence))
    assert [entry.sequence for entry in sessions] == [1, 2]
    assert sessions[1].assigned_user_name == "Leader Two"

    full_pdf = client.get(f"/product-evaluations/{request_id}/report.pdf")
    assert full_pdf.status_code == 200
    full_text = _pdf_text(full_pdf.content)
    assert "Evaluation Session 1" in full_text
    assert "Evaluation Session 2" in full_text
    assert "Initial Request Images" in full_text
    assert (320, 240) in _pdf_image_sizes(full_pdf.content)


def test_product_evaluation_permissions_duplicate_serial_and_change_request(client, db):
    login(client, *CUSTOMER_A)
    assert client.get("/product-evaluations").status_code == 403
    logout(client)

    request_id = _create_request(client)
    logout(client)
    leader = db.query(User).filter(User.username == LEADER_B[0]).one()
    permission = db.get(
        UserDepartmentPermission,
        (leader.id, 1, "product_evaluations.approve"),
    )
    assert permission is not None
    permission.allowed = False
    db.commit()
    login(client, *LEADER_B)
    assert client.post(
        f"/product-evaluations/{request_id}/decision",
        data={"csrf_token": csrf_of(client, "/dashboard"), "action": "approve"},
    ).status_code == 403
    logout(client)

    login(client, *ADMIN)
    changed = client.post(
        f"/product-evaluations/{request_id}/decision",
        data={"csrf_token": csrf_of(client, f"/product-evaluations/{request_id}"), "action": "changes", "admin_notes": "Clarify the required environmental test."},
    )
    assert changed.status_code == 303
    db.expire_all()
    assert db.get(ProductEvaluationRequest, request_id).status == ProductEvaluationStatus.CHANGES_REQUESTED

    logout(client)
    login(client, *LEADER_A)
    edit_page = client.get(f"/product-evaluations/{request_id}/edit")
    assert edit_page.status_code == 200
    assert "Clarify the required environmental test" in edit_page.text

    # A serial is unique to the physical device request, while later tests reuse
    # the same request and therefore the same serial.
    db.add(
        ProductEvaluationRequest(
            request_number="PE-2026-99999",
            device_name="Existing Device",
            model="OLD-1",
            serial_number="DUPLICATE-SERIAL",
            customer_project_name="Existing Pilot",
            sales_contact_name="Sales",
            after_sales_name="Support",
            assigned_admin_id=1,
            assigned_admin_name="Test Admin",
            reason="Existing request",
            status=ProductEvaluationStatus.WAITING_FOR_DEVICE,
            created_by_id=2,
            created_by_name="Leader One",
        )
    )
    db.commit()

    # The request remains isolated from Pricing until the explicit prefill action.
    assert not hasattr(db.get(ProductEvaluationRequest, request_id), "pricing_item_id")
