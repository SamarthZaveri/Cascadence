from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint("severity_score >= 0 AND severity_score <= 1", name="ck_signal_severity"),
        Index("ix_signal_company_time", "company_id", "observed_at"),
        Index("ix_signal_location_time", "location_id", "observed_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"))
    location_id: Mapped[UUID | None] = mapped_column(ForeignKey("monitored_locations.id"))
    source_type: Mapped[str] = mapped_column(
        Enum("sec_filing", "news", "satellite", "ais", "viirs", name="signal_source_type")
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    severity_score: Mapped[float | None]
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
