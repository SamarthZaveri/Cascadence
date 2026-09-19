from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.models import Company, Signal
from app.schemas.evidence import CompanyDetail, SignalItem, SignalPage
from app.schemas.intelligence import CompanyPage, CompanySummary
from app.services.gnn.queries import latest_scores_query, require_company

router = APIRouter()


@router.get("", response_model=CompanyPage)
def list_companies(
    industry: str | None = None,
    is_synthetic: bool | None = None,
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    workspace_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> CompanyPage:
    if workspace_id is not None:
        raise HTTPException(422, "Workspace scoping is not implemented yet")
    filters = []
    if is_synthetic is not None:
        filters.append(Company.is_synthetic == is_synthetic)
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


@router.get("/{company_id}", response_model=CompanyDetail)
def company_detail(company_id: UUID, db: Session = Depends(get_db)) -> CompanyDetail:
    c = require_company(db, company_id)
    latest = latest_scores_query()
    score = db.scalar(select(latest.c.score).where(latest.c.company_id == company_id))
    return CompanyDetail(
        id=c.id,
        name=c.name,
        ticker=c.ticker,
        industry=c.industry,
        hq_country=c.hq_country,
        is_synthetic=c.is_synthetic,
        sec_cik=c.sec_cik,
        risk_score=score,
    )


@router.get("/{company_id}/signals", response_model=SignalPage)
def company_signals(
    company_id: UUID,
    source_type: str | None = Query(None, pattern="^(sec_filing|news|satellite|ais|viirs)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SignalPage:
    require_company(db, company_id)
    filters = [Signal.company_id == company_id]
    if source_type:
        filters.append(Signal.source_type == source_type)
    total = db.scalar(select(func.count()).select_from(Signal).where(*filters)) or 0
    rows = db.scalars(
        select(Signal)
        .where(*filters)
        .order_by(Signal.observed_at.desc(), Signal.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return SignalPage(
        items=[
            SignalItem(
                id=s.id,
                company_id=s.company_id,
                source_type=s.source_type,
                title=s.raw_payload.get("title", s.source_type),
                source_url=s.raw_payload.get("url"),
                extracted_data=s.extracted_data,
                severity_score=s.severity_score,
                observed_at=s.observed_at,
                ingested_at=s.ingested_at,
            )
            for s in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
