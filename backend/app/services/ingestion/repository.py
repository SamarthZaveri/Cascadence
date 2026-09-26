"""SQL evidence and review truth, with a repairable Neo4j projection."""

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.db.neo4j_client import get_driver
from app.db.postgres import SessionLocal, engine
from app.models import Company, Signal, SupplyRelationship


@contextmanager
def writer_lock():
    with engine.connect() as connection:
        locked = connection.execute(text("SELECT pg_try_advisory_lock(18092026)")).scalar()
        connection.commit()
        if not locked:
            raise RuntimeError("Another seed/ingestion/review writer is running; retry later")
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(18092026)"))
            connection.commit()


def company_uuid(cik: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"cascadence:sec:{int(cik)}")


def upsert_company(company: dict, profile: dict | None = None) -> UUID:
    cik = str(company["cik"]).zfill(10)
    with SessionLocal.begin() as db:
        existing = db.scalar(select(Company).where(Company.sec_cik == cik))
        identifier = existing.id if existing else company_uuid(cik)
        values = {
            "id": identifier,
            "neo4j_id": str(identifier),
            "name": company["name"],
            "ticker": company.get("ticker"),
            "sec_cik": cik,
            "is_synthetic": False,
        }
        if profile:
            sic = str(profile.get("sic", ""))
            industry = (
                "Electronics"
                if sic.startswith(("35", "36"))
                else ("Energy" if sic.startswith(("13", "29", "49")) else "Other")
            )
            values.update(
                name=profile.get("name") or company["name"], industry=industry, hq_country=None
            )
        statement = insert(Company).values(**values)
        db.execute(
            statement.on_conflict_do_update(
                index_elements=[Company.id], set_={k: v for k, v in values.items() if k != "id"}
            )
        )
        return identifier


def save_signal(values: dict):
    with SessionLocal.begin() as db:
        db.execute(
            insert(Signal)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Signal.id])
        )


def save_relationship(candidate: dict, source_signal_id: UUID) -> UUID:
    supplier, customer = (
        upsert_company(candidate["supplier"]),
        upsert_company(candidate["customer"]),
    )
    identifier = uuid5(NAMESPACE_URL, f"supply:{source_signal_id}:{supplier}:{customer}")
    with SessionLocal.begin() as db:
        db.execute(
            insert(SupplyRelationship)
            .values(
                id=identifier,
                supplier_id=supplier,
                customer_id=customer,
                source_signal_id=source_signal_id,
                relationship_type=candidate["relationship_type"],
                criticality=0.5,
                confidence=candidate["confidence"],
                evidence=candidate["evidence"],
                status="pending",
                provenance="sec_filing",
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=[SupplyRelationship.id])
        )
    return identifier


def reconcile() -> dict:
    with SessionLocal() as db:
        nodes = [
            {
                "uuid": str(c.id),
                "name": c.name,
                "industry": c.industry or "Other",
                "is_synthetic": c.is_synthetic,
                "tier": 1 if c.is_synthetic else -1,
            }
            for c in db.scalars(select(Company))
        ]
        signals = [
            {
                "uuid": str(s.id),
                "company": str(s.company_id),
                "source_type": s.source_type,
                "severity": s.severity_score,
                "observed_at": s.observed_at,
            }
            for s in db.scalars(select(Signal).where(Signal.company_id.is_not(None)))
        ]
        edges: dict[tuple[str, str], dict] = {}
        for edge in db.scalars(
            select(SupplyRelationship)
            .where(SupplyRelationship.status == "approved")
            .order_by(SupplyRelationship.created_at, SupplyRelationship.id)
        ):
            key = (str(edge.supplier_id), str(edge.customer_id))
            if key not in edges:
                edges[key] = {"source": key[0], "target": key[1], "evidence_ids": []}
            edges[key].update(
                relationship_type=edge.relationship_type,
                criticality=edge.criticality,
                provenance=edge.provenance,
                confidence=edge.confidence,
                since=edge.created_at.date(),
            )
            if edge.source_signal_id:
                edges[key]["evidence_ids"].append(str(edge.source_signal_id))
    with get_driver().session() as session:
        session.run(
            "CREATE CONSTRAINT company_uuid IF NOT EXISTS FOR (c:Company) REQUIRE c.uuid IS UNIQUE"
        ).consume()
        session.run(
            "CREATE CONSTRAINT signal_uuid IF NOT EXISTS FOR (s:Signal) REQUIRE s.uuid IS UNIQUE"
        ).consume()

        def project(tx):
            tx.run(
                "UNWIND $rows AS n MERGE (c:Company {uuid:n.uuid}) "
                "ON CREATE SET c.tier=n.tier SET c.name=n.name,c.industry=n.industry,"
                "c.is_synthetic=n.is_synthetic",
                rows=nodes,
            ).consume()
            tx.run(
                "UNWIND $rows AS n MATCH (c:Company {uuid:n.company}) "
                "MERGE (s:Signal {uuid:n.uuid}) SET s.source_type=n.source_type,"
                "s.severity=n.severity,s.observed_at=n.observed_at MERGE (c)-[:AFFECTED_BY]->(s)",
                rows=signals,
            ).consume()
            tx.run("MATCH ()-[r:SUPPLIES {managed_by:'phase2'}]->() DELETE r").consume()
            tx.run(
                "UNWIND $rows AS e MATCH (a:Company {uuid:e.source}), (b:Company {uuid:e.target}) "
                "MERGE (a)-[r:SUPPLIES]->(b) SET r.managed_by='phase2',"
                "r.relationship_type=e.relationship_type,r.criticality=e.criticality,"
                "r.since=e.since,r.since_basis='first_recorded',r.provenance=e.provenance,"
                "r.confidence=e.confidence,r.evidence_ids=e.evidence_ids",
                rows=list(edges.values()),
            ).consume()

        session.execute_write(project)
    return {"companies": len(nodes), "signals": len(signals), "approved_edges": len(edges)}


def review_relationship(identifier: UUID, decision: str) -> dict:
    if decision not in {"approved", "rejected"}:
        raise ValueError("Invalid decision")
    with writer_lock():
        with SessionLocal.begin() as db:
            edge = db.get(SupplyRelationship, identifier)
            if edge is None:
                raise ValueError("Relationship not found")
            edge.status, edge.reviewed_at = decision, datetime.now(UTC)
        return reconcile()


def augment(company_id: UUID, count: int = 5) -> dict:
    if not 1 <= count <= 20:
        raise ValueError("Synthetic supplier count must be 1–20")
    with writer_lock():
        with SessionLocal.begin() as db:
            focal = db.get(Company, company_id)
            if focal is None or focal.is_synthetic:
                raise ValueError("Select an existing real company")
            for index in range(count):
                supplier = uuid5(NAMESPACE_URL, f"cascadence:synthetic-feeder:{company_id}:{index}")
                db.execute(
                    insert(Company)
                    .values(
                        id=supplier,
                        neo4j_id=str(supplier),
                        name=f"DEMO supplier {index + 1:02d} for {focal.ticker or focal.name}",
                        industry="Manufacturing",
                        is_synthetic=True,
                    )
                    .on_conflict_do_nothing(index_elements=[Company.id])
                )
                db.execute(
                    insert(SupplyRelationship)
                    .values(
                        id=uuid5(NAMESPACE_URL, f"demo-supply:{supplier}:{company_id}"),
                        supplier_id=supplier,
                        customer_id=company_id,
                        relationship_type="component",
                        criticality=0.5,
                        confidence=1.0,
                        evidence="Explicit synthetic demo augmentation",
                        status="approved",
                        provenance="synthetic",
                        created_at=datetime.now(UTC),
                    )
                    .on_conflict_do_nothing(index_elements=[SupplyRelationship.id])
                )
        return reconcile()
