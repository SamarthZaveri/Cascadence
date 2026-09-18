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
}
export interface GraphLink {
  source: string;
  target: string;
  criticality: number;
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
}
export interface RiskResponse {
  company_id: string;
  latest: RiskObservation | null;
  history: RiskObservation[];
}
