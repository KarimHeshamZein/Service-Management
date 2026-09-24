"""Stable Department permission catalogue and role-template presets."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PermissionDefinition:
    key: str
    group: str
    label: str
    description: str


def _permission(group: str, name: str, label: str, description: str) -> PermissionDefinition:
    return PermissionDefinition(f"{group}.{name}", group, label, description)


PERMISSIONS: tuple[PermissionDefinition, ...] = (
    _permission("dashboard", "view", "View dashboard", "See Department dashboard totals and shortcuts."),
    _permission("projects", "view", "View assigned Projects", "See Projects where the user is an explicit team member."),
    _permission("projects", "create", "Create Projects", "Create a Project and choose its cross-Department team."),
    _permission("projects", "edit", "Edit Projects", "Edit an assigned Project and its hierarchy."),
    _permission("projects", "manage_team", "Manage Project team", "Add or remove Project members across Departments."),
    _permission("records", "view", "View service records", "View records belonging to assigned Projects."),
    _permission("records", "create_installation", "Create installations", "Create installation records for assigned Projects."),
    _permission("records", "create_preventive", "Create preventive maintenance", "Create preventive-maintenance records."),
    _permission("records", "create_maintenance", "Create maintenance", "Create general-maintenance records."),
    _permission("records", "edit", "Edit service records", "Edit records within assigned Projects."),
    _permission("records", "delete", "Delete service records", "Delete records within assigned Projects."),
    _permission("reports", "view", "View reports", "View generated reports for assigned Projects."),
    _permission("reports", "create", "Create reports", "Generate reports from accessible records."),
    _permission("reports", "download", "Download reports", "Preview and download customer PDFs."),
    _permission("reports", "delete", "Delete reports", "Delete generated reports."),
    _permission("pricing_items", "view", "View item library", "View permitted Department categories and items."),
    _permission("pricing_items", "manage", "Manage item library", "Create and edit Department categories and items."),
    _permission("quotations", "view", "View quotations", "View Department quotations and permitted Project quotations."),
    _permission("quotations", "create", "Create quotations", "Create quotations from the Department library."),
    _permission("quotations", "edit", "Edit quotations", "Edit Department quotations."),
    _permission("quotations", "delete", "Delete quotations", "Delete one or more Department quotations."),
    _permission("purchase_documents", "view", "View purchase documents", "View supplier quotations and invoices."),
    _permission("purchase_documents", "manage", "Manage purchase documents", "Upload, edit and delete supplier documents."),
    _permission("technical_documents", "view", "View technical information", "View data sheets and recommendations."),
    _permission("technical_documents", "manage", "Manage technical information", "Upload data sheets and edit recommendations."),
    _permission("wiring", "view", "View wiring diagrams", "View Department wiring diagrams."),
    _permission("wiring", "manage", "Manage wiring diagrams", "Create folders and upload or remove diagrams."),
    _permission("store", "view", "View warehouses", "View assigned Department warehouses and custody."),
    _permission("store", "receive", "Receive stock", "Record purchases and stock receipts."),
    _permission("store", "issue", "Issue stock", "Issue stock to free-text Projects."),
    _permission("store", "transfer", "Transfer between warehouses", "Transfer stock between permitted warehouses."),
    _permission("store", "custody", "Manage technician custody", "Issue to and return stock from technicians."),
    _permission("store", "manage", "Manage warehouse setup", "Manage items, warehouses and adjustments."),
    _permission("store", "reports", "View warehouse reports", "View stock, movement and custody reports."),
    _permission("product_evaluations", "view", "View product evaluations", "View Department evaluation requests and reports."),
    _permission("product_evaluations", "create", "Request product evaluation", "Submit a device purchase and evaluation request."),
    _permission("product_evaluations", "approve", "Approve evaluation requests", "Approve, reject and confirm device receipt."),
    _permission("product_evaluations", "assign", "Assign evaluators", "Schedule an evaluation for a Department user."),
    _permission("product_evaluations", "execute", "Perform evaluations", "Complete assigned testing sessions."),
    _permission("tasks", "view", "View tasks", "View assigned and Department-manageable tasks."),
    _permission("tasks", "create", "Create tasks", "Create a task for a Department member."),
    _permission("tasks", "assign", "Assign tasks", "Assign and reassign Department tasks."),
    _permission("tasks", "manage", "Manage Department tasks", "Update any task in the Department."),
)

PERMISSION_BY_KEY = {permission.key: permission for permission in PERMISSIONS}
PERMISSION_GROUPS = tuple(dict.fromkeys(permission.group for permission in PERMISSIONS))

# View scopes are saved directly for each user/Department.  Project-linked
# modules share one selected Project list, but remain independently visible.
SCOPED_PERMISSION_GROUPS: frozenset[str] = frozenset(
    {
        "projects",
        "records",
        "reports",
        "pricing_items",
        "quotations",
        "purchase_documents",
        "technical_documents",
        "wiring",
        "store",
        "product_evaluations",
        "tasks",
    }
)

PROJECT_SCOPED_GROUPS: frozenset[str] = frozenset(
    {"projects", "records", "reports", "quotations", "tasks"}
)

SCOPE_CHOICES: tuple[tuple[str, str], ...] = (
    ("none", "No access"),
    ("own", "Own work only"),
    ("selected", "Selected resources"),
    ("department", "All Department data"),
)

# Creation/management always implies that the user can reopen their own work.
# Data scopes still decide whether work created by somebody else is visible.
PERMISSION_IMPLICATIONS: dict[str, frozenset[str]] = {
    "projects.view": frozenset({"projects.create", "projects.edit", "projects.manage_team"}),
    "records.view": frozenset({
        "records.create_installation", "records.create_preventive",
        "records.create_maintenance", "records.edit", "records.delete",
    }),
    "reports.view": frozenset({"reports.create", "reports.download", "reports.delete"}),
    "pricing_items.view": frozenset({"pricing_items.manage"}),
    "quotations.view": frozenset({"quotations.create", "quotations.edit", "quotations.delete"}),
    "purchase_documents.view": frozenset({"purchase_documents.manage"}),
    "technical_documents.view": frozenset({"technical_documents.manage"}),
    "wiring.view": frozenset({"wiring.manage"}),
    "store.view": frozenset({
        "store.receive", "store.issue", "store.transfer", "store.custody",
        "store.manage", "store.reports",
    }),
    "product_evaluations.view": frozenset({
        "product_evaluations.create", "product_evaluations.approve",
        "product_evaluations.assign", "product_evaluations.execute",
    }),
    "tasks.view": frozenset({"tasks.create", "tasks.assign", "tasks.manage"}),
}

ARABIC_PERMISSION_GROUPS = {
    "dashboard": "لوحة التحكم", "projects": "المشاريع", "records": "سجلات الخدمة",
    "reports": "التقارير", "pricing_items": "مكتبة الأصناف", "quotations": "عروض الأسعار",
    "purchase_documents": "مستندات الشراء", "technical_documents": "المعلومات التقنية",
    "wiring": "مخططات التوصيل", "store": "المستودعات",
    "product_evaluations": "تقييم المنتجات", "tasks": "المهام",
}

ARABIC_PERMISSION_TEXT: dict[str, tuple[str, str]] = {
    "dashboard.view": ("عرض لوحة التحكم", "عرض إجماليات القسم والاختصارات."),
    "projects.view": ("عرض المشاريع المسندة", "عرض المشاريع التي يكون المستخدم عضوًا صريحًا في فريقها."),
    "projects.create": ("إنشاء مشاريع", "إنشاء مشروع واختيار فريقه من الأقسام المختلفة."),
    "projects.edit": ("تعديل المشاريع", "تعديل المشروع المسند وهيكله."),
    "projects.manage_team": ("إدارة فريق المشروع", "إضافة أو إزالة أعضاء فريق المشروع من الأقسام المختلفة."),
    "records.view": ("عرض سجلات الخدمة", "عرض سجلات المشاريع المسندة."),
    "records.create_installation": ("إنشاء تركيبات", "إنشاء سجلات تركيب للمشاريع المسندة."),
    "records.create_preventive": ("إنشاء صيانة دورية", "إنشاء سجلات الصيانة الدورية."),
    "records.create_maintenance": ("إنشاء صيانة", "إنشاء سجلات الصيانة العامة."),
    "records.edit": ("تعديل سجلات الخدمة", "تعديل السجلات داخل المشاريع المسندة."),
    "records.delete": ("حذف سجلات الخدمة", "حذف السجلات داخل المشاريع المسندة."),
    "reports.view": ("عرض التقارير", "عرض التقارير المنشأة للمشاريع المسندة."),
    "reports.create": ("إنشاء تقارير", "إنشاء تقارير من السجلات المتاحة."),
    "reports.download": ("تنزيل التقارير", "معاينة وتنزيل تقارير العملاء بصيغة PDF."),
    "reports.delete": ("حذف التقارير", "حذف التقارير المنشأة."),
    "pricing_items.view": ("عرض مكتبة الأصناف", "عرض كاتجوريز وأصناف القسم المسموح بها."),
    "pricing_items.manage": ("إدارة مكتبة الأصناف", "إنشاء وتعديل كاتجوريز وأصناف القسم."),
    "quotations.view": ("عرض عروض الأسعار", "عرض عروض أسعار القسم والمشاريع المسموح بها."),
    "quotations.create": ("إنشاء عروض أسعار", "إنشاء عروض أسعار من مكتبة القسم."),
    "quotations.edit": ("تعديل عروض الأسعار", "تعديل عروض أسعار القسم."),
    "quotations.delete": ("حذف عروض الأسعار", "حذف عرض سعر واحد أو عدة عروض."),
    "purchase_documents.view": ("عرض مستندات الشراء", "عرض عروض الموردين وفواتير الشراء."),
    "purchase_documents.manage": ("إدارة مستندات الشراء", "رفع وتعديل وحذف مستندات الموردين."),
    "technical_documents.view": ("عرض المعلومات التقنية", "عرض ملفات الداتا شيت والتوصيات."),
    "technical_documents.manage": ("إدارة المعلومات التقنية", "رفع الداتا شيت وتعديل التوصيات."),
    "wiring.view": ("عرض مخططات التوصيل", "عرض مخططات توصيل القسم."),
    "wiring.manage": ("إدارة مخططات التوصيل", "إنشاء الفولدرات ورفع أو إزالة المخططات."),
    "store.view": ("عرض المستودعات", "عرض مستودعات القسم المسندة والعهدة."),
    "store.receive": ("استلام مخزون", "تسجيل المشتريات واستلام المخزون."),
    "store.issue": ("صرف مخزون", "صرف المخزون لمشاريع مكتوبة بحرية."),
    "store.transfer": ("التحويل بين المستودعات", "تحويل المخزون بين المستودعات المسموح بها."),
    "store.custody": ("إدارة عهد الفنيين", "صرف المخزون للفنيين وإعادته منهم."),
    "store.manage": ("إدارة إعدادات المستودع", "إدارة الأصناف والمستودعات والتسويات."),
    "store.reports": ("عرض تقارير المستودع", "عرض تقارير المخزون والحركات والعهد."),
    "product_evaluations.view": ("عرض تقييمات المنتجات", "عرض طلبات وتقارير تقييمات القسم."),
    "product_evaluations.create": ("طلب تقييم منتج", "إرسال طلب شراء جهاز وتقييمه."),
    "product_evaluations.approve": ("اعتماد طلبات التقييم", "اعتماد أو رفض الطلب وتأكيد استلام الجهاز."),
    "product_evaluations.assign": ("تعيين المقيمين", "جدولة تقييم لمستخدم داخل القسم."),
    "product_evaluations.execute": ("تنفيذ التقييمات", "إكمال جلسات الاختبار المسندة."),
    "tasks.view": ("عرض المهام", "عرض المهام المسندة والمهام المسموح بإدارتها داخل القسم."),
    "tasks.create": ("إنشاء مهام", "إنشاء مهمة لعضو في القسم."),
    "tasks.assign": ("توجيه المهام", "تعيين المهام وإعادة توجيهها."),
    "tasks.manage": ("إدارة مهام القسم", "تحديث أي مهمة داخل القسم."),
}

TEMPLATE_PERMISSIONS: dict[str, frozenset[str]] = {
    "technical": frozenset(
        permission.key
        for permission in PERMISSIONS
        if permission.key in {
            "dashboard.view", "projects.view", "records.view", "records.create_installation",
            "records.create_preventive", "records.create_maintenance", "records.edit",
            "reports.view", "reports.create", "reports.download", "tasks.view",
        }
    ),
    "sales": frozenset(
        {
            "dashboard.view", "projects.view", "pricing_items.view", "quotations.view",
            "quotations.create", "quotations.edit", "purchase_documents.view",
            "technical_documents.view", "tasks.view", "product_evaluations.view",
            "product_evaluations.create",
        }
    ),
    "maintenance": frozenset(
        {
            "dashboard.view", "projects.view", "records.view", "records.create_preventive",
            "records.create_maintenance", "records.edit", "reports.view", "reports.create",
            "reports.download", "tasks.view",
        }
    ),
    "testing": frozenset(
        {
            "dashboard.view", "projects.view", "product_evaluations.view",
            "product_evaluations.create", "product_evaluations.execute", "tasks.view",
        }
    ),
    "warehouse": frozenset(
        {
            "dashboard.view", "store.view", "store.receive", "store.issue", "store.transfer",
            "store.custody", "store.reports", "tasks.view",
        }
    ),
    "custom": frozenset(),
}


def grouped_permissions(language: str = "en") -> dict[str, tuple[PermissionDefinition, ...]]:
    localized = PERMISSIONS
    if language == "ar":
        localized = tuple(
            replace(
                permission,
                label=ARABIC_PERMISSION_TEXT[permission.key][0],
                description=ARABIC_PERMISSION_TEXT[permission.key][1],
            )
            for permission in PERMISSIONS
        )
    return {
        (ARABIC_PERMISSION_GROUPS.get(group, group) if language == "ar" else group):
        tuple(permission for permission in localized if permission.group == group)
        for group in PERMISSION_GROUPS
    }
