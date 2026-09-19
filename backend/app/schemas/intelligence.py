from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanySummary(BaseModel):
    id: UUID
    name: str
    ticker: str | None
    industry: str | None
    hq_country: str | None
    is_synthetic: bool
    risk_score: float | None = Field(default=None, ge=0, le=1)


class CompanyPage(BaseModel):
    items: list[CompanySummary]
    total: int
    page: int
    page_size: int


class GraphNode(BaseModel):
    id: str
    name: str
    risk_score: float | None = Field(default=None, ge=0, le=1)
    tier: int
    is_synthetic: bool = True


class GraphLink(BaseModel):
    source: str
    target: str
    criticality: float = Field(ge=0, le=1)
    provenance: str = "synthetic"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]


class RiskObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: UUID
    score: float = Field(ge=0, le=1)
    model_version_id: UUID
    computed_at: datetime
    graph_snapshot_id: str
    input_basis: str = "synthetic_scenario"
    evidence_count: int = 0


class RiskHistory(BaseModel):
    company_id: UUID
    history: list[RiskObservation]


class RiskResponse(RiskHistory):
    latest: RiskObservation | None
