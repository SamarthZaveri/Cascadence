"""CPU training with graph-disjoint train/validation/test sets and validation selection."""

from copy import deepcopy
from typing import Any

import torch
from torch_geometric.data import Batch

from app.services.gnn.graph_builder import shock_targets, synthetic_shocks, to_pyg
from app.services.gnn.models import GCNRiskModel
from app.services.ingestion.synthetic_generator import generate_network


def make_batch(seeds: list[int]) -> Batch:
    graphs = []
    for seed in seeds:
        graph = generate_network(seed=seed)
        shocks = synthetic_shocks(graph, seed)
        data = to_pyg(graph, shocks)
        data.y = torch.tensor(shock_targets(graph, shocks), dtype=torch.float32)
        graphs.append(data)
    return Batch.from_data_list(graphs)


def train_model(
    epochs: int = 120, seed: int = 42, lr: float = 0.01
) -> tuple[GCNRiskModel, dict[str, Any]]:
    if epochs < 1 or lr <= 0:
        raise ValueError("epochs and learning rate must be positive")
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    # Negative seeds are reserved for training; the seed CLI accepts nonnegative demo seeds.
    splits = {
        "train": list(range(-1024, -1000)),
        "validation": list(range(-2006, -2000)),
        "test": list(range(-3006, -3000)),
    }
    train, validation, test = (make_batch(splits[name]) for name in splits)
    model = GCNRiskModel()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    best_loss = float("inf")
    best_state = deepcopy(model.state_dict())
    best_epoch = 0
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        loss = torch.nn.functional.mse_loss(model(train), train.y)
        loss.backward()
        optimizer.step()
        model.eval()
        with torch.no_grad():
            validation_loss = float(torch.nn.functional.mse_loss(model(validation), validation.y))
        if validation_loss < best_loss:
            best_loss, best_epoch = validation_loss, epoch + 1
            best_state = deepcopy(model.state_dict())
    model.load_state_dict(best_state)
    model.eval()
    metrics: dict[str, Any] = {
        "task": "synthetic_two_step_shock_regression",
        "seed": seed,
        "epochs": epochs,
        "best_epoch": best_epoch,
        "split_graph_seeds": splits,
        "limitation": "Synthetic evaluation only; no real-world validation",
    }
    with torch.no_grad():
        for name, batch in (("train", train), ("validation", validation), ("test", test)):
            prediction = model(batch)
            metrics[name + "_mae"] = float((prediction - batch.y).abs().mean())
            metrics[name + "_mse"] = float(((prediction - batch.y) ** 2).mean())
        metrics["test_constant_baseline_mae"] = float((test.y - train.y.mean()).abs().mean())
        metrics["test_local_shock_baseline_mae"] = float((test.y - test.x[:, -1]).abs().mean())
    return model, metrics
