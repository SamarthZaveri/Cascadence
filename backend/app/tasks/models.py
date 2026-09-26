from app.celery_app import celery_app
from app.services.gnn.registry import score_current
from app.services.ingestion.repository import writer_lock


@celery_app.task(name="app.tasks.models.record_and_score", soft_time_limit=240, time_limit=300)
def record_and_score():
    with writer_lock():
        return score_current()
