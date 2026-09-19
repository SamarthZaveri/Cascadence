import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "../pages/Dashboard";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: { companies: vi.fn(), graph: vi.fn(), risk: vi.fn(), signals: vi.fn(), relationships: vi.fn(), ingestionRuns: vi.fn() },
}));
vi.mock("../components/NetworkGraph", () => ({
  default: ({ onNodeClick }: { onNodeClick: (id: string) => void }) => (
    <button onClick={() => onNodeClick("supplier")}>
      Explore supplier node
    </button>
  ),
}));
const company = {
  id: "focal",
  name: "Aster Works",
  ticker: null,
  industry: "Materials",
  hq_country: "India",
  is_synthetic: true,
  risk_score: 0.35,
};
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.resetAllMocks());
beforeEach(() => {
  const empty = {items: [], total: 0, page: 1, page_size: 10};
  vi.mocked(api.signals).mockResolvedValue(empty);
  vi.mocked(api.relationships).mockResolvedValue(empty);
  vi.mocked(api.ingestionRuns).mockResolvedValue(empty);
});

function mockNetwork() {
  vi.mocked(api.companies).mockResolvedValue({
    items: [company],
    total: 1,
    page: 1,
    page_size: 12,
  });
  vi.mocked(api.graph).mockResolvedValue({
    nodes: [{ id: "focal", name: company.name, risk_score: 0.35, tier: 0 }],
    links: [],
  });
  vi.mocked(api.risk).mockResolvedValue({
    company_id: "focal",
    latest: null,
    history: [],
  });
}

describe("Dashboard", () => {
  it("explains how to populate an empty database", async () => {
    vi.mocked(api.companies).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 12,
    });
    mount();
    expect(
      await screen.findByText(/Import sources or load the synthetic demonstration/),
    ).toBeInTheDocument();
    expect(api.graph).not.toHaveBeenCalled();
  });
  it("shows backend errors and permits retry", async () => {
    vi.mocked(api.companies)
      .mockRejectedValueOnce(new Error("Data store unavailable"))
      .mockResolvedValue({ items: [], total: 0, page: 1, page_size: 12 });
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Data store unavailable",
    );
    await userEvent.click(screen.getByRole("button", { name: /Refresh data/ }));
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
  });
  it("loads graph and history and reselects clicked nodes", async () => {
    mockNetwork();
    mount();
    await screen.findByRole("button", { name: /Explore supplier node/ });
    expect(api.graph).toHaveBeenCalledWith(
      "focal",
      3,
      "upstream",
      expect.any(AbortSignal),
    );
    expect(
      await screen.findByText("No scores have been computed for this company."),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /Explore supplier node/ }),
    );
    await waitFor(() =>
      expect(api.risk).toHaveBeenCalledWith(
        "supplier",
        expect.any(AbortSignal),
      ),
    );
    expect(
      screen.getByText(/Scores are not calibrated probabilities/),
    ).toBeInTheDocument();
  });
  it("sends traversal and directory filters to the API", async () => {
    mockNetwork();
    mount();
    await screen.findByRole("button", { name: /Explore supplier node/ });
    await userEvent.selectOptions(
      screen.getByLabelText("Direction"),
      "downstream",
    );
    await waitFor(() =>
      expect(api.graph).toHaveBeenCalledWith(
        "focal",
        3,
        "downstream",
        expect.any(AbortSignal),
      ),
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Industry"),
      "Materials",
    );
    await waitFor(() =>
      expect(api.companies).toHaveBeenCalledWith(
        "",
        "Materials",
        1,
        expect.any(AbortSignal),
      ),
    );
  });
});
