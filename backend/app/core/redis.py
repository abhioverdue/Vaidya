"""
Vaidya — Redis client
Used for: session cache, rate limiting, Celery broker
"""

import redis.asyncio as aioredis
from app.core.config import settings


redis_client: aioredis.Redis = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=5,
    socket_keepalive=True,
    health_check_interval=30,
)


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency — yields the shared Redis client."""
    yield redis_client
