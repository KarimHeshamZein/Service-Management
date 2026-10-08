"""Focused coverage for Department isolation, overrides and task delivery."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.access_control import permission_allowed, project_access_allowed
from app.database import SessionLocal
import app.routers.pricing as pricing_router
from app.models import (
    AccessScope,
    AuditEvent,
    Department,
    DepartmentPermission,
    InstallationRecord,
    MaintenanceResult,
    PricingItem,
    PricingItemCategory,
    PricingRelatedItem,
    PurchaseDocument,
    PurchaseDocumentItem,
    PurchaseDocumentType,
    PricingCategoryUserAccess,
    PricingItemUserAccess,
    ProjectTeamMember,
    StoreUserWarehouse,
    StoreWarehouse,
    StoreWarehouseType,
    TaskStatus,
    User,
    UserDepartment,
    UserDepartmentPermission,
    UserDepartmentScope,
    UserNotification,
    WorkTask,
)
from app.permissions import PERMISSIONS
from tests.conftest import ADMIN, LEADER_A, LEADER_B, csrf_of, login, logout


def _add_department(db, *, name: str = "Operations", code: str = "OPS") -> Department:
    # The shared fixture deliberately seeds General with an explicit id=1, so
    # use the next stable identity instead of relying on the untouched sequence.
    department = Department(id=2, name=name, code=code)
    db.add(department)
    db.flush()
    db.add_all(
        DepartmentPermission(
            department_id=department.id,
            permission_key=permission.key,
            allowed=True,
        )
        for permission in PERMISSIONS
    )
    db.commit()
    return department


def test_user_permissions_are_direct_and_do_not_inherit_department_defaults(db):
    user = db.query(User).filter(User.username == LEADER_A[0]).one()

    assert permission_allowed(db, user, 1, "pricing_items.view") is True
    pricing_permission = db.get(
        UserDepartmentPermission, (user.id, 1, "pricing_items.view")
    )
    pricing_permission.allowed = False
    db.commit()
    assert permission_allowed(db, user, 1, "pricing_items.view") is False

    default = db.get(DepartmentPermission, (1, "tasks.create"))
    default.allowed = False
    task_permission = db.get(
        UserDepartmentPermission, (user.id, 1, "tasks.create")
    )
    task_permission.allowed = False
    db.commit()
    assert permission_allowed(db, user, 1, "tasks.create") is False
    task_permission.allowed = True
    db.commit()
    assert permission_allowed(db, user, 1, "tasks.create") is True


def _installation(*, number: str, project_id: int, user_id: int) -> InstallationRecord:
    return InstallationRecord(
        record_number=number,
        site_id=project_id,
        service_type_id=1,
        submitted_by_id=user_id,
        site_name=f"Project {project_id}",
        customer_name="Scope test customer",
        site_address="Riyadh",
        service_name="Camera Service",
        team_leader_name=f"User {user_id}",
        equipment_model="Scope test model",
        result=MaintenanceResult.COMPLETED_SUCCESSFULLY,
        notes="",
    )


def test_create_permission_keeps_only_the_users_own_records_visible(client, db):
    user = db.query(User).filter(User.username == LEADER_A[0]).one()
    db.query(UserDepartmentPermission).filter(
        UserDepartmentPermission.user_id == user.id,
        UserDepartmentPermission.department_id == 1,
    ).delete(synchronize_session=False)
    db.add(UserDepartmentPermission(
        user_id=user.id,
        department_id=1,
        permission_key="records.create_installation",
        allowed=True,
    ))
    scope = db.get(UserDepartmentScope, (user.id, 1, "records"))
    scope.scope = AccessScope.NONE
    db.add_all([
        _installation(number="NI-2099-OWN01", project_id=1, user_id=user.id),
        _installation(number="NI-2099-OTHER", project_id=1, user_id=3),
    ])
    db.commit()

    login(client, *LEADER_A)
    response = client.get("/installations/records")
    assert response.status_code == 200
    assert "NI-2099-OWN01" in response.text
    assert "NI-2099-OTHER" not in response.text


def test_selected_project_scope_exposes_other_users_work_only_in_selected_projects(client, db):
    user = db.query(User).filter(User.username == LEADER_A[0]).one()
    db.get(UserDepartmentScope, (user.id, 1, "records")).scope = AccessScope.SELECTED
    db.query(ProjectTeamMember).filter(
        ProjectTeamMember.user_id == user.id,
        ProjectTeamMember.project_id.in_((2, 3)),
    ).delete(synchronize_session=False)
    db.add_all([
        _installation(number="NI-2099-SELECTED", project_id=1, user_id=3),
        _installation(number="NI-2099-HIDDEN", project_id=3, user_id=3),
    ])
    db.commit()

    login(client, *LEADER_A)
    response = client.get("/installations/records")
    assert response.status_code == 200
    assert "NI-2099-SELECTED" in response.text
    assert "NI-2099-HIDDEN" not in response.text


def test_selected_pricing_scope_supports_whole_categories_and_individual_items(client, db):
    user = db.query(User).filter(User.username == LEADER_A[0]).one()
    selected = PricingItemCategory(name="Selected CCTV", department_id=1)
    selected_sub = PricingItemCategory(
        name="Selected brand", department_id=1, parent=selected
    )
    selected_leaf = PricingItemCategory(
        name="Selected cameras", department_id=1, parent=selected_sub
    )
    individual_folder = PricingItemCategory(name="Individual access", department_id=1)
    individual_sub = PricingItemCategory(
        name="Individual brand", department_id=1, parent=individual_folder
    )
    individual_leaf = PricingItemCategory(
        name="Individual cameras", department_id=1, parent=individual_sub
    )
    db.add_all([selected, individual_folder])
    db.flush()
    category_item = PricingItem(
        department_id=1, category_id=selected_leaf.id, name="Allowed category camera",
        model="CAT-1", unit_price=Decimal("10"), currency="SAR",
    )
    direct_item = PricingItem(
        department_id=1, category_id=individual_leaf.id, name="Allowed direct camera",
        model="DIRECT-1", unit_price=Decimal("20"), currency="SAR",
    )
    hidden_item = PricingItem(
        department_id=1, category_id=individual_leaf.id, name="Hidden peer camera",
        model="HIDDEN-1", unit_price=Decimal("30"), currency="SAR",
    )
    db.add_all([category_item, direct_item, hidden_item])
    db.flush()
    db.add(PricingCategoryUserAccess(
        category_id=selected.id, user_id=user.id, granted_by_id=1
    ))
    db.add(PricingItemUserAccess(
        item_id=direct_item.id, user_id=user.id, granted_by_id=1
    ))
    db.get(UserDepartmentScope, (user.id, 1, "pricing_items")).scope = AccessScope.SELECTED
    db.commit()

    login(client, *LEADER_A)
    category_page = client.get(f"/pricing/items?category={selected_leaf.id}")
    assert category_page.status_code == 200
    assert "Allowed category camera" in category_page.text
    direct_page = client.get(f"/pricing/items?category={individual_leaf.id}")
    assert direct_page.status_code == 200
    assert "Allowed direct camera" in direct_page.text
    assert "Hidden peer camera" not in direct_page.text


def test_category_content_posts_cannot_change_user_grants(client, db):
    manager = db.query(User).filter(User.username == LEADER_A[0]).one()
    other_user = db.query(User).filter(User.username == LEADER_B[0]).one()
    root = PricingItemCategory(name="Grant root", department_id=1)
    child = PricingItemCategory(name="Grant child", department_id=1, parent=root)
    leaf = PricingItemCategory(name="Grant leaf", department_id=1, parent=child)
    db.add(root)
    db.flush()
    item = PricingItem(
        department_id=1, category_id=leaf.id, name="Granted device",
        model="GRANT-1", unit_price=Decimal("10"), currency="SAR",
    )
    db.add(item)
    db.flush()
    db.add_all([
        PricingItemUserAccess(item_id=item.id, user_id=manager.id, granted_by_id=1),
        PricingCategoryUserAccess(category_id=root.id, user_id=other_user.id, granted_by_id=1),
    ])
    db.get(UserDepartmentScope, (manager.id, 1, "pricing_items")).scope = AccessScope.SELECTED
    db.commit()

    login(client, *LEADER_A)
    page = client.get(f"/pricing/items?category={root.id}")
    assert page.status_code == 200
    assert 'name="category_user_ids"' not in page.text
    token = csrf_of(client, f"/pricing/items?category={root.id}")
    renamed = client.post(f"/pricing/categories/{root.id}/edit", data={
        "csrf_token": token, "name": "Grant root renamed",
        "visibility": "selected_users", "category_user_ids": str(manager.id),
    })
    assert renamed.status_code == 303
    db.refresh(root)
    assert root.name == "Grant root renamed"
    assert root.visibility == "department"
    assert set(db.scalars(select(PricingCategoryUserAccess.user_id).where(
        PricingCategoryUserAccess.category_id == root.id
    ))) == {other_user.id}

    created = client.post("/pricing/categories", data={
        "csrf_token": token, "name": "Forged grant category",
        "visibility": "selected_users", "category_user_ids": str(manager.id),
    })
    assert created.status_code == 303
    category = db.scalar(select(PricingItemCategory).where(
        PricingItemCategory.name == "Forged grant category"
    ))
    assert category is not None and category.visibility == "department"
    assert not db.scalar(select(PricingCategoryUserAccess).where(
        PricingCategoryUserAccess.category_id == category.id
    ))


def test_user_roles_reconciles_nested_pricing_grants_without_erasing_newer_grants(client, db):
    target = db.query(User).filter(User.username == LEADER_A[0]).one()
    root = PricingItemCategory(name="Roles root", department_id=1)
    child = PricingItemCategory(name="Roles child", department_id=1, parent=root)
    leaf = PricingItemCategory(name="Roles leaf", department_id=1, parent=child)
    later = PricingItemCategory(name="Later grant", department_id=1)
    db.add_all([root, later])
    db.flush()
    item = PricingItem(
        department_id=1, category_id=leaf.id, name="Roles device",
        model="ROLES-1", unit_price=Decimal("10"), currency="SAR",
    )
    db.add(item)
    db.flush()
    db.add_all([
        PricingCategoryUserAccess(category_id=leaf.id, user_id=target.id, granted_by_id=1),
        PricingItemUserAccess(item_id=item.id, user_id=target.id, granted_by_id=1),
    ])
    db.commit()

    login(client, *ADMIN)
    page = client.get(f"/users/{target.id}/access")
    assert page.status_code == 200
    assert "Roles root / Roles child / Roles leaf" in page.text
    assert f'name="category_original:1" value="{leaf.id}"' in page.text
    assert f'name="item_original:1" value="{item.id}"' in page.text
    token = csrf_of(client, f"/users/{target.id}/access")
    switched = client.post("/language", data={
        "language": "ar", "next": f"/users/{target.id}/access", "csrf_token": token,
    })
    assert switched.status_code == 303
    arabic_page = client.get(f"/users/{target.id}/access")
    assert '<html lang="ar" dir="rtl">' in arabic_page.text
    assert "Roles root / Roles child / Roles leaf" in arabic_page.text

    # A second Administrator may grant another Category after this form opens.
    db.add(PricingCategoryUserAccess(
        category_id=later.id, user_id=target.id, granted_by_id=1,
    ))
    db.commit()
    unchanged = client.post(f"/users/{target.id}/access", data={
        "csrf_token": token, "department_id": "1", "primary_department_id": "1",
        "category:1": str(leaf.id), "category_original:1": str(leaf.id),
        "item:1": str(item.id), "item_original:1": str(item.id),
    })
    assert unchanged.status_code == 303
    assert set(db.scalars(select(PricingCategoryUserAccess.category_id).where(
        PricingCategoryUserAccess.user_id == target.id
    ))) == {leaf.id, later.id}
    assert set(db.scalars(select(PricingItemUserAccess.item_id).where(
        PricingItemUserAccess.user_id == target.id
    ))) == {item.id}

    revoked = client.post(f"/users/{target.id}/access", data={
        "csrf_token": token, "department_id": "1", "primary_department_id": "1",
        "category_original:1": str(leaf.id),
        "item_original:1": str(item.id),
    })
    assert revoked.status_code == 303
    assert set(db.scalars(select(PricingCategoryUserAccess.category_id).where(
        PricingCategoryUserAccess.user_id == target.id
    ))) == {later.id}
    assert not db.scalar(select(PricingItemUserAccess).where(
        PricingItemUserAccess.user_id == target.id
    ))

    granted = client.post(f"/users/{target.id}/access", data={
        "csrf_token": token, "department_id": "1", "primary_department_id": "1",
        "category:1": str(root.id),
    })
    assert granted.status_code == 303
    assert set(db.scalars(select(PricingCategoryUserAccess.category_id).where(
        PricingCategoryUserAccess.user_id == target.id
    ))) == {root.id, later.id}


def test_internal_user_creation_requires_department_and_opens_roles_page(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/users")
    rejected = client.post("/users", data={
        "full_name": "No Department", "username": "no.department@test.local",
        "password": "StrongPass123", "role": "technical", "csrf_token": token,
    })
    assert rejected.status_code == 303
    assert rejected.headers["location"] == "/users"
    assert db.query(User).filter(User.username == "no.department@test.local").first() is None

    token = csrf_of(client, "/users")
    created = client.post("/users", data={
        "full_name": "Scoped User", "username": "scoped.user@test.local",
        "password": "StrongPass123", "role": "technical",
        "department_ids": "1", "csrf_token": token,
    })
    new_user = db.query(User).filter(User.username == "scoped.user@test.local").one()
    assert created.status_code == 303
    assert created.headers["location"] == f"/users/{new_user.id}/access"
    membership = db.get(UserDepartment, (new_user.id, 1))
    assert membership is not None and membership.is_primary is True


def test_switching_workspace_isolates_pricing_library(client, db):
    operations = _add_department(db)
    user = db.query(User).filter(User.username == LEADER_A[0]).one()
    db.add(UserDepartment(user_id=user.id, department_id=operations.id))
    db.add(UserDepartmentPermission(
        user_id=user.id,
        department_id=operations.id,
        permission_key="pricing_items.view",
        allowed=True,
    ))
    db.add(UserDepartmentScope(
        user_id=user.id,
        department_id=operations.id,
        module_key="pricing_items",
        scope=AccessScope.DEPARTMENT,
    ))
    db.add(
        PricingItem(
            department_id=operations.id,
            name="Operations-only camera",
            unit_price=Decimal("325.00"),
            currency="SAR",
        )
    )
    db.commit()

    login(client, *LEADER_A)
    general = client.get("/pricing/items?category=uncategorized")
    assert general.status_code == 200
    assert "Operations-only camera" not in general.text

    token = csrf_of(client, "/dashboard")
    switched = client.post(
        "/workspace",
        data={
            "department_id": str(operations.id),
            "next_url": "/pricing/items",
            "csrf_token": token,
        },
    )
    assert switched.status_code == 303
    operations_page = client.get("/pricing/items?category=uncategorized")
    assert operations_page.status_code == 200
    assert "Operations-only camera" in operations_page.text
    assert "IP Camera" not in operations_page.text


def test_pricing_starts_with_department_folders(client, db):
    operations = _add_department(db)
    db.add(PricingItem(
        department_id=operations.id,
        name="Operations-only camera",
        unit_price=Decimal("325.00"),
        currency="SAR",
    ))
    db.commit()

    login(client, *ADMIN)
    pricing_root = client.get("/pricing", follow_redirects=False)
    assert pricing_root.status_code == 303
    assert pricing_root.headers["location"] == "/pricing/quotations/departments"
    item_folders = client.get("/pricing/items/departments")
    assert item_folders.status_code == 200
    assert "General" in item_folders.text
    assert "Operations" in item_folders.text
    assert 'name="next_url" value="/pricing/items"' in item_folders.text

    quotation_folders = client.get("/pricing/quotations/departments")
    assert quotation_folders.status_code == 200
    assert "General" in quotation_folders.text
    assert "Operations" in quotation_folders.text
    assert 'name="next_url" value="/pricing/quotations"' in quotation_folders.text


def test_department_folders_hide_workspaces_without_direct_user_permission(client, db):
    operations = _add_department(db)
    user = db.query(User).filter(User.username == LEADER_A[0]).one()
    db.add(UserDepartment(user_id=user.id, department_id=operations.id))
    db.commit()

    login(client, *LEADER_A)
    item_folders = client.get("/pricing/items/departments")
    assert item_folders.status_code == 200
    assert "<strong>General</strong>" in item_folders.text
    assert "<strong>Operations</strong>" not in item_folders.text


def test_admin_can_move_category_tree_and_items_to_another_department(client, db):
    operations = _add_department(db)
    root = PricingItemCategory(name="Cameras", department_id=1)
    child = PricingItemCategory(name="Hikvision", department_id=1, parent=root)
    grandchild = PricingItemCategory(
        name="Hikvision NVR",
        department_id=1,
        parent=child,
    )
    direct_item = PricingItem(
        department_id=1,
        category=root,
        name="Department camera",
        model="MAIN",
        unit_price=Decimal("100.00"),
        currency="SAR",
    )
    child_item = PricingItem(
        department_id=1,
        category=grandchild,
        name="Department NVR",
        model="SUB",
        unit_price=Decimal("200.00"),
        currency="SAR",
    )
    child_item.related_items.append(PricingRelatedItem(
        department_id=1,
        name="NVR disk",
        unit_price=Decimal("25.00"),
        currency="SAR",
    ))
    db.add(root)
    db.commit()
    root_id = root.id
    child_id = child.id
    grandchild_id = grandchild.id
    item_ids = {direct_item.id, child_item.id}

    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items")
    moved = client.post(
        f"/pricing/categories/{root_id}/move-department",
        data={
            "target_department_id": str(operations.id),
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert moved.status_code == 303
    assert moved.headers["location"] == "/pricing/items/departments"

    db.expire_all()
    moved_categories = list(db.scalars(
        select(PricingItemCategory)
        .where(PricingItemCategory.id.in_({root_id, child_id, grandchild_id}))
        .execution_options(include_all_departments=True)
    ))
    moved_items = list(db.scalars(
        select(PricingItem)
        .where(PricingItem.id.in_(item_ids))
        .execution_options(include_all_departments=True)
    ))
    moved_related = db.scalar(
        select(PricingRelatedItem)
        .where(PricingRelatedItem.main_item_id == child_item.id)
        .execution_options(include_all_departments=True)
    )
    assert {entry.department_id for entry in moved_categories} == {operations.id}
    assert next(entry for entry in moved_categories if entry.id == child_id).parent_id == root_id
    assert next(entry for entry in moved_categories if entry.id == grandchild_id).parent_id == child_id
    assert {entry.department_id for entry in moved_items} == {operations.id}
    assert moved_related is not None and moved_related.department_id == operations.id

    token = csrf_of(client, "/dashboard")
    switched = client.post(
        "/workspace",
        data={
            "department_id": str(operations.id),
            "next_url": f"/pricing/items?category={root_id}",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert switched.status_code == 303
    target_page = client.get(f"/pricing/items?category={root_id}")
    assert target_page.status_code == 200
    assert "Department camera" in target_page.text
    assert "Hikvision" in target_page.text


def test_category_manager_separates_edit_move_delete_and_keeps_category_context(client, db):
    target = _add_department(db)
    root = PricingItemCategory(name="Security", department_id=1)
    child = PricingItemCategory(name="Cameras", department_id=1, parent=root)
    other = PricingItemCategory(name="Other", department_id=1)
    empty = PricingItemCategory(name="Empty", department_id=1)
    db.add_all([root, child, other, empty])
    db.commit()
    empty_id = empty.id
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/categories/manage")

    items_page = client.get("/pricing/items")
    assert 'href="/pricing/categories/manage"' in items_page.text
    page = client.get(f"/pricing/categories/manage?category_id={root.id}")
    assert page.status_code == 200
    assert f'href="/pricing/categories/manage?category_id={child.id}"' in page.text
    assert 'data-folder-destination-picker' in page.text
    assert 'data-folder-rename-form' in page.text
    assert 'data-folder-delete-form' in page.text
    assert 'name="category_kind" value="main"' in page.text
    assert 'name="category_kind" value="sub"' in page.text
    move_form = re.search(
        rf'<form method="post" action="/pricing/categories/{root.id}/move-department"(.*?)</form>',
        page.text, re.S,
    )
    assert move_form is None
    assert 'data-folder-id="' + str(root.id) + '"' in page.text
    assert 'name="target_department_id"' in page.text
    assert 'name="category_ids"' in page.text

    searched = client.get("/pricing/categories/manage?q=Security")
    browser_html = searched.text.split('<section class="pricing-category-browser"', 1)[1].split("</section>", 1)[0]
    assert "Security" in browser_html and "Cameras" in browser_html
    assert "Other" not in browser_html

    created = client.post("/pricing/categories", data={
        "csrf_token": token, "from_manager": "1", "name": "Access Control",
        "parent_category_id": str(root.id),
    })
    assert created.status_code == 303
    created_category = db.scalar(select(PricingItemCategory).where(PricingItemCategory.name == "Access Control"))
    assert created_category.parent_id == root.id
    assert created.headers["location"] == f"/pricing/categories/manage?category_id={created_category.id}"
    duplicate = client.post("/pricing/categories", data={
        "csrf_token": token, "from_manager": "1", "name": "Access Control",
        "parent_category_id": str(root.id),
    })
    assert duplicate.status_code == 422
    assert 'value="Access Control"' in duplicate.text
    assert f'name="parent_category_id" value="{root.id}"' in duplicate.text

    missing_parent = client.post("/pricing/categories", data={
        "csrf_token": token, "from_manager": "1", "category_kind": "sub",
        "name": "Missing parent", "parent_category_id": "",
    })
    assert missing_parent.status_code == 422
    assert db.scalar(select(PricingItemCategory).where(PricingItemCategory.name == "Missing parent")) is None
    standalone = client.post("/pricing/categories", data={
        "csrf_token": token, "from_manager": "1", "category_kind": "main",
        "name": "Standalone", "parent_category_id": str(root.id),
    })
    assert standalone.status_code == 303
    assert db.scalar(select(PricingItemCategory).where(PricingItemCategory.name == "Standalone")).parent_id is None

    renamed = client.post(f"/pricing/categories/{root.id}/edit", data={
        "csrf_token": token, "from_manager": "1", "name": "Site Security",
        "parent_category_id": "",
    })
    assert renamed.status_code == 303
    assert renamed.headers["location"] == f"/pricing/categories/manage?category_id={root.id}"
    db.expire_all()
    assert db.get(PricingItemCategory, root.id).name == "Site Security"

    moved_inside = client.post(f"/pricing/categories/{child.id}/edit", data={
        "csrf_token": token, "from_manager": "1", "name": "Cameras",
        "parent_category_id": str(other.id),
    })
    assert moved_inside.status_code == 303
    assert moved_inside.headers["location"] == f"/pricing/categories/manage?category_id={child.id}"
    db.expire_all()
    assert db.get(PricingItemCategory, child.id).parent_id == other.id

    invalid = client.post(f"/pricing/categories/{other.id}/edit", data={
        "csrf_token": token, "from_manager": "1", "name": "Other revised",
        "parent_category_id": str(child.id),
    })
    assert invalid.status_code == 422
    assert 'value="Other revised"' in invalid.text
    assert 'data-folder-rename-form' in invalid.text
    db.expire_all()
    assert (db.get(PricingItemCategory, other.id).name, db.get(PricingItemCategory, other.id).parent_id) == ("Other", None)

    deleted = client.post(f"/pricing/categories/{empty_id}/delete", data={
        "csrf_token": token, "from_manager": "1",
    })
    assert deleted.status_code == 303
    assert deleted.headers["location"] == "/pricing/categories/manage"
    db.expire_all()
    assert db.get(PricingItemCategory, empty_id) is None

    transferred = client.post(f"/pricing/categories/{root.id}/move-department", data={
        "csrf_token": token, "from_manager": "1",
        "target_department_id": str(target.id),
    })
    assert transferred.status_code == 303
    assert transferred.headers["location"] == "/pricing/items/departments"


def test_folder_move_nests_a_full_branch_across_departments_with_items(client, db):
    target = _add_department(db)
    root = PricingItemCategory(name="Cameras", department_id=1)
    child = PricingItemCategory(name="Outdoor", department_id=1, parent=root)
    grandchild = PricingItemCategory(name="Dome", department_id=1, parent=child)
    source_item = PricingItem(
        department_id=1, category=grandchild, name="Deep camera", model="DC-1",
        unit_price=Decimal("100.00"), currency="SAR",
    )
    source_item.related_items.append(PricingRelatedItem(
        department_id=1, name="Mount", unit_price=Decimal("5.00"), currency="SAR",
    ))
    target_root = PricingItemCategory(name="Security", department_id=target.id)
    target_child = PricingItemCategory(name="Equipment", department_id=target.id, parent=target_root)
    db.add_all([root, target_root])
    db.commit()
    root_id, child_id, grandchild_id, item_id = root.id, child.id, grandchild.id, source_item.id
    db.add_all([
        PricingCategoryUserAccess(category_id=child_id, user_id=2, granted_by_id=1),
        PricingItemUserAccess(item_id=item_id, user_id=2, granted_by_id=1),
    ])
    db.commit()

    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/categories/manage")
    page = client.get("/pricing/categories/manage")
    assert f'id="folder-destination-{target_child.id}"' in page.text
    moved = client.post("/pricing/categories/move", data={
        "csrf_token": token, "category_ids": str(root_id),
        "target_department_id": str(target.id), "target_category_id": str(target_child.id),
        "move_items": "yes",
    })
    assert moved.status_code == 303
    db.expire_all()
    assert db.get(PricingItemCategory, root_id).parent_id == target_child.id
    assert db.get(PricingItemCategory, child_id).parent_id == root_id
    assert db.get(PricingItemCategory, grandchild_id).parent_id == child_id
    assert {db.get(PricingItemCategory, entry_id).department_id for entry_id in (root_id, child_id, grandchild_id)} == {target.id}
    assert db.get(PricingItem, item_id).department_id == target.id
    assert db.get(PricingItem, item_id).category_id == grandchild_id
    assert db.get(PricingItem, item_id).related_items[0].department_id == target.id
    assert db.get(PricingItemCategory, grandchild_id).depth == 4
    assert db.scalar(select(PricingCategoryUserAccess).where(PricingCategoryUserAccess.category_id == child_id)) is None
    assert db.scalar(select(PricingItemUserAccess).where(PricingItemUserAccess.item_id == item_id)) is None


def test_multiple_folder_move_without_items_keeps_items_in_source_uncategorized(client, db):
    target = _add_department(db)
    root = PricingItemCategory(name="Cameras", department_id=1)
    child = PricingItemCategory(name="Outdoor", department_id=1, parent=root)
    peer = PricingItemCategory(name="Gates", department_id=1)
    destination = PricingItemCategory(name="Hardware", department_id=target.id)
    first = PricingItem(department_id=1, category=child, name="Camera", model="C1", unit_price=Decimal("10"))
    second = PricingItem(department_id=1, category=peer, name="Gate", model="G1", unit_price=Decimal("20"))
    db.add_all([root, peer, destination])
    db.commit()
    root_id, child_id, peer_id, first_id, second_id = root.id, child.id, peer.id, first.id, second.id

    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/categories/manage")
    moved = client.post("/pricing/categories/move", data={
        "csrf_token": token,
        "category_ids": [str(root_id), str(child_id), str(peer_id)],
        "target_department_id": str(target.id), "target_category_id": str(destination.id),
        "move_items": "no",
    })
    assert moved.status_code == 303
    db.expire_all()
    assert db.get(PricingItemCategory, root_id).parent_id == destination.id
    assert db.get(PricingItemCategory, child_id).parent_id == root_id
    assert db.get(PricingItemCategory, peer_id).parent_id == destination.id
    assert {db.get(PricingItemCategory, entry_id).department_id for entry_id in (root_id, child_id, peer_id)} == {target.id}
    assert {(db.get(PricingItem, entry_id).department_id, db.get(PricingItem, entry_id).category_id) for entry_id in (first_id, second_id)} == {(1, None)}


def test_bulk_item_move_uses_only_chosen_direct_items_and_preserves_folders(client, db):
    target = _add_department(db)
    source = PricingItemCategory(name="Cameras", department_id=1)
    child = PricingItemCategory(name="Indoor", department_id=1, parent=source)
    destination = PricingItemCategory(name="Equipment", department_id=target.id)
    first = PricingItem(department_id=1, category=source, name="Camera A", model="A", unit_price=Decimal("10"))
    second = PricingItem(department_id=1, category=source, name="Camera B", model="B", unit_price=Decimal("20"))
    nested = PricingItem(department_id=1, category=child, name="Indoor Camera", model="I", unit_price=Decimal("30"))
    db.add_all([source, destination])
    db.commit()
    source_id, child_id, first_id, second_id, nested_id = source.id, child.id, first.id, second.id, nested.id

    login(client, *ADMIN)
    page = client.get(f"/pricing/items?category={source_id}")
    table = page.text.split("<table>", 1)[1].split("</table>", 1)[0]
    assert 'data-pricing-items-select-all' in table
    assert f'name="item_ids" value="{first_id}"' in table
    assert f'name="item_ids" value="{second_id}"' in table
    assert f'name="item_ids" value="{nested_id}"' not in table
    token = csrf_of(client, "/pricing/items")
    moved = client.post("/pricing/items/move", data={
        "csrf_token": token, "item_ids": [str(first_id), str(second_id)],
        "target_department_id": str(target.id), "target_category_id": str(destination.id),
    })
    assert moved.status_code == 303
    db.expire_all()
    assert {(db.get(PricingItem, entry_id).department_id, db.get(PricingItem, entry_id).category_id) for entry_id in (first_id, second_id)} == {(target.id, destination.id)}
    assert (db.get(PricingItem, nested_id).department_id, db.get(PricingItem, nested_id).category_id) == (1, child_id)
    assert db.get(PricingItemCategory, source_id) is not None


def test_folder_delete_removes_descendants_and_obeys_item_choice(client, db):
    untouched_root = PricingItemCategory(name="Untouched", department_id=1)
    deleted_sub = PricingItemCategory(name="Delete this subfolder", department_id=1, parent=untouched_root)
    untouched_peer = PricingItemCategory(name="Keep this sibling", department_id=1, parent=untouched_root)
    keep_root = PricingItemCategory(name="Keep Items", department_id=1)
    keep_child = PricingItemCategory(name="Keep Child", department_id=1, parent=keep_root)
    keep_item = PricingItem(department_id=1, category=keep_child, name="Preserved item", model="P", unit_price=Decimal("10"))
    delete_root = PricingItemCategory(name="Delete Items", department_id=1)
    delete_child = PricingItemCategory(name="Delete Child", department_id=1, parent=delete_root)
    delete_item = PricingItem(department_id=1, category=delete_child, name="Deleted item", model="D", unit_price=Decimal("20"))
    db.add_all([untouched_root, keep_root, delete_root])
    db.commit()
    untouched_root_id, deleted_sub_id, untouched_peer_id = untouched_root.id, deleted_sub.id, untouched_peer.id
    keep_root_id, keep_child_id, keep_item_id = keep_root.id, keep_child.id, keep_item.id
    delete_root_id, delete_child_id, delete_item_id = delete_root.id, delete_child.id, delete_item.id

    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/categories/manage")
    assert client.post(f"/pricing/categories/{deleted_sub_id}/delete", data={
        "csrf_token": token, "delete_items": "no",
    }).status_code == 303
    db.expire_all()
    assert db.get(PricingItemCategory, untouched_root_id) is not None
    assert db.get(PricingItemCategory, untouched_peer_id) is not None
    assert db.get(PricingItemCategory, deleted_sub_id) is None
    assert client.post(f"/pricing/categories/{keep_root_id}/delete", data={
        "csrf_token": token, "delete_items": "no",
    }).status_code == 303
    db.expire_all()
    assert db.get(PricingItemCategory, keep_root_id) is None
    assert db.get(PricingItemCategory, keep_child_id) is None
    assert db.get(PricingItem, keep_item_id).category_id is None
    assert client.post(f"/pricing/categories/{delete_root_id}/delete", data={
        "csrf_token": token, "delete_items": "yes",
    }).status_code == 303
    db.expire_all()
    assert db.get(PricingItemCategory, delete_root_id) is None
    assert db.get(PricingItemCategory, delete_child_id) is None
    assert db.get(PricingItem, delete_item_id) is None


def test_folder_move_rejects_cycles_and_name_conflicts_without_partial_changes(client, db):
    root = PricingItemCategory(name="Cameras", department_id=1)
    child = PricingItemCategory(name="Outdoor", department_id=1, parent=root)
    destination = PricingItemCategory(name="Security", department_id=1)
    same_name = PricingItemCategory(name="Cameras", department_id=1, parent=destination)
    item = PricingItem(department_id=1, category=child, name="Camera", model="C1", unit_price=Decimal("10"))
    db.add_all([root, destination])
    db.commit()
    root_id, child_id, item_id = root.id, child.id, item.id
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/categories/manage")
    for target_id in (child_id, destination.id, "invalid"):
        response = client.post("/pricing/categories/move", data={
            "csrf_token": token, "category_ids": str(root_id),
            "target_department_id": "1", "target_category_id": str(target_id),
            "move_items": "no",
        })
        assert response.status_code == 303
        db.expire_all()
        assert db.get(PricingItemCategory, root_id).parent_id is None
        assert db.get(PricingItemCategory, child_id).parent_id == root_id
        assert db.get(PricingItem, item_id).category_id == child_id


def test_bulk_item_move_rejects_destination_name_conflict(client, db):
    target = _add_department(db)
    source = PricingItemCategory(name="Cameras", department_id=1)
    destination = PricingItemCategory(name="Equipment", department_id=target.id)
    item = PricingItem(department_id=1, category=source, name="Camera", model="C1", unit_price=Decimal("10"))
    duplicate = PricingItem(department_id=target.id, category=destination, name="camera", model="c1", unit_price=Decimal("20"))
    db.add_all([source, destination])
    db.commit()
    source_id, item_id = source.id, item.id
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items")
    invalid_target = client.post("/pricing/items/move", data={
        "csrf_token": token, "item_ids": str(item_id),
        "target_department_id": str(target.id), "target_category_id": "invalid",
    })
    assert invalid_target.status_code == 303
    response = client.post("/pricing/items/move", data={
        "csrf_token": token, "item_ids": str(item_id),
        "target_department_id": str(target.id), "target_category_id": str(destination.id),
    })
    assert response.status_code == 303
    db.expire_all()
    assert db.get(PricingItem, item_id).department_id == 1
    assert db.get(PricingItem, item_id).category_id == source_id


def test_non_admin_cannot_move_folders_or_items_between_departments(client, db):
    target = _add_department(db)
    source = PricingItemCategory(name="Cameras", department_id=1)
    destination = PricingItemCategory(name="Equipment", department_id=target.id)
    item = PricingItem(department_id=1, category=source, name="Camera", model="C1", unit_price=Decimal("10"))
    db.add_all([source, destination])
    db.commit()
    source_id, item_id = source.id, item.id
    login(client, *LEADER_A)
    token = csrf_of(client, "/pricing/categories/manage")
    page = client.get("/pricing/categories/manage")
    assert f'id="folder-destination-{destination.id}"' not in page.text
    folder_move = client.post("/pricing/categories/move", data={
        "csrf_token": token, "category_ids": str(source_id),
        "target_department_id": str(target.id), "target_category_id": str(destination.id),
        "move_items": "yes",
    })
    item_move = client.post("/pricing/items/move", data={
        "csrf_token": token, "item_ids": str(item_id),
        "target_department_id": str(target.id), "target_category_id": str(destination.id),
    })
    assert folder_move.status_code == 303 and item_move.status_code == 303
    db.expire_all()
    assert db.get(PricingItemCategory, source_id).department_id == 1
    assert db.get(PricingItem, item_id).department_id == 1


def test_category_transfer_lists_all_item_conflicts_without_moving_branch(client, db):
    target = _add_department(db)
    root = PricingItemCategory(name="Security", department_id=1)
    child = PricingItemCategory(name="Outdoor", department_id=1, parent=root)
    first = PricingItem(
        department_id=1, category=root, name="Camera Alpha", model="A",
        unit_price=Decimal("100.00"), currency="SAR",
    )
    second = PricingItem(
        department_id=1, category=child, name="Camera Beta", model="B",
        unit_price=Decimal("200.00"), currency="SAR",
    )
    second.related_items.append(PricingRelatedItem(
        department_id=1, name="Mount", unit_price=Decimal("10.00"), currency="SAR",
    ))
    db.add_all([
        root,
        PricingItem(department_id=target.id, name="camera alpha", model="a",
                    unit_price=Decimal("50.00"), currency="SAR"),
        PricingItem(department_id=target.id, name="CAMERA BETA", model="b",
                    unit_price=Decimal("60.00"), currency="SAR"),
    ])
    db.commit()
    admin_user = db.get(User, 1)
    document = PurchaseDocument(
        department_id=1,
        document_type=PurchaseDocumentType.PURCHASE_INVOICE,
        supplier_name="Branch supplier",
        document_date=date.today(),
        uploaded_by_id=admin_user.id,
        uploaded_by_name=admin_user.full_name,
    )
    document.item_links.append(PurchaseDocumentItem(item=second, position=0))
    db.add(document)
    db.add(PricingCategoryUserAccess(category_id=child.id, user_id=2, granted_by_id=1))
    db.commit()
    root_id, child_id, first_id, second_id, document_id = root.id, child.id, first.id, second.id, document.id

    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items")
    rejected = client.post(f"/pricing/categories/{root_id}/move-department", data={
        "csrf_token": token, "target_department_id": str(target.id),
    })
    assert rejected.status_code == 303
    assert rejected.headers["location"] == "/pricing/items"
    page = client.get("/pricing/items")
    assert "Camera Alpha" in page.text and "Camera Beta" in page.text
    assert "Security / Outdoor" in page.text
    assert "Rename or move those Items" in page.text

    db.expire_all()
    assert db.get(PricingItemCategory, root_id).department_id == 1
    assert db.get(PricingItemCategory, child_id).parent_id == root_id
    assert db.get(PricingItem, first_id).department_id == 1
    assert db.get(PricingItem, second_id).department_id == 1
    assert db.get(PricingItem, second_id).related_items[0].department_id == 1
    assert db.get(PurchaseDocument, document_id).department_id == 1
    assert [link.pricing_item_id for link in db.get(PurchaseDocument, document_id).item_links] == [second_id]
    assert db.scalar(select(PricingCategoryUserAccess).where(
        PricingCategoryUserAccess.category_id == child_id,
    )) is not None


def test_category_transfer_rolls_back_a_new_destination_item_conflict(client, db, monkeypatch):
    target = _add_department(db)
    root = PricingItemCategory(name="Security", department_id=1)
    item = PricingItem(
        department_id=1, category=root, name="Race camera", model="M",
        unit_price=Decimal("100.00"), currency="SAR",
    )
    db.add(root)
    db.commit()
    root_id, item_id, target_id = root.id, item.id, target.id
    original = pricing_router._move_linked_item_resources

    def concurrent_insert(session, *, items, target_department):
        with SessionLocal() as other:
            other.add(PricingItem(
                department_id=target_id, name="Race camera", model="M",
                unit_price=Decimal("50.00"), currency="SAR",
            ))
            other.commit()
        return original(session, items=items, target_department=target_department)

    monkeypatch.setattr(pricing_router, "_move_linked_item_resources", concurrent_insert)
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items")
    rejected = client.post(f"/pricing/categories/{root_id}/move-department", data={
        "csrf_token": token, "target_department_id": str(target_id),
    })
    assert rejected.status_code == 303
    assert rejected.headers["location"] == "/pricing/items"
    assert "No data moved. Refresh and try again." in client.get("/pricing/items").text
    db.expire_all()
    assert db.get(PricingItemCategory, root_id).department_id == 1
    assert db.get(PricingItem, item_id).department_id == 1
    assert db.get(PricingItem, item_id).category_id == root_id


def test_new_categories_and_items_are_owned_by_the_active_department(client, db):
    operations = _add_department(db)
    login(client, *ADMIN)
    token = csrf_of(client, "/dashboard")
    switched = client.post(
        "/workspace",
        data={
            "department_id": str(operations.id),
            "next_url": "/pricing/items",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert switched.status_code == 303

    token = csrf_of(client, "/pricing/items")
    created_category = client.post(
        "/pricing/categories",
        data={
            "name": "Operations catalogue",
            "visibility": "department",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert created_category.status_code == 303
    category = db.scalar(
        select(PricingItemCategory)
        .where(PricingItemCategory.name == "Operations catalogue")
        .execution_options(include_all_departments=True)
    )
    assert category is not None and category.department_id == operations.id

    token = csrf_of(client, "/pricing/items")
    created_item = client.post(
        "/pricing/items",
        data={
            "name": "New Operations item",
            "model": "OPS-1",
            "unit_price": "75.00",
            "currency": "SAR",
            "category_id": str(category.id),
            "service_enabled": "1",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert created_item.status_code == 303
    item = db.scalar(
        select(PricingItem)
        .where(PricingItem.name == "New Operations item")
        .execution_options(include_all_departments=True)
    )
    assert item is not None
    assert item.department_id == operations.id
    assert item.category_id == category.id

    token = csrf_of(client, "/dashboard")
    client.post(
        "/workspace",
        data={"department_id": "1", "next_url": "/pricing/items", "csrf_token": token},
        follow_redirects=False,
    )
    general_page = client.get("/pricing/items?category=uncategorized")
    assert "New Operations item" not in general_page.text


def test_item_move_refuses_to_split_a_shared_purchase_document(client, db):
    operations = _add_department(db)
    admin = db.query(User).filter(User.username == ADMIN[0]).one()
    first = PricingItem(
        department_id=1,
        name="Shared document item A",
        model="A",
        unit_price=Decimal("10.00"),
        currency="SAR",
    )
    second = PricingItem(
        department_id=1,
        name="Shared document item B",
        model="B",
        unit_price=Decimal("20.00"),
        currency="SAR",
    )
    document = PurchaseDocument(
        department_id=1,
        document_type=PurchaseDocumentType.PURCHASE_INVOICE,
        supplier_name="Shared supplier",
        document_date=date.today(),
        uploaded_by_id=admin.id,
        uploaded_by_name=admin.full_name,
    )
    document.item_links.extend([
        PurchaseDocumentItem(item=first, position=0),
        PurchaseDocumentItem(item=second, position=1),
    ])
    db.add(document)
    db.commit()
    first_id = first.id

    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items?category=uncategorized")
    item_page = client.get("/pricing/items?category=uncategorized")
    edit_action = f'action="/pricing/items/{first_id}/edit"'
    edit_start = item_page.text.index(edit_action)
    edit_end = item_page.text.index("</form>", edit_start)
    assert 'name="target_department_id"' not in item_page.text[edit_start:edit_end]
    assert f'action="/pricing/items/{first_id}/move-department"' in item_page.text

    refused = client.post(
        f"/pricing/items/{first_id}/move-department",
        data={"target_department_id": str(operations.id), "csrf_token": token},
        follow_redirects=False,
    )
    assert refused.status_code == 303
    assert refused.headers["location"] == "/pricing/items"

    db.expire_all()
    unchanged = db.scalar(
        select(PricingItem)
        .where(PricingItem.id == first_id)
        .execution_options(include_all_departments=True)
    )
    assert unchanged is not None and unchanged.department_id == 1


def test_project_team_access_can_cross_department_boundaries(db):
    operations = _add_department(db)
    user = db.query(User).filter(User.username == LEADER_B[0]).one()
    db.add(UserDepartment(user_id=user.id, department_id=operations.id))
    db.flush()
    membership = db.get(ProjectTeamMember, (3, user.id))
    membership.department_id = operations.id
    membership.can_view_records = True
    membership.can_view_reports = True
    db.commit()
    user._permission_scopes = {
        "records": AccessScope.SELECTED,
        "reports": AccessScope.SELECTED,
    }
    db.info["department_id"] = operations.id

    assert project_access_allowed(db, user, 3, capability="can_view_records") is True
    assert project_access_allowed(db, user, 3, capability="can_view_reports") is True


def test_task_assignment_creates_notification_and_assignee_can_complete(client, db):
    login(client, *LEADER_A)
    token = csrf_of(client, "/tasks/new")
    created = client.post(
        "/tasks",
        data={
            "title": "Inspect gate controller",
            "description": "Confirm wiring and firmware.",
            "assigned_to_id": "3",
            "project_id": "1",
            "priority": "important",
            "due_at": "",
            "csrf_token": token,
        },
    )
    assert created.status_code == 303
    task = db.query(WorkTask).filter(WorkTask.title == "Inspect gate controller").one()
    notification = db.query(UserNotification).filter(UserNotification.task_id == task.id).one()
    assert notification.user_id == 3
    assert notification.is_read is False

    logout(client)
    login(client, *LEADER_B)
    detail = client.get(f"/tasks/{task.id}")
    assert detail.status_code == 200
    assert "Inspect gate controller" in detail.text
    token = csrf_of(client, f"/tasks/{task.id}")
    updated = client.post(
        f"/tasks/{task.id}/status",
        data={"status_value": "completed", "csrf_token": token},
    )
    assert updated.status_code == 303
    db.refresh(task)
    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at is not None


def test_task_manager_can_reassign_task_and_new_assignee_is_notified(client, db):
    login(client, *LEADER_A)
    token = csrf_of(client, "/tasks/new")
    created = client.post(
        "/tasks",
        data={
            "title": "Review solar controller",
            "description": "Initial assignment.",
            "assigned_to_id": "3",
            "project_id": "1",
            "priority": "normal",
            "due_at": "",
            "csrf_token": token,
        },
    )
    assert created.status_code == 303
    task = db.query(WorkTask).filter(WorkTask.title == "Review solar controller").one()

    token = csrf_of(client, f"/tasks/{task.id}")
    reassigned = client.post(
        f"/tasks/{task.id}/assignment",
        data={
            "title": "Review solar controller and wiring",
            "description": "Updated assignment.",
            "assigned_to_id": "2",
            "project_id": "1",
            "priority": "important",
            "due_at": "2026-09-01T14:30",
            "csrf_token": token,
        },
    )
    assert reassigned.status_code == 303
    db.refresh(task)
    assert task.assigned_to_id == 2
    assert task.assigned_to_name == "Leader One"
    assert task.title == "Review solar controller and wiring"
    assert task.priority.value == "important"
    assert task.due_at is not None
    notification = (
        db.query(UserNotification)
        .filter(
            UserNotification.task_id == task.id,
            UserNotification.kind == "task_reassigned",
        )
        .one()
    )
    assert notification.user_id == 2
    assert notification.is_read is False


def test_administrator_can_switch_to_any_active_department(client, db):
    operations = _add_department(db)
    login(client, *ADMIN)
    token = csrf_of(client, "/dashboard")
    switched = client.post(
        "/workspace",
        data={
            "department_id": str(operations.id),
            "next_url": "/dashboard",
            "csrf_token": token,
        },
    )
    assert switched.status_code == 303


def test_project_team_assignment_notifies_user_and_writes_detailed_audit(client, db):
    existing = db.get(ProjectTeamMember, (1, 3))
    db.delete(existing)
    db.commit()

    login(client, *ADMIN)
    token = csrf_of(client, "/projects?project_id=1")
    saved = client.post(
        "/projects/1/team",
        data={
            "membership": "3:1",
            "project_role": "Site engineer",
            "can_create_records": "1",
            "can_view_quotations": "1",
            "can_manage_tasks": "1",
            "csrf_token": token,
        },
    )
    assert saved.status_code == 303
    db.expire_all()
    membership = db.get(ProjectTeamMember, (1, 3))
    assert membership is not None
    assert membership.project_role == "Site engineer"
    notification = (
        db.query(UserNotification)
        .filter(
            UserNotification.user_id == 3,
            UserNotification.kind == "project_team_added",
        )
        .one()
    )
    assert notification.target_url == "/projects?project_id=1"
    audit = (
        db.query(AuditEvent)
        .filter(AuditEvent.action == "project_team_member_added")
        .one()
    )
    assert audit.entity_id == "1:3"
    assert "Site engineer" in audit.changes_json


def test_project_access_moves_to_new_primary_department(client, db):
    operations = _add_department(db)
    user = db.query(User).filter(User.username == LEADER_B[0]).one()
    db.add(UserDepartment(user_id=user.id, department_id=operations.id))
    db.commit()

    login(client, *ADMIN)
    token = csrf_of(client, f"/users/{user.id}/access")
    response = client.post(
        f"/users/{user.id}/access",
        data={
            "department_id": str(operations.id),
            "primary_department_id": str(operations.id),
            "csrf_token": token,
        },
    )
    assert response.status_code == 303
    db.expire_all()
    assert db.get(UserDepartment, (user.id, 1)) is None
    new_membership = db.get(UserDepartment, (user.id, operations.id))
    assert new_membership is not None
    assert new_membership.is_primary is True
    project_membership = db.get(ProjectTeamMember, (1, user.id))
    assert project_membership is not None
    assert project_membership.department_id == operations.id


def test_user_cannot_leave_department_with_an_active_assigned_task(client, db):
    operations = _add_department(db)
    user = db.query(User).filter(User.username == LEADER_B[0]).one()
    db.add(UserDepartment(user_id=user.id, department_id=operations.id))
    db.add(
        WorkTask(
            department_id=operations.id,
            task_number="TSK-2026-00999",
            title="Finish the Operations handover",
            status=TaskStatus.IN_PROGRESS,
            assigned_to_id=user.id,
            assigned_to_name=user.full_name,
            created_by_id=1,
            created_by_name="Administrator",
        )
    )
    db.commit()

    login(client, *ADMIN)
    token = csrf_of(client, f"/users/{user.id}/access")
    response = client.post(
        f"/users/{user.id}/access",
        data={
            "department_id": "1",
            "primary_department_id": "1",
            "csrf_token": token,
        },
    )
    assert response.status_code == 303
    db.expire_all()
    assert db.get(UserDepartment, (user.id, operations.id)) is not None
    page = client.get(response.headers["location"])
    assert "Reassign or close the user&#39;s active Tasks" in page.text


def test_single_selected_department_becomes_primary_automatically(client, db):
    operations = _add_department(db, name="GPS", code="GPS")
    user = db.query(User).filter(User.username == LEADER_A[0]).one()
    db.add(UserDepartment(user_id=user.id, department_id=operations.id))
    db.commit()

    login(client, *ADMIN)
    token = csrf_of(client, f"/users/{user.id}/access")
    response = client.post(
        f"/users/{user.id}/access",
        data={
            "department_id": str(operations.id),
            # Browser may still submit the former primary while it is being unchecked.
            "primary_department_id": "1",
            "csrf_token": token,
        },
    )
    assert response.status_code == 303
    db.expire_all()
    assert db.get(UserDepartment, (user.id, 1)) is None
    membership = db.get(UserDepartment, (user.id, operations.id))
    assert membership is not None
    assert membership.is_primary is True


def test_user_roles_page_saves_warehouses_and_basic_edit_does_not_clear_them(client, db):
    user = db.query(User).filter(User.username == LEADER_A[0]).one()
    warehouse = StoreWarehouse(
        department_id=1,
        name="Roles page branch warehouse",
        warehouse_type=StoreWarehouseType.BRANCH,
        location="Riyadh",
    )
    db.add(warehouse)
    db.commit()

    login(client, *ADMIN)
    token = csrf_of(client, f"/users/{user.id}/access")
    response = client.post(
        f"/users/{user.id}/access",
        data={
            "department_id": "1",
            "primary_department_id": "1",
            "warehouse:1": str(warehouse.id),
            "csrf_token": token,
        },
    )
    assert response.status_code == 303
    assert db.get(StoreUserWarehouse, (user.id, warehouse.id)) is not None

    token = csrf_of(client, "/users")
    edited = client.post(
        f"/users/{user.id}/edit",
        data={
            "full_name": user.full_name,
            "username": user.username,
            "email": user.email or "",
            "phone": user.phone or "",
            "role": user.role.value,
            "csrf_token": token,
        },
    )
    assert edited.status_code == 303
    assert db.get(StoreUserWarehouse, (user.id, warehouse.id)) is not None
