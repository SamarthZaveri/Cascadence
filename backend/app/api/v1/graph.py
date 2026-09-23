from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import Driver
from neo4j import Query as CypherQuery
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.neo4j_client import get_driver
from app.db.postgres import get_db
from app.models import Company
from app.schemas.intelligence import GraphLink, GraphNode, GraphResponse
from app.services.gnn.queries import latest_scores_query, require_company

router = APIRouter()


@router.get("/{company_id}", response_model=GraphResponse)
def get_graph(
    company_id: UUID,
    real_only: bool = False,
    depth: int = Query(2, ge=1, le=5),
    direction: Literal["upstream", "downstream", "both"] = "upstream",
    db: Session = Depends(get_db),
    driver: Driver = Depends(get_driver),
) -> GraphResponse:
    require_company(db, company_id, real_only)
    real_ids = (
        [str(i) for i in db.scalars(select(Company.id).where(Company.is_synthetic.is_(False)))]
        if real_only
        else []
    )
    path_filter = (
        (
            "WHERE all(x IN nodes(p) WHERE x.is_synthetic=false AND x.uuid IN $real_ids) "
            "AND all(r IN relationships(p) WHERE r.provenance IN ['sec_filing','public_source'] "
            "AND size(coalesce(r.evidence_ids,[]))>0) "
        )
        if real_only
        else ""
    )
    edge_filter = (
        (
            "AND r.provenance IN ['sec_filing','public_source'] "
            "AND size(coalesce(r.evidence_ids,[]))>0 "
        )
        if real_only
        else ""
    )
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
                    f"MATCH p=(c:Company {{uuid:$id}}){pattern}(n:Company) "
                    + path_filter
                    + "RETURN DISTINCT n.uuid AS id, n.name AS name, n.tier AS tier, "
                    "n.is_synthetic AS is_synthetic LIMIT 1001",
                    timeout=10,
                ),
                id=str(company_id),
                real_ids=real_ids,
            )
        )
        if not nodes:
            raise HTTPException(
                409, "Company graph projection missing; run ingestion reconciliation"
            )
        if len(nodes) > 1000:
            raise HTTPException(422, "Graph is too large; reduce traversal depth")
        ids = [row["id"] for row in nodes]
        links = [
            GraphLink(
                source=row["source"],
                target=row["target"],
                criticality=row["criticality"],
                provenance=row["provenance"],
                evidence_ids=row["evidence_ids"],
                confidence=row["confidence"],
            )
            for row in session.run(
                "MATCH (a:Company)-[r:SUPPLIES]->(b:Company) "
                "WHERE a.uuid IN $ids AND b.uuid IN $ids "
                + edge_filter
                + "RETURN a.uuid AS source, b.uuid AS target, r.criticality AS criticality, "
                "coalesce(r.provenance, 'synthetic') AS provenance, "
                "coalesce(r.evidence_ids, []) AS evidence_ids, r.confidence AS confidence "
                "ORDER BY source, target",
                ids=ids,
            )
        ]
    latest = latest_scores_query(real_only)
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
                is_synthetic=row["is_synthetic"] is not False,
                risk_score=scores.get(UUID(row["id"])),
            )
            for row in sorted(nodes, key=lambda item: (item["tier"], item["id"]))
        ],
        links=links,
    )
