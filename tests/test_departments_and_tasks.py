"""Focused coverage for Department isolation, overrides and task delivery."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.access_control import permission_allowed, project_access_allowed
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
    individual_folder = PricingItemCategory(name="Individual access", department_id=1)
    db.add_all([selected, individual_folder])
    db.flush()
    category_item = PricingItem(
        department_id=1, category_id=selected.id, name="Allowed category camera",
        model="CAT-1", unit_price=Decimal("10"), currency="SAR",
    )
    direct_item = PricingItem(
        department_id=1, category_id=individual_folder.id, name="Allowed direct camera",
        model="DIRECT-1", unit_price=Decimal("20"), currency="SAR",
    )
    hidden_item = PricingItem(
        department_id=1, category_id=individual_folder.id, name="Hidden peer camera",
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
    category_page = client.get(f"/pricing/items?category={selected.id}")
    assert category_page.status_code == 200
    assert "Allowed category camera" in category_page.text
    direct_page = client.get(f"/pricing/items?category={individual_folder.id}")
    assert direct_page.status_code == 200
    assert "Allowed direct camera" in direct_page.text
    assert "Hidden peer camera" not in direct_page.text


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
        category=child,
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
        .where(PricingItemCategory.id.in_({root_id, child_id}))
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
