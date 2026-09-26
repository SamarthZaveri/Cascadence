"""Immutable input records for forward collection and reproducible model experiments."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class GraphSnapshot(Base):
    __tablename__ = "graph_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True)
    feature_schema: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
