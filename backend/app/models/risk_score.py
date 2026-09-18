from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 1", name="ck_risk_score_range"),
        Index("ix_risk_company_time", "company_id", "computed_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"))
    model_version_id: Mapped[UUID] = mapped_column(ForeignKey("model_versions.id"))
    score: Mapped[float]
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    graph_snapshot_id: Mapped[str] = mapped_column(String)
