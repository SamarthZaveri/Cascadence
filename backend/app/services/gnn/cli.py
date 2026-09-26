"""python -m app.services.gnn.cli --help"""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

import numpy as np
import torch
from sqlalchemy import select

from app.config import get_settings
from app.db.postgres import SessionLocal
from app.models import GraphSnapshot
from app.services.gnn.dataset import load_labels, real_examples, temporal_split
from app.services.gnn.eval import markdown_report, run_ablations, run_architecture_comparison
from app.services.gnn.features import record_snapshot
from app.services.gnn.registry import activate, save_version, score_current
from app.services.ingestion.repository import writer_lock


def experiment(splits, output, epochs, seeds, lineage, register=False):
    output.mkdir(parents=True, exist_ok=True)
    runs = run_architecture_comparison(splits, epochs, seeds) + run_ablations(splits, epochs, seeds)
    train_y = torch.cat([e.y[e.mask] for e in splits["train"]]).numpy()
    prevalence = float(train_y.mean())
    baseline = {
        name: float(np.mean((torch.cat([e.y[e.mask] for e in rows]).numpy() - prevalence) ** 2))
        for name, rows in splits.items()
    }
    reports, versions = [], []
    for _, model, report in runs:
        report["validation_constant_brier"] = baseline["validation"]
        report["test_constant_brier"] = baseline["test"]
        reports.append(report)
        if register:
            versions.append(str(save_version(model, report, lineage)))
    result = {
        **lineage,
        "reports": reports,
        "model_versions": versions,
        "constant_baseline_brier": baseline,
        "split_examples": {k: len(v) for k, v in splits.items()},
        "split_snapshot_ids": {
            k: sorted({s for e in v for s in e.snapshot_ids}) for k, v in splits.items()
        },
    }
    # Recommend only by validation; do not use the held-out test as a selection loop.
    full = [r for r in reports if r["ablation"] == "full"]
    best = min(full, key=lambda r: r["validation"]["brier"])
    result["recommended"] = {"architecture": best["architecture"], "seed": best["seed"]}
    if register:
        result["recommended"]["model_version_id"] = versions[reports.index(best)]
    (output / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    markdown_report(reports, output / "comparison.md", lineage["data_basis"])
    return {
        "output": str(output),
        "runs": len(runs),
        "recommended": result["recommended"],
        "data_basis": lineage["data_basis"],
        "model_versions": versions,
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 4 real snapshots and model experiments")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot")
    sub.add_parser("snapshot-list")
    sub.add_parser("score")
    select_model = sub.add_parser("activate")
    select_model.add_argument("--id", type=UUID, required=True)
    for command in ("benchmark", "compare"):
        p = sub.add_parser(command)
        p.add_argument("--epochs", type=int, default=80)
        p.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44])
        p.add_argument("--output", type=Path, default=None)
        if command == "compare":
            p.add_argument("--labels", type=Path, required=True)
            p.add_argument("--steps", type=int, default=4)
    args = parser.parse_args()
    if args.command == "snapshot-list":
        with SessionLocal() as db:
            rows = list(db.scalars(select(GraphSnapshot).order_by(
                GraphSnapshot.as_of.desc()).limit(1000)))
            result = {"items": [{"id": row.id, "as_of": row.as_of.isoformat(),
                                 "companies": row.payload["node_ids"]} for row in rows]}
    elif args.command == "snapshot":
        with writer_lock(), SessionLocal.begin() as db:
            row = record_snapshot(db)
            result = {
                "snapshot_id": row.id,
                "as_of": row.as_of.isoformat(),
                "companies": len(row.payload["node_ids"]),
                "edges": len(row.payload["edges"]),
            }
    elif args.command == "score":
        with writer_lock():
            result = score_current()
    elif args.command == "activate":
        result = activate(args.id)
    else:
        if not 1 <= args.epochs <= 2000 or not 1 <= len(args.seeds) <= 10:
            parser.error("Use 1–2000 epochs and 1–10 seeds")
        output = args.output or Path(get_settings().MODEL_ARTIFACT_DIR) / ("phase4-" + args.command)
        if args.command == "benchmark":
            from app.services.gnn.benchmark import benchmark_splits

            splits = benchmark_splits()
            lineage = {
                "data_basis": "synthetic_engineering_benchmark",
                "steps": 4,
                "limitation": "Offline simulation only; no real forecasting claim",
            }
        else:
            labels = load_labels(args.labels)
            output.mkdir(parents=True, exist_ok=True)
            (output / "labels.jsonl").write_bytes(args.labels.read_bytes())
            with SessionLocal() as db:
                snapshots = list(db.scalars(select(GraphSnapshot).order_by(GraphSnapshot.as_of)))
            splits = temporal_split(real_examples(snapshots, labels, args.steps))
            lineage = {
                "data_basis": "real_reviewed_outcomes",
                "steps": args.steps,
                "labels_sha256": hashlib.sha256(args.labels.read_bytes()).hexdigest(),
                "snapshot_ids": sorted(
                    {s for rows in splits.values() for e in rows for s in e.snapshot_ids}
                ),
                "split_method": "chronological_purged_feature_and_label_windows",
            }
        result = experiment(
            splits, output, args.epochs, args.seeds, lineage, register=args.command == "compare"
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
