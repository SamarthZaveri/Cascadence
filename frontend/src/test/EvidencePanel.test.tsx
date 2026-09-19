import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import EvidencePanel, { IngestionStatus, SourceLink } from "../components/EvidencePanel";
import { api } from "../api/client";
vi.mock("../api/client", () => ({ api: { signals: vi.fn(), relationships: vi.fn(), ingestionRuns: vi.fn() } }));
const empty = { items: [], total: 0, page: 1, page_size: 10 };
beforeEach(() => {
  vi.mocked(api.signals).mockResolvedValue(empty);
  vi.mocked(api.relationships).mockResolvedValue(empty);
  vi.mocked(api.ingestionRuns).mockResolvedValue(empty);
});
afterEach(() => vi.resetAllMocks());
function mount(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}
it("shows news provenance, unknown severity and pending evidence", async () => {
  vi.mocked(api.signals).mockResolvedValue({ ...empty, total: 1, items: [{
    id: "signal", company_id: "a", source_type: "news", title: "Example company avoids strike",
    source_url: "https://publisher.invalid/article", severity_score: null, extracted_data: { event_type: "other" },
    observed_at: "2026-09-18T00:00:00Z", ingested_at: "2026-09-18T01:00:00Z",
  }] });
  vi.mocked(api.relationships).mockResolvedValue({ ...empty, total: 1, items: [{
    id: "edge", supplier_id: "b", supplier_name: "Supplier", customer_id: "a", customer_name: "Customer",
    source_signal_id: "filing", source_url: "https://www.sec.gov/Archives/example.htm", relationship_type: "component",
    criticality: .5, confidence: .95, evidence: "We source components from Supplier.", status: "pending", provenance: "sec_filing",
  }] });
  mount(<EvidencePanel companyId="a" />);
  expect(await screen.findByText("GDELT news")).toBeInTheDocument();
  expect(screen.getByText(/Severity not assigned/)).toBeInTheDocument();
  expect(await screen.findByText("pending")).toBeInTheDocument();
  expect(screen.getByText(/Only approved relationships appear/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /avoids strike/ })).toHaveAttribute("href", "https://publisher.invalid/article");
});
it("paginates signals independently and displays errors", async () => {
  vi.mocked(api.signals).mockResolvedValueOnce({ ...empty, total: 11 }).mockRejectedValueOnce(new Error("Evidence unavailable"));
  mount(<EvidencePanel companyId="a" />);
  const panel = screen.getByRole("region", { name: "Company signals" });
  await waitFor(() => expect(within(panel).getByRole("button", { name: "Next" })).toBeEnabled());
  await userEvent.click(within(panel).getByRole("button", { name: "Next" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Evidence unavailable");
  expect(api.signals).toHaveBeenLastCalledWith("a", 2, expect.any(AbortSignal));
  expect(api.relationships).toHaveBeenCalledTimes(1);
});
it("reports partial import source issues", async () => {
  vi.mocked(api.ingestionRuns).mockResolvedValue({ ...empty, total: 1, items: [{
    id: "run", status: "partial", tickers: ["ACME"], started_at: "2026-09-18T00:00:00Z", finished_at: "2026-09-18T00:01:00Z",
    summary: { filings_processed: 1, news_processed: 0 }, errors: [{ ticker: "ACME", source: "gdelt_news", message: "HTTP 429" }],
  }] });
  mount(<IngestionStatus />);
  expect(await screen.findByText("partial")).toBeInTheDocument();
  await userEvent.click(screen.getByText("1 import issue(s)"));
  expect(screen.getByText(/HTTP 429/)).toBeInTheDocument();
});
it("rejects script links and treats source text literally", () => {
  mount(<SourceLink url="javascript:alert(1)">{"<img src=x onerror=alert(1)>"}</SourceLink>);
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
  expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
});
