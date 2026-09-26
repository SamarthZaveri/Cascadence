from app.celery_app import celery_app
from app.config import get_settings
from app.services.ingestion.pipeline import run_ingestion_cycle


@celery_app.task(name="app.tasks.ingestion.ingest_sources", soft_time_limit=840, time_limit=900)
def ingest_sources(tickers: list[str], days: int = 7):
    return run_ingestion_cycle(tickers, days)


@celery_app.task(name="app.tasks.ingestion.ingest_watchlist", soft_time_limit=840, time_limit=900)
def ingest_watchlist():
    from celery import chain

    tickers = [t.strip() for t in get_settings().INGESTION_TICKERS.split(",") if t.strip()]
    if not tickers:
        return {"status": "disabled"}
    if len(tickers) > 500:
        raise ValueError("Watchlist supports at most 500 tickers")
    job = chain(*(ingest_sources.si(tickers[i : i + 5]) for i in range(0, len(tickers), 5)))()
    return {"status": "queued", "task_id": job.id, "companies": len(tickers)}
