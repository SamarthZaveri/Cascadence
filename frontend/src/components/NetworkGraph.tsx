import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { GraphResponse } from "../types/intelligence";

type Props = GraphResponse & {
  centerNodeId: string;
  mode?: "static" | "simulation";
  onNodeClick: (id: string) => void;
};

export default function NetworkGraph({
  nodes,
  links,
  centerNodeId,
  onNodeClick,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(240, entry.contentRect.width)),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  // ForceGraph mutates coordinates and link endpoints. Protect the TanStack Query cache.
  const graph = useMemo(
    () => ({
      nodes: nodes.map((node) => ({ ...node })),
      links: links.map((link) => ({ ...link })),
    }),
    [nodes, links],
  );
  const color = (score: number | null) =>
    score === null
      ? "#87919d"
      : score >= 0.7
        ? "#e36d56"
        : score >= 0.4
          ? "#e0ae51"
          : "#62b5a2";
  return (
    <div
      className="graph-wrap"
      ref={container}
      aria-label="Supply network visualization"
    >
      <ForceGraph2D
        width={width}
        height={450}
        graphData={graph}
        backgroundColor="#101e2c"
        nodeRelSize={6}
        nodeColor={(node) => color(node.risk_score)}
        nodeLabel="name"
        nodeVal={(node) => (node.id === centerNodeId ? 3 : 1)}
        linkColor={() => "#536577"}
        linkWidth={(link) => 0.6 + link.criticality * 2}
        linkDirectionalArrowLength={5}
        linkDirectionalArrowRelPos={0.85}
        cooldownTicks={100}
        onNodeClick={(node) => onNodeClick(String(node.id))}
        nodeCanvasObjectMode={() => "after"}
        nodeCanvasObject={(node, context, scale) => {
          if (node.id !== centerNodeId && scale < 1.3) return;
          context.font = `${11 / scale}px sans-serif`;
          context.fillStyle = "#e5edf5";
          context.textAlign = "center";
          context.fillText(node.name, node.x ?? 0, (node.y ?? 0) + 12 / scale);
        }}
      />
      <div className="graph-caption">
        Arrows follow supplier → customer · Click a company to explore
      </div>
      <details className="graph-accessible">
        <summary>Accessible company list ({nodes.length})</summary>
        <ul>
          {nodes.map((node) => (
            <li key={node.id}>
              <button onClick={() => onNodeClick(node.id)}>
                {node.name} · Tier {node.tier} ·{" "}
                {node.risk_score === null
                  ? "Unscored"
                  : node.risk_score.toFixed(2)}
              </button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
