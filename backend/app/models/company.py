from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    neo4j_id: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    ticker: Mapped[str | None] = mapped_column(String)
    sec_cik: Mapped[str | None] = mapped_column(String)
    industry: Mapped[str | None] = mapped_column(String)
    hq_country: Mapped[str | None] = mapped_column(String)
    hq_lat: Mapped[float | None]
    hq_lng: Mapped[float | None]
    is_synthetic: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
