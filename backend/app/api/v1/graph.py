from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import Driver
from neo4j import Query as CypherQuery
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.neo4j_client import get_driver
from app.db.postgres import get_db
from app.schemas.intelligence import GraphLink, GraphNode, GraphResponse
from app.services.gnn.queries import latest_scores_query, require_company

router = APIRouter()


@router.get("/{company_id}", response_model=GraphResponse)
def get_graph(
    company_id: UUID,
    depth: int = Query(2, ge=1, le=5),
    direction: Literal["upstream", "downstream", "both"] = "upstream",
    db: Session = Depends(get_db),
    driver: Driver = Depends(get_driver),
) -> GraphResponse:
    require_company(db, company_id)
    # Only validated integers and literal patterns are interpolated; IDs remain parameters.
    pattern = {
        "upstream": f"<-[:SUPPLIES*0..{depth}]-",
        "downstream": f"-[:SUPPLIES*0..{depth}]->",
        "both": f"-[:SUPPLIES*0..{depth}]-",
    }[direction]
    with driver.session() as session:
        nodes = list(
            session.run(
                CypherQuery(
                    f"MATCH (c:Company {{uuid:$id}}){pattern}(n:Company) "
                    "RETURN DISTINCT n.uuid AS id, n.name AS name, n.tier AS tier LIMIT 1001",
                    timeout=10,
                ),
                id=str(company_id),
            )
        )
        if not nodes:
            raise HTTPException(409, "Company graph projection missing; rerun seeding")
        if len(nodes) > 1000:
            raise HTTPException(422, "Graph is too large; reduce traversal depth")
        ids = [row["id"] for row in nodes]
        links = [
            GraphLink(source=row["source"], target=row["target"], criticality=row["criticality"])
            for row in session.run(
                "MATCH (a:Company)-[r:SUPPLIES]->(b:Company) "
                "WHERE a.uuid IN $ids AND b.uuid IN $ids "
                "RETURN a.uuid AS source, b.uuid AS target, r.criticality AS criticality "
                "ORDER BY source, target",
                ids=ids,
            )
        ]
    latest = latest_scores_query()
    scores = dict(
        db.execute(select(latest).where(latest.c.company_id.in_([UUID(i) for i in ids])))
        .tuples()
        .all()
    )
    return GraphResponse(
        nodes=[
            GraphNode(
                id=row["id"],
                name=row["name"],
                tier=row["tier"],
                risk_score=scores.get(UUID(row["id"])),
            )
            for row in sorted(nodes, key=lambda item: (item["tier"], item["id"]))
        ],
        links=links,
    )
