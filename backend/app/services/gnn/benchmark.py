"""Explicit offline engineering benchmark. Never inserts companies/signals/risk rows."""

from datetime import UTC, datetime, timedelta

import torch

from app.services.gnn.dataset import Example
from app.services.gnn.features import EDGE_WIDTH, FEATURES, WIDTH
from app.services.gnn.graph_builder import shock_targets
from app.services.ingestion.synthetic_generator import INDUSTRIES, RELATIONSHIPS, generate_network


def benchmark_splits():
    from torch_geometric.data import Data

    splits = {}
    for name, seeds in {
        "train": range(100, 112),
        "validation": range(200, 204),
        "test": range(300, 304),
    }.items():
        examples = []
        for seed in seeds:
            graph = generate_network(num_companies=30, seed=seed)
            ids = sorted(graph)
            index = {n: i for i, n in enumerate(ids)}
            edges = sorted(graph.edges)
            edge_index = torch.tensor([[index[u], index[v]] for u, v in edges]).t().contiguous()
            attrs = torch.tensor(
                [
                    [graph.edges[e]["criticality"]]
                    + [float(graph.edges[e]["relationship_type"] == r) for r in RELATIONSHIPS]
                    for e in edges
                ]
            ).reshape(-1, EDGE_WIDTH)
            rng = torch.Generator().manual_seed(seed)
            frames, history = [], []
            for _ in range(4):
                shocks = torch.rand(len(ids), generator=rng)
                shocks = torch.where(shocks > 0.7, shocks, shocks * 0.1)
                x = torch.zeros(len(ids), WIDTH)
                for i, n in enumerate(ids):
                    x[i, INDUSTRIES.index(graph.nodes[n]["industry"])] = 1
                for source in ("news", "satellite", "viirs", "ais"):
                    column = FEATURES.index(source + "_value")
                    x[:, column] = (shocks + 0.15 * torch.rand(len(ids), generator=rng)).clamp(0, 1)
                    x[:, column + 1 : column + 3] = 1
                frame = Data(
                    x=x,
                    edge_index=edge_index,
                    edge_attr=attrs,
                    edge_weight=attrs[:, 0],
                    node_present=torch.ones(len(ids), dtype=torch.bool),
                )
                frame.node_ids = ids
                frames.append(frame)
                history.append(shocks)
            # Known simulated mechanism; engineering evidence only.
            shock = 0.55 * history[-1] + 0.3 * history[-2] + 0.15 * history[-3]
            target = torch.tensor(shock_targets(graph, dict(zip(ids, shock.tolist())))) > 0.4
            now = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=seed)
            examples.append(
                Example(
                    frames,
                    target.float(),
                    torch.ones(len(ids), dtype=torch.bool),
                    now - timedelta(days=3),
                    now,
                    now + timedelta(days=7),
                    [f"benchmark:{seed}:{i}" for i in range(4)],
                )
            )
        splits[name] = examples
    return splits
