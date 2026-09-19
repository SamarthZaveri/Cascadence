from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery(
    "cascadence",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.ingestion"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
if settings.INGESTION_TICKERS.strip():
    celery_app.conf.beat_schedule = {
        "source-watchlist": {
            "task": "app.tasks.ingestion.ingest_watchlist",
            "schedule": max(3600, settings.INGESTION_INTERVAL_SECONDS),
        }
    }
