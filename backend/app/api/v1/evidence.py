from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.postgres import get_db
from app.models import Company, IngestionRun, Signal, SupplyRelationship
from app.schemas.evidence import (
    IngestionRunItem,
    IngestionRunPage,
    RelationshipItem,
    RelationshipPage,
)
from app.services.gnn.queries import require_company

router = APIRouter()


@router.get("/relationships", response_model=RelationshipPage)
def relationships(
    company_id: UUID | None = None,
    status: Literal["pending", "approved", "rejected"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> RelationshipPage:
    filters = []
    if company_id:
        require_company(db, company_id)
        filters.append(
            or_(
                SupplyRelationship.supplier_id == company_id,
                SupplyRelationship.customer_id == company_id,
            )
        )
    if status:
        filters.append(SupplyRelationship.status == status)
    total = db.scalar(select(func.count()).select_from(SupplyRelationship).where(*filters)) or 0
    supplier, customer = aliased(Company), aliased(Company)
    rows = db.execute(
        select(SupplyRelationship, supplier.name, customer.name, Signal.raw_payload)
        .join(supplier, SupplyRelationship.supplier_id == supplier.id)
        .join(customer, SupplyRelationship.customer_id == customer.id)
        .outerjoin(Signal, SupplyRelationship.source_signal_id == Signal.id)
        .where(*filters)
        .order_by(SupplyRelationship.created_at.desc(), SupplyRelationship.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return RelationshipPage(
        items=[
            RelationshipItem(
                id=e.id,
                supplier_id=e.supplier_id,
                supplier_name=sn,
                customer_id=e.customer_id,
                customer_name=cn,
                source_signal_id=e.source_signal_id,
                source_url=(raw or {}).get("url"),
                relationship_type=e.relationship_type,
                criticality=e.criticality,
                confidence=e.confidence,
                evidence=e.evidence,
                status=e.status,
                provenance=e.provenance,
                created_at=e.created_at,
                reviewed_at=e.reviewed_at,
            )
            for e, sn, cn, raw in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/ingestion/runs", response_model=IngestionRunPage)
def ingestion_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> IngestionRunPage:
    total = db.scalar(select(func.count()).select_from(IngestionRun)) or 0
    rows = db.scalars(
        select(IngestionRun)
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return IngestionRunPage(
        items=[IngestionRunItem.model_validate(s) for s in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
