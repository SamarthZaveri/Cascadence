"""Explicit development cleanup; preview by default. Real observations and model files survive."""

from sqlalchemy import delete, func, or_, select

from app.config import get_settings
from app.db.neo4j_client import get_driver
from app.db.postgres import SessionLocal
from app.models import (
    Company,
    CompanyLocation,
    DisruptionCase,
    RiskScore,
    Signal,
    SupplyRelationship,
)
from app.services.gnn.queries import REAL_INPUT_BASIS
from app.services.gnn.registry import INPUT_BASIS
from app.services.ingestion.repository import writer_lock


def cleanup_synthetic(apply=False):
    if get_settings().ENVIRONMENT != "development":
        raise ValueError("Cleanup requires development environment")
    with writer_lock(), SessionLocal.begin() as db:
        fake = list(db.scalars(select(Company.id).where(Company.is_synthetic.is_(True))))
        signals = list(db.scalars(select(Signal.id).where(Signal.company_id.in_(fake))))
        rules = [
            (
                SupplyRelationship,
                or_(
                    SupplyRelationship.provenance == "synthetic",
                    SupplyRelationship.supplier_id.in_(fake),
                    SupplyRelationship.customer_id.in_(fake),
                    SupplyRelationship.source_signal_id.in_(signals),
                ),
            ),
            (
                RiskScore,
                or_(RiskScore.company_id.in_(fake),
                    RiskScore.input_basis.not_in([REAL_INPUT_BASIS, INPUT_BASIS])),
            ),
            (CompanyLocation, CompanyLocation.company_id.in_(fake)),
            (DisruptionCase, DisruptionCase.company_id.in_(fake)),
            (Signal, Signal.id.in_(signals)),
            (Company, Company.id.in_(fake)),
        ]
        counts = {
            m.__tablename__: db.scalar(select(func.count()).select_from(m).where(q))
            for m, q in rules
        }
        with get_driver().session() as session:
            params = {"ids": [str(i) for i in fake], "signals": [str(i) for i in signals]}
            condition = "c.is_synthetic=true OR c.uuid IN $ids"
            record = session.run(
                "MATCH (c:Company) WHERE " + condition + " RETURN count(c) AS n", parameters=params
            ).single()
            graph_count = record["n"] if record else 0
            if apply:

                def purge(tx):
                    tx.run(
                        "MATCH (c:Company) WHERE " + condition + " DETACH DELETE c", **params
                    ).consume()
                    tx.run(
                        "MATCH (s:Signal) WHERE s.uuid IN $signals DETACH DELETE s", **params
                    ).consume()
                    tx.run(
                        "MATCH ()-[r:SUPPLIES]->() WHERE r.provenance='synthetic' DELETE r"
                    ).consume()

                session.execute_write(purge)
        if apply:
            for model, rule in rules:
                db.execute(delete(model).where(rule))
        return {
            "mode": "applied" if apply else "preview",
            "sql_rows": counts,
            "neo4j_synthetic_companies": graph_count,
        }
