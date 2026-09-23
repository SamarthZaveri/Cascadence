import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function SourceLink({ url, children }: { url: string | null; children: React.ReactNode }) {
  let safe = false;
  try { const p = new URL(url || ""); safe = ["https:", "http:"].includes(p.protocol) && !p.username && !p.password; } catch { /* invalid source URL */ }
  return safe ? <a href={url!} target="_blank" rel="noopener noreferrer">{children} ↗</a> : <span>{children}</span>;
}
export function Pager({ page, total, change }: { page: number; total: number; change: (n: number) => void }) {
  return <div className="pagination"><button disabled={page === 1} onClick={() => change(page - 1)}>Previous</button>
    <span>Page {page} · {total} records</span><button disabled={page * 10 >= total} onClick={() => change(page + 1)}>Next</button></div>;
}
export default function EvidencePanel({ companyId }: { companyId: string }) {
  const [signalPage, setSignalPage] = useState(1);
  const [relationshipPage, setRelationshipPage] = useState(1);
  const signals = useQuery({ queryKey: ["signals", companyId, signalPage], queryFn: ({ signal }) => api.signals(companyId, signalPage, signal), retry: false });
  const relationships = useQuery({ queryKey: ["relationships", companyId, relationshipPage], queryFn: ({ signal }) => api.relationships(companyId, relationshipPage, signal), retry: false });
  return <div className="evidence-grid">
    <section className="panel evidence-panel" aria-label="Company signals">
      <div className="panel-title"><h2>Signals & sources</h2><span>{signals.data?.total ?? "—"}</span></div>
      <p className="evidence-note">News is classified from headlines. Severity is a heuristic; it is not a verified assessment of company impact.</p>
      {signals.isPending && <p role="status">Loading signals…</p>}
      {signals.isError && <p role="alert" className="error">{signals.error.message}</p>}
      {signals.data?.total === 0 && <p>No source evidence has been imported for this company.</p>}
      {signals.data?.items.map(item => <article className="evidence-item" key={item.id}>
        <div className="evidence-meta"><span className="source-tag">{item.extracted_data.origin?.startsWith("curated") ? "Curated public source" : item.source_type === "sec_filing" ? "SEC filing" : "GDELT news"}</span><time dateTime={item.observed_at}>{new Date(item.observed_at).toLocaleDateString()}</time></div>
        <h3><SourceLink url={item.source_url}>{item.title}</SourceLink></h3>
        <p>{item.extracted_data.summary}</p><p>{item.extracted_data.event_type?.replaceAll("_", " ") || "Relationship evidence"} · {item.severity_score === null ? "Severity not assigned" : `Heuristic severity ${item.severity_score.toFixed(2)}`}</p>
        <small>{item.extracted_data.origin?.startsWith("curated") ? "Dated source; excluded from risk scoring." : item.source_type === "news" ? "Date shown is first discovery by GDELT, not necessarily publication." : "Annual filings may describe historical relationships."}</small>
      </article>)}
      {signals.data && <Pager page={signalPage} total={signals.data.total} change={setSignalPage} />}
    </section>
    <section className="panel evidence-panel" aria-label="Relationship evidence">
      <div className="panel-title"><h2>Relationship evidence</h2><span>{relationships.data?.total ?? "—"}</span></div>
      <p className="evidence-note">Extracted candidates need review. Only approved relationships appear in the graph; extraction confidence is not verification.</p>
      {relationships.isPending && <p role="status">Loading relationships…</p>}
      {relationships.isError && <p role="alert" className="error">{relationships.error.message}</p>}
      {relationships.data?.total === 0 && <p>No relationship candidates have been recorded for this company.</p>}
      {relationships.data?.items.map(item => <article className="evidence-item" key={item.id}>
        <div className="evidence-meta"><span className={`source-tag ${item.provenance === "synthetic" ? "synthetic-tag" : ""}`}>{item.provenance === "public_source" ? "Curated public source" : "SEC filing"}</span><span>{item.status}</span></div>
        <h3>{item.supplier_name} → {item.customer_name}</h3><blockquote>{item.evidence}</blockquote>
        <p>Evidence confidence {item.confidence.toFixed(2)} · Criticality {item.criticality.toFixed(2)} (placeholder)</p>
        <SourceLink url={item.source_url}>Source evidence</SourceLink>
        <details><summary>Record reference</summary><code>{item.id}</code></details>
      </article>)}
      {relationships.data && <Pager page={relationshipPage} total={relationships.data.total} change={setRelationshipPage} />}
    </section>
  </div>;
}
export function IngestionStatus() {
  const runs = useQuery({ queryKey: ["ingestion-runs"], queryFn: ({ signal }) => api.ingestionRuns(signal), retry: false, refetchInterval: 30000 });
  return <section className="panel ingestion-panel" aria-label="Import activity"><div className="panel-title"><h2>Import activity</h2><span>Latest 5 runs</span></div>
    {runs.isPending && <p role="status">Loading imports…</p>}
    {runs.isError && <p role="alert" className="error">{runs.error.message}</p>}
    {runs.data?.total === 0 && <p>No imports have run yet.</p>}
    {runs.data?.items.map(run => <article className="evidence-item" key={run.id}>
      <div className="evidence-meta"><strong>{run.tickers.join(", ")}</strong><span className={`import-state ${run.status}`}>{run.status}</span><time>{new Date(run.started_at).toLocaleString()}</time></div>
      <p>{run.summary.operation ? `${run.summary.operation} · ${run.summary.observations ?? 0} observations · ` : ""}{run.summary.filings_processed ?? 0} filings · {run.summary.news_processed ?? 0} news records processed</p>
      {run.summary.inference?.reason && <small>Scoring: {run.summary.inference.reason}</small>}
      {!!run.errors.length && <details><summary>{run.errors.length} import issue(s)</summary><ul>{run.errors.map((error, i) => <li key={i}>{error.ticker || error.location || "Source"} / {error.source}: {error.message}</li>)}</ul></details>}
    </article>)}
  </section>;
}
