import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../api/client";

type Metric = { n: number; positives: number; f1: number; roc_auc: number | null; brier: number };
type Model = { id: string; architecture: string; is_active: boolean; trained_at: string;
  selection_blocked: string | null; metrics: { ablation: string; seed: number; test: Metric; validation: Metric } };
type Coverage = { real_companies: number; companies_with_recent_news: number;
  approved_relationship_evidence: number; snapshot_count: number; latest_snapshot_at: string | null;
  latest_snapshot_id: string | null; feature_coverage: Record<string, number>;
  sources: { source: string; records: number; latest_observed_at: string; latest_ingested_at: string; stale: boolean }[];
  limitations: string[] };
const base = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");

export default function ModelsPanel() {
  const client = useQueryClient();
  const models = useQuery({ queryKey: ["models"], queryFn: ({ signal }) => request<{items: Model[]}>("/models", signal) });
  const coverage = useQuery({ queryKey: ["coverage"], queryFn: ({ signal }) => request<Coverage>("/coverage", signal) });
  const select = useMutation({ mutationFn: async (id: string) => {
    const response = await fetch(`${base}/models/${id}/activate`, {method: "POST"});
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new Error(error?.error?.message || error?.detail || "Model selection failed");
    }
  }, onSuccess: () => { for (const key of ["models", "risk", "companies", "graph"]) void client.invalidateQueries({queryKey: [key]}); } });
  return <section className="panel research-panel">
    <h2>Models & data coverage</h2>
    <p>Use these signals to guide research. Model scores are experimental indices. Historical validation and calibration remain required before beta decision use.</p>
    {(models.isPending || coverage.isPending) && <p role="status">Loading research status…</p>}
    {[models.error, coverage.error, select.error].filter(Boolean).map((e, i) => <p role="alert" key={i}>{e?.message}</p>)}
    {coverage.data && <>
      <div className="coverage-grid">
        <div><strong>{coverage.data.real_companies}</strong><span>Real companies</span></div>
        <div><strong>{coverage.data.companies_with_recent_news}</strong><span>With news in 30 days</span></div>
        <div><strong>{coverage.data.approved_relationship_evidence}</strong><span>Approved relationship evidence</span></div>
        <div><strong>{coverage.data.snapshot_count}</strong><span>Recorded snapshots</span></div>
      </div>
      <p>Last snapshot: {coverage.data.latest_snapshot_at ? new Date(coverage.data.latest_snapshot_at).toLocaleString() : "Not recorded"}</p>
      {coverage.data.latest_snapshot_id && <details><summary>Snapshot reference</summary><code>{coverage.data.latest_snapshot_id}</code></details>}
      <div className="table-scroll"><table><thead><tr><th>Source</th><th>Records</th><th>Latest observation</th><th>Latest ingestion</th><th>Freshness</th></tr></thead>
        <tbody>{coverage.data.sources.map(s => <tr key={s.source}><td>{s.source}</td><td>{s.records}</td>
          <td>{new Date(s.latest_observed_at).toLocaleDateString()}</td><td>{new Date(s.latest_ingested_at).toLocaleDateString()}</td><td>{s.stale ? "Stale" : "Within source window"}</td></tr>)}</tbody></table></div>
      <p>Companies with usable features: {Object.entries(coverage.data.feature_coverage).map(([s,n]) => `${s}: ${n}`).join(" · ")}</p>
      <ul>{coverage.data.limitations.map(text => <li key={text}>{text}</li>)}</ul>
    </>}
    <h3>Real-data model versions</h3>
    {models.data?.items.length === 0 && <p>No models trained on reviewed real outcomes yet. Continue collecting daily snapshots and verified outcomes. Companies remain unscored until an eligible model is selected.</p>}
    {!!models.data?.items.length && <div className="table-scroll"><table><thead><tr><th>Architecture</th><th>Variant</th><th>Validation Brier ↓</th><th>Test F1</th><th>Test AUC</th><th>Test labels</th><th>Selection</th></tr></thead>
      <tbody>{models.data.items.map(m => <tr key={m.id}><td>{m.architecture}<small className="basis-count">{m.id.slice(0,8)} · seed {m.metrics.seed}</small></td><td>{m.metrics.ablation}</td>
        <td>{m.metrics.validation.brier.toFixed(3)}</td><td>{m.metrics.test.f1.toFixed(3)}</td><td>{m.metrics.test.roc_auc?.toFixed(3) ?? "Undefined"}</td><td>{m.metrics.test.n}</td>
        <td>{m.is_active ? "Active" : <button disabled={!!m.selection_blocked || select.isPending} title={m.selection_blocked || "Select for next inference run"} onClick={() => select.mutate(m.id)}>Select model</button>}
          {m.selection_blocked && <small className="basis-count">{m.selection_blocked}</small>}</td></tr>)}</tbody></table></div>}
    <p>Choose models using validation results. The held-out test is a final assessment, not a tuning target. Selection takes effect on the next scoring run.</p>
  </section>;
}

type ContextItem = { id: string; title: string; url: string; topic: string; observed_at: string; source_country: string | null; query_saturated: boolean };
export function ContextPanel() {
  const [topic, setTopic] = useState("");
  const [page, setPage] = useState(1);
  const context = useQuery({queryKey: ["context", topic, page], queryFn: ({signal}) => request<{items: ContextItem[]; total: number}>(`/context?${new URLSearchParams({topic, page: String(page), page_size: "20"})}`, signal)});
  return <section className="panel research-panel"><h2>Geopolitical context</h2>
    <p>Reported developments around trade routes, energy, sanctions and critical materials. Inclusion does not establish disruption or exposure for a particular company.</p>
    <label>Topic <select value={topic} onChange={e => {setTopic(e.target.value); setPage(1);}}>
      <option value="">All topics</option>{["red-sea", "taiwan-strait", "hormuz", "panama-canal", "black-sea", "export-controls", "critical-minerals", "sanctions"].map(t => <option key={t}>{t}</option>)}</select></label>
    {context.isPending && <p role="status">Loading reports…</p>}
    {context.error && <p role="alert">{context.error.message}</p>}
    {context.data?.total === 0 && <p>No topic reports imported yet. Source failures and missing coverage are visible in ingestion status.</p>}
    {context.data?.items.map(item => <article className="context-item" key={item.id}>
      <small>{item.topic} · Discovered {new Date(item.observed_at).toLocaleString()} · {item.source_country || "Publisher country unknown"}</small>
      <p>{/^https?:\/\//i.test(item.url) ? <a href={item.url} target="_blank" rel="noreferrer">{item.title} ↗</a> : item.title}</p>
      {item.query_saturated && <small>Search window reached its result limit; coverage is incomplete.</small>}
    </article>)}
    <div className="pagination"><button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} · {context.data?.total ?? 0} reports</span><button disabled={!context.data || page * 20 >= context.data.total} onClick={() => setPage(page + 1)}>Next</button></div>
  </section>;
}
