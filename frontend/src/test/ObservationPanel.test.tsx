import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import ObservationPanel, { ObservationCard } from "../components/ObservationPanel";
import { api, realGraph } from "../api/client";
import type { Signal } from "../types/intelligence";

vi.mock("../api/client", async (original) => {
  const actual = await original<typeof import("../api/client")>();
  return { ...actual, api: { ...actual.api, locations: vi.fn(), sources: vi.fn(), locationSignals: vi.fn() } };
});
afterEach(() => vi.resetAllMocks());

it("removes synthetic and unsupported relationships from a mixed graph", () => {
  const base = { risk_score: null, tier: 0 };
  const result = realGraph({
    nodes: [{ ...base, id: "real", name: "Real", is_synthetic: false }, { ...base, id: "other", name: "Other", is_synthetic: false }, { ...base, id: "fake", name: "Fake", is_synthetic: true }],
    links: [{ source: "fake", target: "real", criticality: 0.5, provenance: "synthetic" }, { source: "other", target: "real", criticality: 0.5, provenance: "public_source", evidence_ids: ["evidence"] }],
  });
  expect(result.nodes.map(n => n.id)).toEqual(["real", "other"]);
  expect(result.links).toHaveLength(1);
});

it("renders real source configuration and an honest empty state", async () => {
  vi.mocked(api.locations).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
  vi.mocked(api.sources).mockResolvedValue({ items: [{ source_type: "ais", configured: false, latest_observed_at: null, note: "Historical NOAA sample" }, { source_type: "satellite", configured: false, latest_observed_at: null, note: "Free account required" }] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><ObservationPanel /></QueryClientProvider>);
  expect(await screen.findByText("No monitoring areas installed.")).toBeInTheDocument();
  expect(await screen.findByText("Download needed")).toBeInTheDocument();
  expect(await screen.findByText("Credentials needed")).toBeInTheDocument();
});

it("shows acquisition dates, source links and unavailable images without substitutes", () => {
  const item: Signal = { id: "sample", company_id: null, location_id: "la", source_type: "satellite", title: "Surface change", source_url: "https://dataspace.copernicus.eu/", severity_score: null, observed_at: "2024-02-01T00:00:00Z", ingested_at: "2026-09-21T00:00:00Z", extracted_data: { interpretation: "Location change only", surface_change: 0.2, common_valid_fraction: 0.8, provenance: { before: { observed_at: "2024-01-01" }, after: { observed_at: "2024-02-01" } }, images: { before: { sha256: "abc" }, after: { sha256: "def" } } } };
  render(<ObservationCard item={item} />);
  expect(screen.getByRole("link", { name: /Original data source/ })).toHaveAttribute("href", item.source_url);
  fireEvent.error(screen.getByRole("img", { name: "before observation dated 2024-01-01" }));
  expect(screen.getByText("Image unavailable. Refresh the source cache.")).toBeInTheDocument();
});
