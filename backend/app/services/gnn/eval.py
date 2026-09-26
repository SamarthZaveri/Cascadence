"""Same splits/seeds/budget across architectures and retrained modality ablations."""

from copy import deepcopy
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score

from app.services.gnn.dataset import Example
from app.services.gnn.features import NEWS_COLUMNS, VISION_COLUMNS
from app.services.gnn.models import ARCHITECTURES, create_model


def inputs(example: Example, architecture: str, ablation: str):
    frames = [f.clone() for f in example.frames]
    columns = (
        VISION_COLUMNS if ablation == "no_vision" else NEWS_COLUMNS if ablation == "no_news" else []
    )
    for frame in frames:
        frame.x[:, columns] = 0
    if ablation == "no_temporal":
        frames = frames[-1:]
    return frames if architecture == "temporal" else frames[-1]


def evaluate(model, examples, architecture, ablation="full"):
    model.eval()
    with torch.no_grad():
        p = torch.cat([model(inputs(e, architecture, ablation))[e.mask] for e in examples])
        y = torch.cat([e.y[e.mask] for e in examples])
    return y.numpy(), p.numpy()


def metrics(y, p):
    if not len(y) or not np.isfinite(p).all():
        raise ValueError("Cannot evaluate empty/nonfinite predictions")
    precision, recall, f1, _ = precision_recall_fscore_support(
        y, p >= 0.5, average="binary", zero_division=0
    )
    both = len(np.unique(y)) == 2
    return {
        "n": len(y),
        "positives": int(sum(y)),
        "threshold": 0.5,
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": float(roc_auc_score(y, p)) if both else None,
        "pr_auc": float(average_precision_score(y, p)) if both else None,
        "brier": float(np.mean((p - y) ** 2)),
    }


def fit(architecture, splits, epochs=80, lr=0.003, seed=42, ablation="full"):
    if epochs < 1 or not 0 < lr <= 1:
        raise ValueError("Invalid epochs/learning rate")
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    model = create_model(architecture)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    best_loss, best_epoch, state = float("inf"), 0, None
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        total = sum(int(e.mask.sum()) for e in splits["train"])
        for example in splits["train"]:
            prediction = model(inputs(example, architecture, ablation))[example.mask]
            loss = (
                torch.nn.functional.binary_cross_entropy(
                    prediction, example.y[example.mask], reduction="sum"
                )
                / total
            )
            loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
        optimizer.step()
        y, p = evaluate(model, splits["validation"], architecture, ablation)
        loss_value = float(np.mean((p - y) ** 2))
        if loss_value < best_loss:
            best_loss, best_epoch, state = loss_value, epoch + 1, deepcopy(model.state_dict())
    if state is None:
        raise ValueError("Training did not produce a finite validation score")
    model.load_state_dict(state)
    model.eval()
    report = {
        "architecture": architecture,
        "ablation": ablation,
        "seed": seed,
        "epochs": epochs,
        "best_epoch": best_epoch,
        "selection": "validation_brier",
        "parameters": sum(p.numel() for p in model.parameters()),
    }
    for name, examples in splits.items():
        report[name] = metrics(*evaluate(model, examples, architecture, ablation))
    return model, report


def run_architecture_comparison(splits, epochs=80, seeds=(42, 43, 44)):
    return [
        (architecture, *fit(architecture, splits, epochs=epochs, seed=seed))
        for architecture in ARCHITECTURES
        for seed in seeds
    ]


def run_ablations(splits, epochs=80, seeds=(42, 43, 44)):
    return [
        ("temporal", *fit("temporal", splits, epochs=epochs, seed=seed, ablation=ablation))
        for ablation in ("no_temporal", "no_vision", "no_news")
        for seed in seeds
    ]


def markdown_report(reports: list[dict], path: Path, basis: str):
    lines = [
        "# cascadence Phase 4 model evaluation",
        "",
        f"Data basis: **{basis}**.",
        "",
        "Checkpoint selection uses validation Brier score. Test data never selects a model.",
        "Scores are experimental indices; these metrics do not establish trading utility.",
        "",
        "| Architecture | Ablation | Seed | Best epoch | Test precision | Recall | F1 "
        "| ROC AUC | PR AUC | Brier |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in reports:
        m = r["test"]
        values = [
            f"{m[k]:.4f}" if m[k] is not None else "undefined"
            for k in ("precision", "recall", "f1", "roc_auc", "pr_auc", "brier")
        ]
        lines.append(
            f"| {r['architecture']} | {r['ablation']} | {r['seed']} | {r['best_epoch']} | "
            + " | ".join(values)
            + " |"
        )
    lines += [
        "",
        "## Across-seed variation",
        "",
        "| Architecture | Ablation | Mean test F1 ± SD | Mean test Brier ± SD |",
        "|---|---|---:|---:|",
    ]
    for key in sorted({(r["architecture"], r["ablation"]) for r in reports}):
        group = [r for r in reports if (r["architecture"], r["ablation"]) == key]
        cells = [
            f"{np.mean(v):.4f} ± {np.std(v):.4f}"
            for v in ([r["test"][k] for r in group] for k in ("f1", "brier"))
        ]
        lines.append("| " + " | ".join([*key, *cells]) + " |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
