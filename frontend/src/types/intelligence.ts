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
  provenance?: "synthetic" | "sec_filing" | "public_source";
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
  input_basis?: "synthetic_scenario" | "observed_signals_experimental" | "observed_real_network_experimental";
  evidence_count?: number;
}
export interface RiskResponse {
  company_id: string;
  latest: RiskObservation | null;
  history: RiskObservation[];
}

export interface Page<T> { items: T[]; total: number; page: number; page_size: number; }
export interface Signal {
  id: string; company_id: string | null; location_id?: string | null; source_type: string; title: string; source_url: string | null;
  severity_score: number | null; extracted_data: { event_type?: string; relevance?: number; text_scope?: string; origin?: string; summary?: string; interpretation?: string; [key: string]: unknown };
  observed_at: string; ingested_at: string;
}
export interface Relationship {
  id: string; supplier_id: string; supplier_name: string; customer_id: string; customer_name: string;
  source_signal_id: string | null; source_url: string | null; relationship_type: string;
  criticality: number; confidence: number; evidence: string;
  status: "pending" | "approved" | "rejected"; provenance: "sec_filing" | "synthetic" | "public_source";
}
export interface IngestionRun {
  id: string; status: "running" | "success" | "partial" | "failed"; tickers: string[];
  started_at: string; finished_at: string | null;
  summary: { operation?: string; observations?: number; filings_processed?: number; news_processed?: number;
    inference?: { status: string; reason?: string } };
  errors: { ticker?: string; location?: string; source: string; message: string }[];
}

export interface Location {
  id: string; slug: string; name: string; kind: string; latitude: number; longitude: number; radius_km: number;
  details: { source_url: string; coordinate_basis: string; notes: string; checked_at: string };
  companies: { id: string; name: string; relationship: string; source_url: string }[];
}
export interface DisruptionCase {
  id: string; company_id: string; title: string; summary: string; event_start: string; event_end: string | null;
  published_at: string; checked_at: string; reported_status: string;
  display_status: "historical" | "ongoing_as_reported" | "current_status_unverified"; source_url: string;
}
export interface SourceStatus { source_type: string; configured: boolean; latest_observed_at: string | null; note: string; }
