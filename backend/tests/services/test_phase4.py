import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as Row
from uuid import uuid4

import pytest
import torch

from app.services.gnn.benchmark import benchmark_splits
from app.services.gnn.dataset import Example, load_labels, temporal_split
from app.services.gnn.eval import fit, inputs, metrics
from app.services.gnn.features import (
    FEATURES,
    SCHEMA,
    assemble,
    build_temporal_snapshots,
    measurement,
    to_data,
)
from app.services.gnn.models import ARCHITECTURES, create_model
from app.services.gnn.registry import eligibility, load_version
from app.services.ingestion.universe import WindowedNews

NOW = datetime(2026, 9, 25, tzinfo=UTC)


def company(identifier="a", **kwargs):
    return Row(
        id=identifier,
        created_at=NOW - timedelta(days=100),
        is_synthetic=False,
        industry="Electronics",
        **kwargs,
    )


def signal(identifier="s", **kwargs):
    values = dict(
        id=identifier,
        company_id="a",
        location_id=None,
        source_type="news",
        severity_score=0.8,
        extracted_data={},
        observed_at=NOW - timedelta(days=1),
        ingested_at=NOW - timedelta(hours=12),
    )
    return Row(**(values | kwargs))


def test_features_observation_and_ingestion_cutoffs_missingness_and_synthetic():
    fake = company("fake")
    fake.is_synthetic = True
    rows = [
        signal(),
        signal("late", ingested_at=NOW + timedelta(seconds=1)),
        signal("future", observed_at=NOW + timedelta(seconds=1)),
        signal("stale", observed_at=NOW - timedelta(days=31)),
        signal("excluded", extracted_data={"eligible_for_scoring": False}),
    ]
    payload = assemble([company(), company("b"), fake], rows, [], [], NOW)
    assert payload["node_ids"] == ["a", "b"]
    assert payload["evidence"] == {"a": {"news": ["s"]}, "b": {}}
    frame = to_data(payload)
    assert frame.x[0, FEATURES.index("news_value")] == pytest.approx(0.8)
    assert frame.x[1, FEATURES.index("news_present")] == 0
    assert frame.x[1, FEATURES.index("news_age")] == 1


def test_edges_need_approved_known_evidence_and_knowledge_time():
    edge = Row(
        id="edge",
        supplier_id="a",
        customer_id="b",
        status="approved",
        provenance="sec_filing",
        created_at=NOW - timedelta(days=1),
        reviewed_at=NOW,
        source_signal_id="s",
        criticality=0.5,
        relationship_type="component",
    )
    args = ([company(), company("b")], [signal()], [edge], [])
    assert len(assemble(*args, NOW)["edges"]) == 1
    edge.reviewed_at = NOW + timedelta(seconds=1)
    assert assemble(*args, NOW)["edges"] == []
    edge.reviewed_at, edge.status = NOW, "pending"
    assert assemble(*args, NOW)["edges"] == []


@pytest.mark.parametrize(
    "source,key,value",
    [
        ("satellite", "surface_change", 0.2),
        ("viirs", "relative_radiance_decrease", -0.3),
        ("ais", "vessel_activity_ratio", 0.5),
    ],
)
def test_real_sensor_metrics_are_signed_context_and_require_provenance(source, key, value):
    row = signal(source_type=source, extracted_data={key: value})
    assert measurement(row) is None
    row.extracted_data.update(origin="location_observation", provenance={"url": "source"})
    assert measurement(row) is not None
    link = Row(company_id="a", location_id="port", available_at=NOW, source_url="https://port.test")
    row.company_id, row.location_id = None, "port"
    payload = assemble([company()], [row], [], [link], NOW)
    assert payload["evidence"]["a"][source] == ["s"]
    link.available_at += timedelta(seconds=1)
    assert assemble([company()], [row], [], [link], NOW)["evidence"]["a"] == {}


def test_temporal_identity_alignment_and_history_mask():
    before = assemble([company("b")], [], [], [], NOW - timedelta(days=1))
    after = assemble([company(), company("b")], [signal()], [], [], NOW)
    frames = build_temporal_snapshots([before, after])
    assert frames[0].node_ids == ["a", "b"]
    assert frames[0].node_present.tolist() == [False, True]
    assert frames[0].x[0].sum() == 0
    with pytest.raises(ValueError, match="strictly ordered"):
        build_temporal_snapshots([after, before])


@pytest.mark.parametrize("architecture", list(ARCHITECTURES))
def test_architecture_gradients_shapes_and_checkpoint_integrity(
    architecture, tmp_path, monkeypatch
):
    import hashlib

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "MODEL_ARTIFACT_DIR", str(tmp_path))
    examples = benchmark_splits()["train"]
    model = create_model(architecture)
    sample = inputs(examples[0], architecture, "full")
    output = model(sample)
    assert output.shape == (30,)
    assert torch.isfinite(output).all()
    output.sum().backward()
    assert any(p.grad is not None and p.grad.abs().sum() > 0 for p in model.parameters())
    path = tmp_path / "model.pt"
    torch.save(
        {
            "feature_schema": SCHEMA,
            "feature_names": list(FEATURES),
            "architecture": architecture,
            "hidden_channels": 32,
            "state_dict": model.state_dict(),
        },
        path,
    )
    version = Row(
        artifact_path=str(path),
        architecture=architecture,
        metrics={"artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
    )
    with torch.no_grad():
        assert torch.allclose(output, load_version(version)(sample))
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        load_version(version)


def test_attention_is_normalized_per_target_and_temporal_uses_history():
    frames = benchmark_splits()["test"][0].frames
    gat = create_model("gat").eval()
    edges, weights = gat.attention_weights(frames[-1])
    for target in edges[1].unique():
        assert torch.allclose(weights[edges[1] == target].sum(0), torch.ones(2), atol=1e-6)
    temporal = create_model("temporal").eval()
    assert not torch.allclose(temporal(frames), temporal(frames[-1:]))
    frames[0].node_ids = list(reversed(frames[0].node_ids))
    with pytest.raises(ValueError, match="aligned"):
        temporal(frames)


def test_ablations_remove_values_and_masks_without_mutating_original():
    e = benchmark_splits()["test"][0]
    original = e.frames[0].x.clone()
    frames = inputs(e, "temporal", "no_news")
    for name in ("value", "count", "present", "age"):
        assert frames[0].x[:, FEATURES.index("news_" + name)].sum() == 0
    assert torch.equal(original, e.frames[0].x)
    assert len(inputs(e, "temporal", "no_temporal")) == 1


def test_purged_split_has_no_overlapping_feature_label_windows():
    examples = []
    for i in range(100):
        at = NOW + timedelta(days=i)
        examples.append(
            Example(
                [],
                torch.tensor([0.0, 1.0] * 10),
                torch.ones(20, dtype=torch.bool),
                at - timedelta(days=3),
                at,
                at + timedelta(days=7),
                [str(i)],
            )
        )
    splits = temporal_split(examples)
    assert max(e.label_end for e in splits["train"]) < min(e.start for e in splits["validation"])
    assert max(e.label_end for e in splits["validation"]) < min(e.start for e in splits["test"])
    examples[0].label_available = NOW + timedelta(days=90)
    assert all(e is not examples[0] for e in temporal_split(examples)["train"])
    for e in examples:
        e.y[:] = 0
    with pytest.raises(ValueError, match="both classes"):
        temporal_split(examples)


def test_labels_require_real_evidence_horizon_and_no_duplicates(tmp_path):
    path = tmp_path / "labels.jsonl"
    row = {
        "company_id": str(uuid4()),
        "snapshot_id": "abc",
        "as_of": "2024-01-01T00:00:00Z",
        "outcome_end": "2024-01-08T00:00:00Z",
        "available_at": "2024-01-09T00:00:00Z",
        "target": "documented_operational_disruption",
        "label": 0,
        "reviewed_by": "reviewer",
        "source_url": "https://example.org/operations",
        "rationale": "Confirmed normal operation",
    }
    path.write_text(json.dumps(row))
    assert len(load_labels(path)) == 1
    path.write_text(json.dumps({**row, "label": 0.0}))
    with pytest.raises(ValueError, match="reviewed"):
        load_labels(path)
    path.write_text(json.dumps(row) + "\n" + json.dumps(row))
    with pytest.raises(ValueError, match="Duplicate"):
        load_labels(path)
    row["rationale"] = ""
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="reviewed"):
        load_labels(path)


def test_synthetic_models_cannot_be_activated_and_single_class_auc_is_undefined():
    assert eligibility(Row(metrics={"data_basis": "synthetic_engineering_benchmark"}))
    assert metrics([1, 1], torch.tensor([0.8, 0.9]).numpy())["roc_auc"] is None


def test_training_selects_validation_checkpoint_reproducibly():
    splits = benchmark_splits()
    _, first = fit("gcn", splits, epochs=3, seed=5)
    _, second = fit("gcn", splits, epochs=3, seed=5)
    assert first == second
    assert 1 <= first["best_epoch"] <= 3


def test_windowed_news_deduplicates_urls_and_exposes_saturation():
    calls = []
    now = datetime.now(UTC)
    article = {
        "url": "https://publisher.test/item?utm_source=test",
        "title": "Port report",
        "seendate": (now - timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ"),
    }

    class Client:
        def json(self, url, params, ttl):
            calls.append(deepcopy(params))
            return {"articles": [article] * 250}

    rows = WindowedNews(Client()).fetch_recent_events("Port", now - timedelta(days=2))
    assert len(rows) == 1
    assert rows[0]["query_saturated"]
    assert rows[0]["url"] == "https://publisher.test/item"
    assert all(c["maxrecords"] == 250 and c["enddatetime"] for c in calls)
