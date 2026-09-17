"""
Redis client wrapper. `redis.from_url()` does not connect eagerly, so importing this
module never requires a live Redis instance. Used for: Celery result/cache lookups
outside the broker itself, rate limiting (middleware/rate_limit.py), and pub/sub
(simulation/streaming.py).
"""
import redis

from app.config import get_settings

settings = get_settings()

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client
