// Mirrors DATA_CONTRACT.md §8; backend response models also publish these via OpenAPI.
export interface Company {
  id: string;
  name: string;
  ticker: string | null;
  industry: string | null;
  hq_country: string | null;
  is_synthetic: boolean;
  risk_score: number | null;
}
export interface CompanyPage {
  items: Company[];
  total: number;
  page: number;
  page_size: number;
}
export interface GraphNode {
  id: string;
  name: string;
  risk_score: number | null;
  tier: number;
  is_synthetic?: boolean;
}
export interface GraphLink {
  source: string;
  target: string;
  criticality: number;
  provenance?: "synthetic" | "sec_filing";
  evidence_ids?: string[];
  confidence?: number | null;
}
export interface GraphResponse {
  nodes: GraphNode[];
  links: GraphLink[];
}
export interface RiskObservation {
  id: string;
  score: number;
  model_version_id: string;
  computed_at: string;
  graph_snapshot_id: string;
  input_basis?: "synthetic_scenario" | "observed_signals_experimental";
  evidence_count?: number;
}
export interface RiskResponse {
  company_id: string;
  latest: RiskObservation | null;
  history: RiskObservation[];
}

export interface Page<T> { items: T[]; total: number; page: number; page_size: number; }
export interface Signal {
  id: string; company_id: string; source_type: string; title: string; source_url: string | null;
  severity_score: number | null; extracted_data: { event_type?: string; relevance?: number; text_scope?: string };
  observed_at: string; ingested_at: string;
}
export interface Relationship {
  id: string; supplier_id: string; supplier_name: string; customer_id: string; customer_name: string;
  source_signal_id: string | null; source_url: string | null; relationship_type: string;
  criticality: number; confidence: number; evidence: string;
  status: "pending" | "approved" | "rejected"; provenance: "sec_filing" | "synthetic";
}
export interface IngestionRun {
  id: string; status: "running" | "success" | "partial" | "failed"; tickers: string[];
  started_at: string; finished_at: string | null;
  summary: { filings_processed?: number; news_processed?: number;
    inference?: { status: string; reason?: string } };
  errors: { ticker: string; source: string; message: string }[];
}
