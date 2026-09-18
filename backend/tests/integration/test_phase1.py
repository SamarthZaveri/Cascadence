"""Opt-in real-store tests. CI supplies a dedicated cascadence_test Postgres database.

Run with CASCADENCE_TEST_INTEGRATION=1 and POSTGRES_DB ending in _test.
Only deterministic test network IDs are deleted from Neo4j during cleanup.
"""

import os
from uuid import UUID, uuid4

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db.neo4j_client import get_driver
from app.db.postgres import SessionLocal
from app.main import app
from app.models import Company, ModelVersion, RiskScore
from app.services.ingestion.seed import seed_demo
from app.services.ingestion.synthetic_generator import generate_network

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    if os.getenv("CASCADENCE_TEST_INTEGRATION") != "1":
        pytest.skip("Set CASCADENCE_TEST_INTEGRATION=1 for dedicated-store integration tests")
    settings = get_settings()
    if not settings.POSTGRES_DB.endswith("_test"):
        pytest.fail("Integration tests require a dedicated POSTGRES_DB ending in _test")
    old_path = settings.MODEL_ARTIFACT_DIR
    settings.MODEL_ARTIFACT_DIR = str(tmp_path_factory.mktemp("artifacts"))
    graph = generate_network(18, 4, 2, 987654)
    ids = list(graph)
    try:
        result = seed_demo(18, 4, 2, 987654, 40)
        yield graph, result
    finally:
        with SessionLocal.begin() as db:
            versions = list(
                db.scalars(
                    select(RiskScore.model_version_id)
                    .where(RiskScore.company_id.in_([UUID(i) for i in ids]))
                    .distinct()
                )
            )
            db.execute(delete(RiskScore).where(RiskScore.company_id.in_([UUID(i) for i in ids])))
            db.execute(delete(ModelVersion).where(ModelVersion.id.in_(versions)))
            db.execute(delete(Company).where(Company.id.in_([UUID(i) for i in ids])))
        with get_driver().session() as session:
            session.run("MATCH (c:Company) WHERE c.uuid IN $ids DETACH DELETE c", ids=ids).consume()
        settings.MODEL_ARTIFACT_DIR = old_path


def test_persisted_scores_and_graph_contract(seeded):
    graph, result = seeded
    focal = result["focal_company_id"]
    with TestClient(app) as client:
        response = client.get(f"/api/v1/graph/{focal}?depth=3")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert set(payload) == {"nodes", "links"}
        assert {node["id"] for node in payload["nodes"]} == set(graph)
        assert {(edge["source"], edge["target"]) for edge in payload["links"]} == set(graph.edges)
        assert all(0 <= node["risk_score"] <= 1 for node in payload["nodes"])
        risk = client.get(f"/api/v1/risk/{focal}").json()
        assert risk["latest"]["model_version_id"] == result["model_version_id"]
        assert risk["latest"]["graph_snapshot_id"] == result["graph_snapshot_id"]
        assert risk["history"][0] == risk["latest"]


@pytest.mark.parametrize("direction", ["upstream", "downstream", "both"])
def test_graph_traversal_direction_and_depth(seeded, direction):
    graph, _ = seeded
    selected = next(n for n in graph if graph.nodes[n]["tier"] == 1)
    traversal = graph.reverse() if direction == "upstream" else graph
    if direction == "both":
        traversal = graph.to_undirected()
    expected = set(nx.single_source_shortest_path_length(traversal, selected, cutoff=1))
    with TestClient(app) as client:
        response = client.get(f"/api/v1/graph/{selected}?depth=1&direction={direction}")
        assert response.status_code == 200, response.text
        assert {node["id"] for node in response.json()["nodes"]} == expected


def test_company_pagination_filters_and_unknown_ids(seeded):
    graph, _ = seeded
    node = next(iter(graph))
    name = graph.nodes[node]["name"]
    with TestClient(app) as client:
        result = client.get("/api/v1/companies?page_size=5").json()
        assert len(result["items"]) == 5 and result["total"] >= 18
        result = client.get("/api/v1/companies", params={"search": name}).json()
        assert node in {item["id"] for item in result["items"]}
        assert client.get("/api/v1/companies?search=%25").json()["total"] == 0
        industry = graph.nodes[node]["industry"]
        filtered = client.get("/api/v1/companies", params={"industry": industry}).json()
        assert all(item["industry"] == industry for item in filtered["items"])
        assert client.get(f"/api/v1/risk/{uuid4()}").status_code == 404
        assert client.get(f"/api/v1/graph/{uuid4()}").status_code == 404
        assert client.get(f"/api/v1/companies?workspace_id={uuid4()}").status_code == 422


def test_reseed_is_idempotent_and_appends_history(seeded):
    graph, first = seeded
    with SessionLocal() as db:
        count_before = db.scalar(select(func.count()).select_from(Company))
    second = seed_demo(18, 4, 2, 987654, 10)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Company)) == count_before
        assert (
            db.scalar(select(func.count()).select_from(ModelVersion).where(ModelVersion.is_active))
            == 1
        )
    with TestClient(app) as client:
        result = client.get(f"/api/v1/risk/{first['focal_company_id']}").json()
        assert result["latest"]["model_version_id"] == second["model_version_id"]
        assert len(result["history"]) == 2
        history = client.get(
            f"/api/v1/risk/{first['focal_company_id']}/history",
            params={"since": result["latest"]["computed_at"]},
        ).json()
        assert len(history["history"]) == 1
    with get_driver().session() as session:
        count = session.run(
            "MATCH (a:Company)-[r:SUPPLIES]->(b:Company) "
            "WHERE a.uuid IN $ids AND b.uuid IN $ids RETURN count(r) AS n",
            ids=list(graph),
        ).single()["n"]
        assert count == graph.number_of_edges()


def test_unscored_and_missing_projection_states(seeded):
    identifier = uuid4()
    try:
        with SessionLocal.begin() as db:
            db.add(
                Company(id=identifier, neo4j_id=str(identifier), name="Unscored", is_synthetic=True)
            )
        with TestClient(app) as client:
            risk = client.get(f"/api/v1/risk/{identifier}").json()
            assert risk["latest"] is None and risk["history"] == []
            assert client.get(f"/api/v1/graph/{identifier}").status_code == 409
    finally:
        with SessionLocal.begin() as db:
            db.execute(delete(Company).where(Company.id == identifier))


def test_database_rejects_out_of_range_score(seeded):
    _, result = seeded
    with SessionLocal() as db:
        original = db.scalar(
            select(RiskScore).where(RiskScore.company_id == UUID(result["focal_company_id"]))
        )
        original.score = 1.1
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
