"""structlog setup. JSON renderer in production, console renderer in development.
Correlation ID is bound per-request by app.middleware.correlation_id and shows up in
every log line and every error response emitted during that request.
"""
import logging
import sys

import structlog
from structlog.typing import Processor

from app.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    is_prod = settings.ENVIRONMENT == "production"

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    final_processor: Processor = (
        structlog.processors.JSONRenderer() if is_prod else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=shared_processors + [final_processor],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
