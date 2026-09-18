from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.models import Company
from app.schemas.intelligence import CompanyPage, CompanySummary
from app.services.gnn.queries import latest_scores_query

router = APIRouter()


@router.get("", response_model=CompanyPage)
def list_companies(
    industry: str | None = None,
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    workspace_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> CompanyPage:
    if workspace_id is not None:
        raise HTTPException(422, "Workspace scoping is not implemented in Phase 1")
    filters = []
    if industry:
        filters.append(Company.industry == industry)
    if search:
        filters.append(
            or_(
                Company.name.icontains(search, autoescape=True),
                Company.ticker.icontains(search, autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(Company).where(*filters)) or 0
    latest = latest_scores_query()
    rows = db.execute(
        select(Company, latest.c.score)
        .outerjoin(latest, Company.id == latest.c.company_id)
        .where(*filters)
        .order_by(Company.name, Company.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        CompanySummary(
            id=c.id,
            name=c.name,
            ticker=c.ticker,
            industry=c.industry,
            hq_country=c.hq_country,
            is_synthetic=c.is_synthetic,
            risk_score=score,
        )
        for c, score in rows
    ]
    return CompanyPage(items=items, total=total, page=page, page_size=page_size)
