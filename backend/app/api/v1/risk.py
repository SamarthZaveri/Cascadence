from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.schemas.intelligence import RiskHistory, RiskObservation, RiskResponse
from app.services.gnn.queries import require_company, risk_history

router = APIRouter()


@router.get("/{company_id}", response_model=RiskResponse)
def get_risk(
    company_id: UUID, real_only: bool = False, db: Session = Depends(get_db)
) -> RiskResponse:
    require_company(db, company_id, real_only)
    history = [
        RiskObservation.model_validate(row)
        for row in risk_history(db, company_id, real_only=real_only)
    ]
    return RiskResponse(
        company_id=company_id, latest=history[0] if history else None, history=history
    )


@router.get("/{company_id}/history", response_model=RiskHistory)
def get_history(
    company_id: UUID,
    since: AwareDatetime | None = None,
    real_only: bool = False,
    db: Session = Depends(get_db),
) -> RiskHistory:
    require_company(db, company_id, real_only)
    return RiskHistory(
        company_id=company_id,
        history=[
            RiskObservation.model_validate(row)
            for row in risk_history(db, company_id, since, real_only)
        ],
    )
