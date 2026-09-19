from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class SupplyRelationship(Base):
    __tablename__ = "supply_relationships"
    __table_args__ = (
        CheckConstraint("supplier_id <> customer_id", name="ck_supply_not_self"),
        CheckConstraint("criticality >= 0 AND criticality <= 1", name="ck_supply_criticality"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_supply_confidence"),
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_supply_status"),
        CheckConstraint("provenance IN ('sec_filing','synthetic')", name="ck_supply_provenance"),
        CheckConstraint(
            "provenance = 'synthetic' OR source_signal_id IS NOT NULL", name="ck_supply_evidence"
        ),
        Index("ix_supply_status", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"))
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"))
    source_signal_id: Mapped[UUID | None] = mapped_column(ForeignKey("signals.id"))
    relationship_type: Mapped[str]
    criticality: Mapped[float] = mapped_column(default=0.5)
    confidence: Mapped[float]
    evidence: Mapped[str] = mapped_column(Text)
    status: Mapped[str]
    provenance: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
