"""Database engine and session management."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, false, or_, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.orm import with_loader_criteria

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


def _department_owned_models():
    from .models import (
        PricingItem,
        PricingItemCategory,
        PricingQuotation,
        PricingRelatedItem,
        ProductEvaluationRequest,
        PurchaseDocument,
        StoreItem,
        StoreMovement,
        StoreWarehouse,
        TechnicalDocument,
        TechnicalRecommendation,
        WiringDiagram,
        WiringDiagramCategory,
    )

    return (
        PricingItemCategory,
        PricingItem,
        PricingRelatedItem,
        PricingQuotation,
        PurchaseDocument,
        StoreWarehouse,
        StoreItem,
        StoreMovement,
        TechnicalDocument,
        TechnicalRecommendation,
        WiringDiagramCategory,
        WiringDiagram,
        ProductEvaluationRequest,
    )


@event.listens_for(Session, "do_orm_execute")
def _scope_department_queries(execute_state) -> None:
    """Prevent accidental cross-Department reads in isolated business modules."""
    department_id = execute_state.session.info.get("department_id")
    if (
        department_id is None
        or not execute_state.is_select
        or execute_state.execution_options.get("include_all_departments")
    ):
        return
    statement = execute_state.statement
    for model in _department_owned_models():
        statement = statement.options(
            with_loader_criteria(
                model,
                model.department_id == department_id,
                include_aliases=True,
            )
        )
    if not execute_state.session.info.get("is_admin"):
        from .models import (
            ProductEvaluationRequest,
            ProductEvaluationSession,
            PricingCategoryUserAccess,
            PricingItem,
            PricingItemCategory,
            PricingItemUserAccess,
            PricingRelatedItem,
            PurchaseDocument,
            PurchaseDocumentItem,
            TechnicalDocument,
            TechnicalRecommendation,
            WiringDiagram,
        )
        user_id = execute_state.session.info.get("user_id")
        module_scopes = execute_state.session.info.get("module_scopes", {})
        category_table = PricingItemCategory.__table__
        item_table = PricingItem.__table__
        related_table = PricingRelatedItem.__table__
        pricing_scope = module_scopes.get(
            "pricing_items", "none"
        )
        granted_category_ids = select(PricingCategoryUserAccess.category_id).where(
            PricingCategoryUserAccess.user_id == user_id
        )
        granted_item_ids = select(PricingItemUserAccess.item_id).where(
            PricingItemUserAccess.user_id == user_id
        )
        directly_granted_category_ids = select(item_table.c.category_id).where(
            item_table.c.id.in_(granted_item_ids),
            item_table.c.category_id.is_not(None),
        )
        direct_parent_category_ids = select(category_table.c.parent_id).where(
            category_table.c.id.in_(directly_granted_category_ids),
            category_table.c.parent_id.is_not(None),
        )
        granted_subcategory_ids = select(category_table.c.id).where(
            category_table.c.parent_id.in_(granted_category_ids)
        )
        items_in_granted_categories = select(item_table.c.id).where(
            item_table.c.category_id.in_(granted_category_ids.union(granted_subcategory_ids))
        )
        if pricing_scope == "department":
            category_visible = PricingItemCategory.id.is_not(None)
            item_visible = PricingItem.id.is_not(None)
            related_visible = PricingRelatedItem.id.is_not(None)
            visible_item_ids = select(item_table.c.id)
            visible_related_ids = select(related_table.c.id)
        elif pricing_scope == "selected":
            category_visible = or_(
                PricingItemCategory.id.in_(granted_category_ids),
                PricingItemCategory.parent_id.in_(granted_category_ids),
                # Keep the folder path visible for an individually granted
                # Item, without exposing the folder's other Items.
                PricingItemCategory.id.in_(directly_granted_category_ids),
                PricingItemCategory.id.in_(direct_parent_category_ids),
            )
            visible_item_ids = granted_item_ids.union(items_in_granted_categories)
            item_visible = or_(
                PricingItem.id.in_(granted_item_ids),
                PricingItem.id.in_(items_in_granted_categories),
            )
            visible_related_ids = select(related_table.c.id).where(
                related_table.c.main_item_id.in_(visible_item_ids)
            )
            related_visible = PricingRelatedItem.id.in_(visible_related_ids)
        elif pricing_scope == "own":
            category_visible = PricingItemCategory.created_by_id == user_id
            item_visible = PricingItem.created_by_id == user_id
            visible_item_ids = select(item_table.c.id).where(
                item_table.c.created_by_id == user_id
            )
            visible_related_ids = select(related_table.c.id).where(
                related_table.c.main_item_id.in_(visible_item_ids)
            )
            related_visible = PricingRelatedItem.id.in_(visible_related_ids)
        else:
            category_visible = false()
            item_visible = false()
            related_visible = false()
            visible_item_ids = select(item_table.c.id).where(false())
            visible_related_ids = select(related_table.c.id).where(false())
        statement = statement.options(
            with_loader_criteria(
                PricingItemCategory,
                category_visible,
                include_aliases=True,
            ),
            with_loader_criteria(
                PricingItem,
                item_visible,
                include_aliases=True,
            ),
            with_loader_criteria(
                PricingRelatedItem,
                related_visible,
                include_aliases=True,
            ),
        )

        # Supplier and technical files inherit the selected Pricing Item list.
        # With Own scope, only files authored by this user are visible.
        for module_key, model, owner_column in (
            ("purchase_documents", PurchaseDocument, PurchaseDocument.uploaded_by_id),
            ("technical_documents", TechnicalDocument, TechnicalDocument.uploaded_by_id),
        ):
            scope = module_scopes.get(module_key, "none")
            if scope == "department":
                criterion = model.id.is_not(None)
            elif scope == "own":
                criterion = owner_column == user_id
            elif scope == "selected" and model is PurchaseDocument:
                criterion = PurchaseDocument.id.in_(
                    select(PurchaseDocumentItem.document_id).where(or_(
                        PurchaseDocumentItem.pricing_item_id.in_(visible_item_ids),
                        PurchaseDocumentItem.related_item_id.in_(visible_related_ids),
                    ))
                )
            elif scope == "selected":
                criterion = or_(
                    TechnicalDocument.pricing_item_id.in_(visible_item_ids),
                    TechnicalDocument.related_item_id.in_(visible_related_ids),
                )
            else:
                criterion = false()
            statement = statement.options(with_loader_criteria(
                model, criterion, include_aliases=True
            ))

        technical_scope = module_scopes.get("technical_documents", "none")
        if technical_scope == "department":
            recommendation_visible = TechnicalRecommendation.id.is_not(None)
        elif technical_scope == "own":
            recommendation_visible = TechnicalRecommendation.updated_by_id == user_id
        elif technical_scope == "selected":
            recommendation_visible = or_(
                TechnicalRecommendation.pricing_item_id.in_(visible_item_ids),
                TechnicalRecommendation.related_item_id.in_(visible_related_ids),
            )
        else:
            recommendation_visible = false()
        statement = statement.options(with_loader_criteria(
            TechnicalRecommendation, recommendation_visible, include_aliases=True
        ))

        wiring_scope = module_scopes.get("wiring", "none")
        wiring_visible = (
            WiringDiagram.id.is_not(None) if wiring_scope == "department"
            else WiringDiagram.uploaded_by_id == user_id
            if wiring_scope in {"own", "selected"}
            else false()
        )
        statement = statement.options(with_loader_criteria(
            WiringDiagram, wiring_visible, include_aliases=True
        ))

        evaluation_scope = module_scopes.get("product_evaluations", "none")
        own_or_assigned_evaluation = or_(
            ProductEvaluationRequest.created_by_id == user_id,
            ProductEvaluationRequest.assigned_admin_id == user_id,
            ProductEvaluationRequest.id.in_(
                select(ProductEvaluationSession.request_id).where(
                    ProductEvaluationSession.assigned_user_id == user_id
                )
            ),
        )
        evaluation_visible = (
            ProductEvaluationRequest.id.is_not(None)
            if evaluation_scope == "department"
            else own_or_assigned_evaluation
            if evaluation_scope in {"own", "selected"}
            else false()
        )
        statement = statement.options(with_loader_criteria(
            ProductEvaluationRequest, evaluation_visible, include_aliases=True
        ))
    execute_state.statement = statement


@event.listens_for(Session, "before_flush")
def _assign_department_to_new_rows(session: Session, _flush_context, _instances) -> None:
    """Stamp new isolated resources with the active workspace server-side."""
    department_id = session.info.get("department_id")
    if department_id is None:
        return
    from .models import ServiceReport

    owned_types = _department_owned_models() + (ServiceReport,)
    for row in session.new:
        if isinstance(row, owned_types) and getattr(row, "department_id", None) is None:
            row.department_id = department_id


def init_db(*, create_schema: bool = False) -> None:
    from . import models  # noqa: F401 - registers all ORM mappers

    if create_schema:
        Base.metadata.create_all(bind=engine)
        return
    # Normal startup never bypasses Alembic. It only verifies that PostgreSQL
    # is reachable; deployments must run `alembic upgrade head` first.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
