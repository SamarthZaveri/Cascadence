"""
Prometheus metrics. `instrument_app()` wires up auto HTTP metrics via
prometheus-fastapi-instrumentator. The custom metrics below are declared here so every
service module that needs them imports from one place instead of redefining collectors
(Prometheus client raises on duplicate registration).
"""

from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# Time spent running GNN inference for a workspace, in seconds.
gnn_inference_duration_seconds = Histogram(
    "gnn_inference_duration_seconds",
    "Time spent running GNN inference",
)

# Count of ingested signals, labeled by source_type (sec_filing, news, satellite, ais, viirs).
ingestion_signals_processed_total = Counter(
    "ingestion_signals_processed_total",
    "Signals processed by the ingestion pipeline",
    labelnames=["source_type"],
)

# Current count of active (unacknowledged, is_active) alerts.
active_alerts_total = Gauge(
    "active_alerts_total",
    "Currently active alerts",
)

# Distribution of risk scores currently in the system — used for model-drift monitoring.
model_risk_score_distribution = Histogram(
    "model_risk_score_distribution",
    "Distribution of computed risk scores (0-1)",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)


def instrument_app(app) -> None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
