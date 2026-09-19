from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.intelligence import CompanySummary


class CompanyDetail(CompanySummary):
    sec_cik: str | None


class SignalItem(BaseModel):
    id: UUID
    company_id: UUID | None
    source_type: str
    title: str
    source_url: str | None
    extracted_data: dict[str, Any]
    severity_score: float | None
    observed_at: datetime
    ingested_at: datetime


class SignalPage(BaseModel):
    items: list[SignalItem]
    total: int
    page: int
    page_size: int


class RelationshipItem(BaseModel):
    id: UUID
    supplier_id: UUID
    supplier_name: str
    customer_id: UUID
    customer_name: str
    source_signal_id: UUID | None
    source_url: str | None
    relationship_type: str
    criticality: float
    confidence: float
    evidence: str
    status: str
    provenance: str
    created_at: datetime
    reviewed_at: datetime | None


class RelationshipPage(BaseModel):
    items: list[RelationshipItem]
    total: int
    page: int
    page_size: int


class IngestionRunItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    tickers: list[str]
    summary: dict[str, Any]
    errors: list[dict[str, Any]]


class IngestionRunPage(BaseModel):
    items: list[IngestionRunItem]
    total: int
    page: int
    page_size: int
