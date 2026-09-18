"""Idempotent projection of synthetic companies into the two authoritative stores."""

from uuid import UUID

import networkx as nx
from sqlalchemy.dialects.postgresql import insert

from app.db.neo4j_client import get_driver
from app.db.postgres import SessionLocal
from app.models import Company


def persist_network(graph: nx.DiGraph) -> None:
    if not graph:
        raise ValueError("Cannot persist an empty network")
    nodes = [dict(data) for _, data in graph.nodes(data=True)]
    if any(not node["is_synthetic"] for node in nodes):
        raise ValueError("Demo writer only accepts synthetic companies")
    with SessionLocal.begin() as db:
        for node in nodes:
            values = dict(
                id=UUID(node["uuid"]),
                neo4j_id=node["uuid"],
                name=node["name"],
                industry=node["industry"],
                hq_country=node.get("hq_country"),
                is_synthetic=True,
            )
            statement = insert(Company).values(**values)
            db.execute(
                statement.on_conflict_do_update(
                    index_elements=[Company.id], set_={k: v for k, v in values.items() if k != "id"}
                )
            )
    edges = [dict(source=u, target=v, **data) for u, v, data in graph.edges(data=True)]
    with get_driver().session() as session:
        session.run(
            "CREATE CONSTRAINT company_uuid IF NOT EXISTS FOR (c:Company) REQUIRE c.uuid IS UNIQUE"
        ).consume()

        def write(tx):
            tx.run(
                "UNWIND $nodes AS n MERGE (c:Company {uuid:n.uuid}) "
                "SET c.name=n.name, c.industry=n.industry, "
                "c.is_synthetic=n.is_synthetic, c.tier=n.tier",
                nodes=nodes,
            ).consume()
            # Replace only edges inside this exact deterministic generated network.
            tx.run(
                "MATCH (a:Company)-[r:SUPPLIES]->(b:Company) "
                "WHERE a.uuid IN $ids AND b.uuid IN $ids DELETE r",
                ids=list(graph.nodes),
            ).consume()
            tx.run(
                "UNWIND $edges AS e MATCH (a:Company {uuid:e.source}), "
                "(b:Company {uuid:e.target}) MERGE (a)-[r:SUPPLIES]->(b) "
                "SET r.criticality=e.criticality, r.relationship_type=e.relationship_type, "
                "r.since=date(e.since)",
                edges=edges,
            ).consume()

        session.execute_write(write)


def read_network(company_ids: list[str]) -> nx.DiGraph:
    """Inference uses the persisted Neo4j projection, not the generator's in-memory graph."""
    graph = nx.DiGraph()
    with get_driver().session() as session:
        for row in session.run(
            "MATCH (c:Company) WHERE c.uuid IN $ids RETURN properties(c) AS n", ids=company_ids
        ):
            graph.add_node(row["n"]["uuid"], **row["n"])
        for row in session.run(
            "MATCH (a:Company)-[r:SUPPLIES]->(b:Company) "
            "WHERE a.uuid IN $ids AND b.uuid IN $ids "
            "RETURN a.uuid AS source, b.uuid AS target, properties(r) AS edge",
            ids=company_ids,
        ):
            edge = dict(row["edge"])
            if hasattr(edge.get("since"), "to_native"):
                edge["since"] = edge["since"].to_native()
            graph.add_edge(row["source"], row["target"], **edge)
    if set(graph.nodes) != set(company_ids):
        raise RuntimeError("Neo4j projection is incomplete; rerun seeding")
    return graph
