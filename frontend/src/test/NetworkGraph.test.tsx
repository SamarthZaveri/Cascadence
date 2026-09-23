import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import NetworkGraph from "../components/NetworkGraph";
import RiskBadge from "../components/RiskBadge";

vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    disconnect() {}
  },
);
vi.mock("react-force-graph-2d", () => ({
  default: ({
    graphData,
    onNodeClick,
  }: {
    graphData: {
      nodes: Array<{ id: string; x?: number }>;
      links: Array<{ source: unknown }>;
    };
    onNodeClick: (node: { id: string }) => void;
  }) => {
    graphData.nodes[0].x = 99;
    if (graphData.links[0]) graphData.links[0].source = graphData.nodes[0];
    return (
      <button onClick={() => onNodeClick(graphData.nodes[0])}>
        Canvas node
      </button>
    );
  },
}));

it("protects cached graph objects from force simulation mutations and supports selection", async () => {
  const nodes = [
    { id: "a", name: "Aster", risk_score: 0.1, tier: 0, is_synthetic: false },
    { id: "b", name: "Beryl", risk_score: null, tier: 1, is_synthetic: false },
  ];
  const links = [{ source: "b", target: "a", criticality: 0.9 }];
  const original = JSON.stringify({ nodes, links });
  const onNodeClick = vi.fn();
  render(
    <NetworkGraph
      nodes={nodes}
      links={links}
      centerNodeId="a"
      onNodeClick={onNodeClick}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Canvas node" }));
  expect(onNodeClick).toHaveBeenCalledWith("a");
  expect(JSON.stringify({ nodes, links })).toBe(original);
  expect(screen.getByText("Accessible company list (2)")).toBeInTheDocument();
});

it("distinguishes an unscored company from zero risk", () => {
  render(
    <>
      <RiskBadge score={null} />
      <RiskBadge score={0} />
    </>,
  );
  expect(screen.getByText("Unscored")).toBeInTheDocument();
  expect(screen.getByText("low · 0.00")).toBeInTheDocument();
});
