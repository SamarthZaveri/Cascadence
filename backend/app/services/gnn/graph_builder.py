"""Stable feature ordering and supplier -> customer message passing."""

import hashlib
import random

import networkx as nx
import torch
from torch_geometric.data import Data

from app.services.ingestion.synthetic_generator import INDUSTRIES, RELATIONSHIPS

FEATURE_SCHEMA = "phase1-v1"
NUM_FEATURES = len(INDUSTRIES) + 2


def synthetic_shocks(graph: nx.DiGraph, scenario_seed: int) -> dict[str, float]:
    values = {}
    for node in sorted(graph.nodes):
        digest = hashlib.sha256(f"{scenario_seed}:{node}".encode()).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        values[node] = rng.uniform(0.65, 1.0) if rng.random() < 0.25 else rng.uniform(0, 0.12)
    return values


def shock_targets(graph: nx.DiGraph, shocks: dict[str, float]) -> list[float]:
    """Toy two-step propagation labels, deliberately separate from input features."""
    risks = dict(shocks)
    for _ in range(2):
        next_risks = {}
        for node in graph:
            survival = 1.0
            for supplier in graph.predecessors(node):
                survival *= (
                    1.0 - 0.65 * graph.edges[supplier, node]["criticality"] * risks[supplier]
                )
            next_risks[node] = 1.0 - (1.0 - shocks[node]) * survival
        risks = next_risks
    return [risks[node] for node in sorted(graph.nodes)]


def to_pyg(graph: nx.DiGraph, shocks: dict[str, float]) -> Data:
    ids = sorted(graph.nodes)
    index = {node: i for i, node in enumerate(ids)}
    features = []
    for node in ids:
        attrs = graph.nodes[node]
        industry = attrs.get("industry")
        if industry not in INDUSTRIES:
            industry = "Other"
        shock = shocks.get(node, 0.0)
        if not 0 <= shock <= 1:
            raise ValueError("Shock severity must be finite and within [0,1]")
        features.append(
            [float(industry == name) for name in INDUSTRIES] + [float(attrs["is_synthetic"]), shock]
        )
    edges = sorted(graph.edges)
    edge_index = (
        torch.tensor([[index[u], index[v]] for u, v in edges], dtype=torch.long)
        .reshape(-1, 2)
        .t()
        .contiguous()
    )
    weights = [graph.edges[u, v]["criticality"] for u, v in edges]
    if any(not 0 <= weight <= 1 for weight in weights):
        raise ValueError("Criticality must be finite and within [0,1]")
    edge_attr = [
        [graph.edges[u, v]["criticality"]]
        + [float(graph.edges[u, v]["relationship_type"] == name) for name in RELATIONSHIPS]
        for u, v in edges
    ]
    data = Data(
        x=torch.tensor(features, dtype=torch.float32).reshape(-1, NUM_FEATURES),
        edge_index=edge_index,
        edge_weight=torch.tensor(weights, dtype=torch.float32),
        edge_attr=torch.tensor(edge_attr, dtype=torch.float32).reshape(-1, 5),
    )
    data.node_ids = ids
    return data


def build_pyg_graph(company_ids: list[str], scenario_seed: int = 42) -> Data:
    from app.services.ingestion.stores import read_network

    graph = read_network(company_ids)
    return to_pyg(graph, synthetic_shocks(graph, scenario_seed))
