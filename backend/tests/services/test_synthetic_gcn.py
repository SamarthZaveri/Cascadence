import networkx as nx
import pytest
import torch

from app.services.gnn.graph_builder import (
    FEATURE_SCHEMA,
    NUM_FEATURES,
    shock_targets,
    synthetic_shocks,
    to_pyg,
)
from app.services.gnn.infer import load_model
from app.services.gnn.models import GCNRiskModel
from app.services.gnn.train import train_model
from app.services.ingestion.synthetic_generator import generate_network


def test_generator_is_reproducible_connected_and_directed():
    first = generate_network()
    second = generate_network()
    assert nx.utils.graphs_equal(first, second)
    assert nx.is_directed_acyclic_graph(first)
    assert nx.is_weakly_connected(first)
    assert all(first.nodes[u]["tier"] > first.nodes[v]["tier"] for u, v in first.edges)
    assert all(0 <= edge["criticality"] <= 1 for _, _, edge in first.edges(data=True))
    assert all(node["is_synthetic"] for _, node in first.nodes(data=True))
    assert not set(first) & set(generate_network(seed=43))
    assert not set(first) & set(generate_network(num_companies=61))


@pytest.mark.parametrize(
    "kwargs", [dict(num_companies=0), dict(num_tiers=61), dict(avg_out_degree=0), dict(num_tiers=1)]
)
def test_invalid_generator_inputs(kwargs):
    with pytest.raises(ValueError):
        generate_network(**kwargs)


@pytest.mark.parametrize("size,tiers", [(1, 1), (60, 4)])
def test_pyg_order_direction_and_checkpoint_roundtrip(tmp_path, size, tiers):
    graph = generate_network(size, tiers)
    shocks = synthetic_shocks(graph, 42)
    data = to_pyg(graph, shocks)
    assert data.x.shape == (size, NUM_FEATURES)
    assert data.edge_index.shape == (2, graph.number_of_edges())
    assert data.edge_attr.shape == (graph.number_of_edges(), 5)
    assert data.node_ids == sorted(graph)
    for i, (u, v) in enumerate(sorted(graph.edges)):
        assert data.node_ids[data.edge_index[0, i]] == u
        assert data.node_ids[data.edge_index[1, i]] == v
    assert "y" not in data  # labels and previous scores are not input features
    model = GCNRiskModel().eval()
    path = tmp_path / "model.pt"
    torch.save({"feature_schema": FEATURE_SCHEMA, "state_dict": model.state_dict()}, path)
    with torch.no_grad():
        expected = model(data)
        actual = load_model(path)(data)
    assert actual.shape == (size,)
    assert torch.isfinite(actual).all()
    assert ((actual >= 0) & (actual <= 1)).all()
    assert torch.allclose(expected, actual)


def test_zero_shocks_and_disconnected_graph():
    graph = generate_network(5, 3)
    graph.remove_edges_from(list(graph.edges))
    shocks = {node: 0.0 for node in graph}
    assert shock_targets(graph, shocks) == [0.0] * 5
    data = to_pyg(graph, shocks)
    assert data.edge_index.shape == (2, 0)
    assert GCNRiskModel()(data).shape == (5,)
    empty = to_pyg(nx.DiGraph(), {})
    assert GCNRiskModel()(empty).shape == (0,)


def test_shock_propagates_to_customer_not_supplier():
    graph = nx.DiGraph()
    graph.add_edge("supplier", "customer", criticality=1.0)
    result = dict(zip(sorted(graph), shock_targets(graph, {"supplier": 1.0, "customer": 0.0})))
    assert result["customer"] == pytest.approx(0.65)
    assert result["supplier"] == 1.0
    result = dict(zip(sorted(graph), shock_targets(graph, {"supplier": 0.0, "customer": 1.0})))
    assert result["supplier"] == 0.0


def test_training_uses_disjoint_graphs_and_beats_constant_baseline():
    _, metrics = train_model(epochs=80)
    splits = [set(seeds) for seeds in metrics["split_graph_seeds"].values()]
    assert not splits[0] & splits[1] and not splits[0] & splits[2] and not splits[1] & splits[2]
    assert metrics["test_mae"] < metrics["test_constant_baseline_mae"]
    assert 1 <= metrics["best_epoch"] <= 80
