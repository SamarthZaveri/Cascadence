from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company, RiskScore


def require_company(db: Session, company_id: UUID) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


def latest_scores_query():
    ranked = select(
        RiskScore.company_id,
        RiskScore.score,
        func.row_number()
        .over(
            partition_by=RiskScore.company_id,
            order_by=(RiskScore.computed_at.desc(), RiskScore.id.desc()),
        )
        .label("position"),
    ).subquery()
    return select(ranked.c.company_id, ranked.c.score).where(ranked.c.position == 1).subquery()


def risk_history(db: Session, company_id: UUID, since: datetime | None = None) -> list[RiskScore]:
    query = select(RiskScore).where(RiskScore.company_id == company_id)
    if since is not None:
        query = query.where(RiskScore.computed_at >= since)
    return list(
        db.scalars(query.order_by(RiskScore.computed_at.desc(), RiskScore.id.desc()).limit(100))
    )
