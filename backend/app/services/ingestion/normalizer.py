from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5


def signal_id(source_type: str, company_id: UUID, source_key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"cascadence:signal:{source_type}:{company_id}:{source_key}")


def to_signal(
    raw: dict,
    source_type: str,
    company_id: UUID,
    source_key: str,
    extracted: dict,
    severity: float | None,
    observed_at: datetime,
) -> dict:
    if source_type not in {"sec_filing", "news", "satellite", "ais", "viirs"}:
        raise ValueError("Unknown source type")
    if observed_at.tzinfo is None or (severity is not None and not 0 <= severity <= 1):
        raise ValueError("Require aware time and finite bounded severity")
    return {
        "id": signal_id(source_type, company_id, source_key),
        "company_id": company_id,
        "source_type": source_type,
        "raw_payload": raw,
        "extracted_data": extracted,
        "severity_score": severity,
        "observed_at": observed_at,
        "ingested_at": datetime.now(UTC),
    }
