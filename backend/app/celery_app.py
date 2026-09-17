"""
Celery application object. `celery_worker` and `celery_beat` (see infra/docker-compose.yml)
both point at this module. Task modules live in app/tasks/ and register themselves via
`@celery_app.task` — none exist yet in Phase 0; the ingestion pipeline (Phase 1/2) and
alerting scheduler (Phase 9) are the first real tasks.
"""
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cascadence",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Autodiscover tasks in app/tasks/*.py once real tasks exist there.
celery_app.autodiscover_tasks(["app.tasks"])
