from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class MonitoredLocation(Base):
    __tablename__ = "monitored_locations"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -80 AND 80", name="ck_location_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_location_longitude"),
        CheckConstraint("radius_km > 0 AND radius_km <= 20", name="ck_location_radius"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    kind: Mapped[str]
    latitude: Mapped[float]
    longitude: Mapped[float]
    radius_km: Mapped[float]
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)


class CompanyLocation(Base):
    __tablename__ = "company_locations"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), primary_key=True)
    location_id: Mapped[UUID] = mapped_column(
        ForeignKey("monitored_locations.id"), primary_key=True
    )
    relationship: Mapped[str]
    source_url: Mapped[str]


class DisruptionCase(Base):
    __tablename__ = "disruption_cases"
    __table_args__ = (Index("ix_case_company_date", "company_id", "event_start"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"))
    title: Mapped[str]
    summary: Mapped[str]
    event_start: Mapped[date]
    event_end: Mapped[date | None]
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reported_status: Mapped[str]
    source_url: Mapped[str]
