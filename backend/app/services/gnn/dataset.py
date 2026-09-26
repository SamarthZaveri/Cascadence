"""Reviewed future-outcome labels and purged chronological splits.

Unlabelled nodes stay masked. No-news, absent imagery, or zero vessel messages are
never treated as confirmed negative outcomes. Labels never enter feature vectors.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import torch

from app.services.gnn.features import build_temporal_snapshots


@dataclass
class Example:
    frames: list
    y: torch.Tensor
    mask: torch.Tensor
    start: datetime
    as_of: datetime
    label_end: datetime
    snapshot_ids: list[str]
    label_available: datetime | None = None


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("All label times must include a timezone")
    return result.astimezone(UTC)


def load_labels(path: Path) -> list[dict]:
    if path.stat().st_size > 20_000_000:
        raise ValueError("Label manifest exceeds 20 MB")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    seen = set()
    for row in rows:
        start, end, available = (
            timestamp(row[k]) for k in ("as_of", "outcome_end", "available_at")
        )
        if (
            type(row.get("label")) is not int
            or row.get("label") not in (0, 1)
            or not start < end <= available <= datetime.now(UTC)
            or not row.get("reviewed_by", "").strip()
            or not row.get("rationale", "").strip()
            or row.get("target") != "documented_operational_disruption"
            or urlsplit(row.get("source_url", "")).scheme != "https"
            or not urlsplit(row.get("source_url", "")).hostname
        ):
            raise ValueError(
                "Labels require reviewed binary outcomes, HTTPS evidence and valid times"
            )
        if end - start != timedelta(days=7):
            raise ValueError("Phase 4 target horizon is exactly seven days")
        key = (row["snapshot_id"], row["company_id"])
        if key in seen:
            raise ValueError("Duplicate company/snapshot label")
        seen.add(key)
    if not rows:
        raise ValueError("No reviewed outcomes supplied")
    return rows


def real_examples(snapshots: list, labels: list[dict], steps: int = 4) -> list[Example]:
    if not 2 <= steps <= 30:
        raise ValueError("Temporal steps must be 2–30")
    # One recorded snapshot per UTC day. Never invent intermediate days.
    days = {}
    for snap in sorted(snapshots, key=lambda s: s.as_of):
        days[snap.as_of.date()] = snap
    ordered = list(days.values())
    positions = {s.id: i for i, s in enumerate(ordered)}
    grouped: dict[str, list] = {}
    for row in labels:
        if row["snapshot_id"] not in positions:
            raise ValueError("Label must reference the last recorded snapshot of its UTC day")
        grouped.setdefault(row["snapshot_id"], []).append(row)
    result = []
    for identifier, group in grouped.items():
        index = positions[identifier]
        if index < steps - 1:
            raise ValueError("Label snapshot has insufficient preceding daily history")
        sequence = ordered[index - steps + 1 : index + 1]
        if any((b.as_of.date() - a.as_of.date()).days != 1 for a, b in zip(sequence, sequence[1:])):
            raise ValueError("Temporal sequence has missing daily snapshots")
        if any(s.payload.get("basis") != "forward_recorded_real" for s in sequence):
            raise ValueError("Real training requires forward-recorded real snapshots")
        frames = build_temporal_snapshots([s.payload for s in sequence])
        lookup = {n: i for i, n in enumerate(frames[-1].node_ids)}
        y, mask = torch.zeros(len(lookup)), torch.zeros(len(lookup), dtype=torch.bool)
        for row in group:
            if timestamp(row["as_of"]) != sequence[-1].as_of or row["company_id"] not in lookup:
                raise ValueError("Outcome does not match its snapshot time/company")
            i = lookup[row["company_id"]]
            y[i], mask[i] = row["label"], True
        result.append(
            Example(
                frames,
                y,
                mask,
                sequence[0].as_of,
                sequence[-1].as_of,
                timestamp(group[0]["outcome_end"]),
                [s.id for s in sequence],
                max(timestamp(row["available_at"]) for row in group),
            )
        )
    return sorted(result, key=lambda e: e.as_of)


def temporal_split(examples: list[Example]) -> dict[str, list[Example]]:
    if len(examples) < 12:
        raise ValueError("Need at least 12 labelled daily examples plus purge gaps")
    examples = sorted(examples, key=lambda e: e.as_of)
    a, b = int(len(examples) * 0.6), int(len(examples) * 0.8)
    validation_start, test_start = examples[a].start, examples[b].start
    # Label horizon must end before the next split's earliest feature time.
    splits = {
        "train": [e for e in examples[:a]
                  if max(e.label_end, e.label_available or e.label_end) < validation_start],
        "validation": [e for e in examples[a:b]
                       if max(e.label_end, e.label_available or e.label_end) < test_start],
        "test": examples[b:],
    }
    for name, split in splits.items():
        if not split:
            raise ValueError(f"{name} empty after purging overlapping feature/label windows")
        y = torch.cat([e.y[e.mask] for e in split])
        if y.numel() < 20 or y.unique().numel() != 2:
            raise ValueError(f"{name} needs both classes and at least 20 reviewed labels")
    return splits
