from app.celery_app import celery_app
from app.config import get_settings
from app.services.extra_signals.cli import default_dates
from app.services.extra_signals.pipeline import collect


@celery_app.task(
    name="app.tasks.observations.collect_watchlist", soft_time_limit=3300, time_limit=3600
)
def collect_watchlist():
    s = get_settings()
    locations = [x.strip() for x in s.PHASE3_LOCATIONS.split(",") if x.strip()]
    if not locations or s.ENVIRONMENT != "development":
        return {"status": "disabled"}
    sources = []
    if s.COPERNICUS_CLIENT_ID and s.COPERNICUS_CLIENT_SECRET:
        sources.append("satellite")
    if s.EARTHDATA_TOKEN:
        sources.append("viirs")
    return collect(locations, sources, *default_dates()) if sources else {"status": "disabled"}
