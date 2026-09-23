import type {CompanyPage, Page, Signal, Relationship, IngestionRun, GraphResponse, RiskResponse, Location, DisruptionCase, SourceStatus} from "../types/intelligence";
const base = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");
export const realBasis = "observed_real_network_experimental";
export const imageUrl = (id: string, role: "before" | "after") => `${base}/signals/${encodeURIComponent(id)}/images/${role}`;
export async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${base}${path}`, {signal});
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.error?.message || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}
export function realGraph(data: GraphResponse): GraphResponse {
  const nodes = data.nodes.filter(n => n.is_synthetic === false);
  const ids = new Set(nodes.map(n => n.id));
  return {nodes, links: data.links.filter(l => ids.has(l.source) && ids.has(l.target)
    && ["sec_filing", "public_source"].includes(l.provenance || "") && !!l.evidence_ids?.length)};
}
export const api = {
  companies: async (search: string, industry: string, page: number, signal?: AbortSignal) => {
    const data = await request<CompanyPage>(`/companies?${new URLSearchParams({search, industry, page: String(page), page_size: "12", is_synthetic: "false"})}`, signal);
    return {...data, items: data.items.filter(c => c.is_synthetic === false)};
  },
  signals: (id: string, page: number, signal?: AbortSignal) => request<Page<Signal>>(`/companies/${id}/signals?real_only=true&page=${page}&page_size=10`, signal),
  relationships: async (id: string, page: number, signal?: AbortSignal) => {
    const data = await request<Page<Relationship>>(`/relationships?real_only=true&company_id=${id}&page=${page}&page_size=10`, signal);
    return {...data, items: data.items.filter(r => ["sec_filing", "public_source"].includes(r.provenance) && r.source_signal_id)};
  },
  ingestionRuns: (signal?: AbortSignal) => request<Page<IngestionRun>>("/ingestion/runs?page_size=5", signal),
  graph: async (id: string, depth: number, direction: string, signal?: AbortSignal) => realGraph(await request<GraphResponse>(`/graph/${id}?real_only=true&depth=${depth}&direction=${direction}`, signal)),
  risk: async (id: string, signal?: AbortSignal): Promise<RiskResponse> => {
    const data = await request<RiskResponse>(`/risk/${id}?real_only=true`, signal);
    const history = data.history.filter(r => r.input_basis === realBasis);
    return {...data, history, latest: history[0] || null};
  },
  locations: (signal?: AbortSignal) => request<Page<Location>>("/locations?page_size=100", signal),
  cases: (id: string, signal?: AbortSignal) => request<Page<DisruptionCase>>(`/cases?company_id=${id}&page_size=100`, signal),
  locationSignals: (id: string, source: string, page: number, signal?: AbortSignal) => request<Page<Signal>>(`/locations/${id}/signals?${new URLSearchParams({...(source ? {source_type: source} : {}), page: String(page), page_size: "10"})}`, signal),
  sources: (signal?: AbortSignal) => request<{items: SourceStatus[]}>("/sources/status", signal),
};
