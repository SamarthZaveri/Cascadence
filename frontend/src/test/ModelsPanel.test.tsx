import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import ModelsPanel, { ContextPanel } from "../components/ModelsPanel";
import { request } from "../api/client";

vi.mock("../api/client", () => ({request: vi.fn()}));
afterEach(() => {vi.resetAllMocks(); vi.unstubAllGlobals();});
const coverage = {real_companies: 100, companies_with_recent_news: 20,
  approved_relationship_evidence: 4, snapshot_count: 2, latest_snapshot_at: null,
  feature_coverage: {news: 20}, sources: [], limitations: ["Missing observations are unknown"]};
function show(component: React.ReactNode) {
  const client = new QueryClient({defaultOptions: {queries: {retry: false, gcTime: 0}}});
  render(<QueryClientProvider client={client}>{component}</QueryClientProvider>);
}

it("shows real coverage and an explicit untrained state", async () => {
  vi.mocked(request).mockImplementation(async path => path === "/models" ? {items: []} : coverage);
  show(<ModelsPanel />);
  expect(await screen.findByText(/No models trained on reviewed real outcomes/)).toBeInTheDocument();
  expect(screen.getByText("100")).toBeInTheDocument();
  expect(screen.getByText("Missing observations are unknown")).toBeInTheDocument();
});

it("selects an eligible model explicitly and blocks an ineligible version", async () => {
  const metric = {n: 40, positives: 10, f1: .5, roc_auc: null, brier: .2};
  const models = [{id: "eligible", architecture: "gat", is_active: false,
    metrics: {seed: 42, ablation: "full", validation: metric, test: metric}, selection_blocked: null},
    {id: "blocked", architecture: "temporal", is_active: false,
      metrics: {seed: 43, ablation: "no_news", validation: metric, test: metric}, selection_blocked: "Ablations are evaluation-only"}];
  vi.mocked(request).mockImplementation(async path => path === "/models" ? {items: models} : coverage);
  const fetch = vi.fn().mockResolvedValue({ok: true});
  vi.stubGlobal("fetch", fetch);
  show(<ModelsPanel />);
  const buttons = await screen.findAllByRole("button", {name: "Select model"});
  expect(buttons[1]).toBeDisabled();
  fireEvent.click(buttons[0]);
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/models/eligible/activate", {method: "POST"}));
});

it("renders contextual reports with provenance and search-cap warning", async () => {
  vi.mocked(request).mockResolvedValue({total: 1, items: [{id: "news", title: "Shipping report",
    url: "https://publisher.example/report", topic: "red-sea", observed_at: "2026-09-20T00:00:00Z",
    source_country: "UK", query_saturated: true}]});
  show(<ContextPanel />);
  expect(await screen.findByRole("link", {name: /Shipping report/})).toHaveAttribute("href", "https://publisher.example/report");
  expect(screen.getByText(/Search window reached its result limit/)).toBeInTheDocument();
});
