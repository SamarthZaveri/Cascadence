import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, imageUrl } from "../api/client";
import type { Signal, Location } from "../types/intelligence";
import { Pager, SourceLink } from "./EvidencePanel";
const labels: Record<string, string> = {satellite: "Sentinel-2", viirs: "VIIRS", ais: "AIS"};
const date = (v: unknown) => typeof v === "string" ? v.slice(0,10) : "Unknown";
const object = (v: unknown): Record<string, unknown> => v && typeof v === "object" ? v as Record<string, unknown> : {};
const number = (v: unknown, digits=2) => typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "Unavailable";
function Photo({id, role, at}: {id: string; role: "before" | "after"; at: string}) {
  const [failed, setFailed] = useState(false);
  return <figure>{failed ? <p>Image unavailable. Refresh the source cache.</p> : <img src={imageUrl(id,role)} alt={`${role} observation dated ${at}`} loading="lazy" onError={() => setFailed(true)}/>}<figcaption>{role} · {at}</figcaption></figure>;
}
export function ObservationCard({item}: {item: Signal}) {
  const data = item.extracted_data, provenance = object(data.provenance), images = object(data.images);
  const before = object(provenance.before), after = object(provenance.after);
  const daily = Array.isArray(data.daily) ? data.daily.map(object) : [];
  return <article className="observation-card"><div className="evidence-meta"><span className="source-tag">{labels[item.source_type]}</span><time>{date(item.observed_at)}</time></div>
    <h3>{item.title}</h3><p>{data.interpretation}</p>
    {item.source_type === "satellite" && <p>Surface change: {number(data.surface_change,3)} · Common usable fraction: {number(data.common_valid_fraction)}</p>}
    {item.source_type === "viirs" && <p>Mean radiance: {number(data.before_mean_radiance)} → {number(data.after_mean_radiance)} · Relative decrease: {number(data.relative_radiance_decrease)}{data.relative_radiance_decrease === null ? " (baseline too low)" : ""}</p>}
    {item.source_type === "ais" && <><p>Observed vessels: {number(data.target_vessels,0)} · Baseline median: {number(data.baseline_median_vessels)} · Activity ratio: {number(data.vessel_activity_ratio)}×</p>
      <p>{provenance.sample_is_historical ? "Historical NOAA sample · January 2024 · inner harbor only" : "User-supplied AIS export"}</p>
      <div className="table-scroll"><table><caption>Received vessel activity by UTC day</caption><thead><tr><th>Date</th><th>Vessels</th><th>Positions</th><th>Observed span</th></tr></thead><tbody>{daily.map(d => <tr key={String(d.date)}><td>{String(d.date)}</td><td>{number(d.vessels,0)}</td><td>{number(d.positions,0)}</td><td>{number(d.observed_span_hours)} h</td></tr>)}</tbody></table></div><p>{String(data.coverage_note || "")}</p></>}
    {!!images.before && !!images.after && <div className="observation-images"><Photo key={`${item.id}-before`} id={item.id} role="before" at={date(before.observed_at || before.month)}/><Photo key={`${item.id}-after`} id={item.id} role="after" at={date(after.observed_at || after.month)}/></div>}
    <SourceLink url={item.source_url}>Original data source</SourceLink><details><summary>Provenance and quality</summary><pre>{JSON.stringify({observed_at:item.observed_at, ingested_at:item.ingested_at, ...data},null,2)}</pre></details>
  </article>;
}
function LocationObservations({location}: {location: Location}) {
  const [source,setSource] = useState(""), [page,setPage] = useState(1);
  const query = useQuery({queryKey:["location-signals",location.id,source,page],queryFn:({signal})=>api.locationSignals(location.id,source,page,signal),retry:false});
  return <><p>{location.details.notes}</p><small>{location.latitude}, {location.longitude} · {location.radius_km} km radius · {location.details.coordinate_basis}</small><p><SourceLink url={location.details.source_url}>Location context</SourceLink></p>
    {!!location.companies.length && <p>{location.companies.map(c => `${c.name}: ${c.relationship}`).join(" · ")}</p>}
    <label>Source <select value={source} onChange={e=>{setSource(e.target.value);setPage(1);}}><option value="">All sensor sources</option>{Object.entries(labels).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
    {query.isPending && <p role="status">Loading observations…</p>}{query.isError && <p role="alert">{query.error.message}</p>}
    {query.data?.total === 0 && <p>No usable observations imported. Missing data does not mean normal operations.</p>}
    {query.data?.items.map(item=><ObservationCard key={item.id} item={item}/>)}{query.data && <Pager page={page} total={query.data.total} change={setPage}/>}</>;
}
export default function ObservationPanel() {
  const [selected,setSelected] = useState("");
  const locations = useQuery({queryKey:["locations"],queryFn:({signal})=>api.locations(signal),retry:false});
  const sources = useQuery({queryKey:["source-status"],queryFn:({signal})=>api.sources(signal),retry:false});
  const items=locations.data?.items || [], active=items.find(l=>l.id===selected) || items.find(l=>l.slug==="port-los-angeles") || items[0];
  return <section className="panel observation-panel" aria-label="Location observations"><div className="panel-title"><div><div className="eyebrow">REAL WORLD OBSERVATIONS</div><h2>Location signals</h2></div><span>{locations.data?.total ?? 0} areas</span></div>
    <p>Imagery and vessel activity describe a location. They do not prove company disruption or feed the current risk model.</p>
    <div className="source-status-grid">{sources.data?.items.map(s=><article key={s.source_type}><strong>{labels[s.source_type]}</strong><p>{s.configured ? "Configured" : s.source_type === "ais" ? "Download needed" : "Credentials needed"}</p><small>{s.note}</small><p>Latest: {s.latest_observed_at ? date(s.latest_observed_at) : "None"}</p></article>)}</div>
    {sources.isError && <p role="alert">Source status unavailable: {sources.error.message}</p>}{locations.isPending && <p role="status">Loading monitoring areas…</p>}{locations.isError && <p role="alert">{locations.error.message}</p>}{locations.data?.total===0 && <p>No monitoring areas installed.</p>}
    {!!items.length && <label>Monitoring location <select value={active?.id || ""} onChange={e=>setSelected(e.target.value)}>{items.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>}
    {active && <LocationObservations key={active.id} location={active}/>}</section>;
}
export function CasePanel({companyId}: {companyId: string}) {
  const query=useQuery({queryKey:["cases",companyId],queryFn:({signal})=>api.cases(companyId,signal),retry:false});
  return <section className="panel case-panel" aria-label="Documented company cases"><div className="panel-title"><h2>Documented company cases</h2></div><p>Dated source evidence. Ongoing reports become unverified after 30 days without a newer report.</p>
    {query.isPending && <p role="status">Loading documented cases…</p>}{query.isError && <p role="alert">{query.error.message}</p>}{query.data?.total===0 && <p>No curated disruption case attached. Supplier inclusion alone does not imply disruption.</p>}
    {query.data?.items.map(c=><article className="evidence-item" key={c.id}><div className="evidence-meta"><span className="source-tag">{c.display_status.replaceAll("_"," ")}</span><span>{c.event_start}{c.event_end ? ` to ${c.event_end}` : " · end date not established"}</span></div><h3><SourceLink url={c.source_url}>{c.title}</SourceLink></h3><p>{c.summary}</p><small>Published {date(c.published_at)} · Checked {date(c.checked_at)}</small></article>)}</section>;
}
