import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import NetworkGraph from "../components/NetworkGraph";
import EvidencePanel, { IngestionStatus } from "../components/EvidencePanel";
import ObservationPanel, { CasePanel } from "../components/ObservationPanel";
import RiskBadge from "../components/RiskBadge";

export default function Dashboard() {
  const [tab, setTab] = useState<"network" | "signals">("network");
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [industry, setIndustry] = useState("");
  const [page, setPage] = useState(1);
  const [depth, setDepth] = useState(3);
  const [direction, setDirection] = useState("upstream");
  const [riskSort, setRiskSort] = useState(false);
  const companies = useQuery({
    queryKey: ["companies", search, industry, page],
    queryFn: ({ signal }) => api.companies(search, industry, page, signal),
    retry: false,
  });
  const selected = params.get("company") || companies.data?.items.find(c => c.is_synthetic === false)?.id || "";
  const selectCompany = (id: string) => setParams({ company: id });
  const graph = useQuery({
    queryKey: ["graph", selected, depth, direction],
    enabled: !!selected,
    queryFn: ({ signal }) => api.graph(selected, depth, direction, signal),
    retry: false,
  });
  const risk = useQuery({
    queryKey: ["risk", selected],
    enabled: !!selected,
    queryFn: ({ signal }) => api.risk(selected, signal),
    retry: false,
  });
  const selectedNode = graph.data?.nodes.find((node) => node.id === selected);
  const rows = [...(companies.data?.items || [])].filter(c => c.is_synthetic === false);
  if (riskSort)
    rows.sort((a, b) => (b.risk_score ?? -1) - (a.risk_score ?? -1));
  const refresh = () => {
    for (const key of ["signals", "relationships", "ingestion-runs", "locations", "location-signals", "cases", "source-status"]) void queryClient.invalidateQueries({queryKey: [key]});
    void companies.refetch();
    if (selected) {
      void graph.refetch();
      void risk.refetch();
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/dashboard">
          <span className="brand-mark">C</span>cascadence
          <span className="brand-dot">.</span>
        </a>
        <div className="sidebar-caption">SUPPLY NETWORK INTELLIGENCE</div>
        <a className="nav-active" href="/dashboard">
          ◈ &nbsp; Network overview
        </a>
        <div className="sidebar-note">
          <span className="status-dot" /> Phase 3 · Research prototype
          <p>A working foundation for understanding supply-chain exposure.</p>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>Supply network / Evidence explorer</span>
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
            API reference ↗
          </a>
        </header>
        <section className="page-heading">
          <div>
            <div className="eyebrow">NETWORK OVERVIEW</div>
            <h1>
              See the connections.
              <br />
              <span>Understand the exposure.</span>
            </h1>
            <p>
              Explore suppliers, follow dependencies, and inspect
              model-generated risk.
            </p>
          </div>
          <button className="refresh" onClick={refresh}>
            ↻ Refresh data
          </button>
        </section>
        <div className="demo-banner">
          <strong>Real companies · Sourced relationships</strong>
          <span>
            GCN remains trained on simulated shocks · Scores are
            not calibrated probabilities.
          </span>
        </div>
        <section className="stats" aria-label="Network summary">
          <article>
            <span>Companies matching filters</span>
            <strong>{companies.data?.total ?? "—"}</strong>
            <small>Across all result pages</small>
          </article>
          <article>
            <span>Visible network</span>
            <strong>
              {graph.data?.nodes.length ?? "—"}
              <em> companies</em>
            </strong>
            <small>
              {graph.data?.links.length ?? "—"} supplier relationships
            </small>
          </article>
          <article>
            <span>Selected company risk</span>
            <strong>
              {risk.data?.latest?.score.toFixed(2) ?? "—"}
              <em> / 1.00</em>
            </strong>
            <small>Experimental risk index</small>
          </article>
        </section>
        <div className="view-tabs" role="tablist" aria-label="Explorer views">
          <button id="network-tab" role="tab" aria-selected={tab === "network"} aria-controls="network-view" onClick={() => setTab("network")}>Network</button>
          <button id="signals-tab" role="tab" aria-selected={tab === "signals"} aria-controls="signals-view" onClick={() => setTab("signals")}>Signals</button>
        </div>
        <div className="content-grid">
          <section className="panel companies-panel">
            <div className="panel-title">
              <h2>Company directory</h2>
              <span>{companies.data?.total ?? 0}</span>
            </div>
            <label className="search-label">
              <span className="sr-only">Search companies</span>
              <input
                placeholder="Search companies…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
              />
            </label>
            <div className="directory-controls">
              <label>
                <span className="sr-only">Industry</span>
                <select
                  value={industry}
                  onChange={(e) => {
                    setIndustry(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">All industries</option>
                  {[
                    "Electronics",
                    "Manufacturing",
                    "Logistics",
                    "Materials",
                    "Energy",
                  ].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <button onClick={() => setRiskSort(!riskSort)}>
                {riskSort ? "Risk ↓ (page)" : "Name ↑"}
              </button>
            </div>
            {companies.isPending && (
              <p className="panel-message" role="status">
                Loading companies…
              </p>
            )}
            {companies.isError && (
              <p className="panel-message error" role="alert">
                {companies.error.message}. Check the backend, then refresh.
              </p>
            )}
            {companies.data?.total === 0 && (
              <p className="panel-message">
                {search || industry
                  ? "No companies match these filters."
                  : "No real companies yet. Import sources or install the real-company catalog to begin."}
              </p>
            )}
            <div className="company-list">
              {rows.map((company) => (
                <button
                  className={`company-row ${selected === company.id ? "selected" : ""}`}
                  key={company.id}
                  onClick={() => selectCompany(company.id)}
                  aria-pressed={selected === company.id}
                >
                  <span>
                    <strong>{company.name}</strong>
                    <small>
                      {company.industry || "Industry unknown"} · Real company
                    </small>
                  </span>
                  <RiskBadge score={company.risk_score} />
                </button>
              ))}
            </div>
            <div className="pagination">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
                ← Previous
              </button>
              <span>Page {page}</span>
              <button
                disabled={!companies.data || page * 12 >= companies.data.total}
                onClick={() => setPage(page + 1)}
              >
                Next →
              </button>
            </div>
          </section>
          {tab === "network" ? <section id="network-view" role="tabpanel" aria-labelledby="network-tab" className="panel network-panel">
            <div className="panel-title">
              <div>
                <div className="eyebrow">SUPPLIER EXPLORER</div>
                <h2>
                  {selectedNode?.name ||
                    (selected ? "Selected company" : "Supply network")}
                </h2>
              </div>
              <RiskBadge score={risk.data?.latest?.score ?? null} />
            </div>
            <div className="network-controls">
              <label>
                Depth{" "}
                <select
                  value={depth}
                  onChange={(e) => setDepth(Number(e.target.value))}
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
              <label>
                Direction{" "}
                <select
                  value={direction}
                  onChange={(e) => setDirection(e.target.value)}
                >
                  <option value="upstream">Upstream suppliers</option>
                  <option value="downstream">Downstream customers</option>
                  <option value="both">Both directions</option>
                </select>
              </label>
            </div>
            {!selected && (
              <p className="panel-message">
                Select a company to explore its network.
              </p>
            )}
            {selected && graph.isPending && (
              <p className="panel-message" role="status">
                Loading supply network…
              </p>
            )}
            {graph.isError && (
              <p className="panel-message error" role="alert">
                {graph.error.message}
              </p>
            )}
            {graph.data && (
              <NetworkGraph
                {...graph.data}
                centerNodeId={selected}
                onNodeClick={selectCompany}
              />
            )}
            <div className="legend">
              <span>
                <i className="low-dot" /> Low &lt; 0.40
              </span>
              <span>
                <i className="moderate-dot" /> Moderate 0.40–0.69
              </span>
              <span>
                <i className="high-dot" /> High ≥ 0.70
              </span>
              <span>
                <i className="unscored-dot" /> Unscored
              </span>
            </div>
          </section> : <div id="signals-view" role="tabpanel" aria-labelledby="signals-tab"><ObservationPanel /></div>}
        </div>
        {tab === "signals" && selected && <><CasePanel key={`cases-${selected}`} companyId={selected} /><EvidencePanel key={selected} companyId={selected} /></>}
        <IngestionStatus />
        {tab === "network" && <section className="panel history-panel">
          <div className="panel-title">
            <div>
              <div className="eyebrow">MODEL OBSERVATIONS</div>
              <h2>Risk history</h2>
            </div>
            <span>Latest 100 runs</span>
          </div>
          {risk.isError && (
            <p className="panel-message error" role="alert">
              {risk.error.message}
            </p>
          )}
          {selected && risk.isPending && (
            <p className="panel-message" role="status">
              Loading risk history…
            </p>
          )}
          {risk.data?.latest == null && !risk.isPending && !risk.isError && (
            <p className="panel-message">
              No scores have been computed for this company.
            </p>
          )}
          {risk.data?.history.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Computed at</th>
                    <th>Risk index</th>
                    <th>Input basis</th>
                    <th>Model version</th>
                    <th>Graph snapshot</th>
                  </tr>
                </thead>
                <tbody>
                  {risk.data.history.map((item) => (
                    <tr key={item.id}>
                      <td>{new Date(item.computed_at).toLocaleString()}</td>
                      <td>
                        <div className="score-track">
                          <i style={{ width: `${item.score * 100}%` }} />
                        </div>
                        {item.score.toFixed(3)}
                      </td>
                      <td>
                        {"Real-network news · experimental"}
                        <small className="basis-count">{item.evidence_count ?? 0} direct evidence records</small>
                      </td>
                      <td>
                        <code title={item.model_version_id}>
                          {item.model_version_id.slice(0, 8)}
                        </code>
                      </td>
                      <td>
                        <code title={item.graph_snapshot_id}>
                          {item.graph_snapshot_id.slice(0, 12)}
                        </code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>}
        <footer>
          CASCADENCE / PHASE 03{" "}
          <span>
            Source evidence. Visible provenance. Transparent limits.
          </span>
        </footer>
      </main>
    </div>
  );
}
