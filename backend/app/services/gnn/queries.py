from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company, RiskScore

REAL_INPUT_BASIS = "observed_real_network_experimental"


def require_company(db: Session, company_id: UUID, real_only: bool = False) -> Company:
    company = db.get(Company, company_id)
    if company is None or (real_only and company.is_synthetic):
        raise HTTPException(404, "Company not found")
    return company


def latest_scores_query(real_only: bool = False):
    ranked = select(
        RiskScore.company_id,
        RiskScore.score,
        func.row_number()
        .over(
            partition_by=RiskScore.company_id,
            order_by=(RiskScore.computed_at.desc(), RiskScore.id.desc()),
        )
        .label("position"),
    )
    if real_only:
        ranked = ranked.where(RiskScore.input_basis == REAL_INPUT_BASIS)
    sub = ranked.subquery()
    return select(sub.c.company_id, sub.c.score).where(sub.c.position == 1).subquery()


def risk_history(
    db: Session, company_id: UUID, since: datetime | None = None, real_only: bool = False
) -> list[RiskScore]:
    query = select(RiskScore).where(RiskScore.company_id == company_id)
    if real_only:
        query = query.where(RiskScore.input_basis == REAL_INPUT_BASIS)
    if since is not None:
        query = query.where(RiskScore.computed_at >= since)
    return list(
        db.scalars(query.order_by(RiskScore.computed_at.desc(), RiskScore.id.desc()).limit(100))
    )
