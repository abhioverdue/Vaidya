"""
Vaidya — Redis client
Used for: session cache, rate limiting, OTP storage

If Redis is unreachable at startup or during a request, the pipeline
degrades gracefully: NullRedis no-ops all cache calls so triage still
works (just without caching).  OTP endpoints explicitly refuse NullRedis
and return HTTP 503 so the caller knows OTP service is down.
"""

import structlog
import redis.asyncio as aioredis
from app.core.config import settings

logger = structlog.get_logger(__name__)


# ── No-op fallback used when Redis is unavailable ─────────────────────────────

class _NullRedis:
    """Swapped in when Redis cannot be reached. Cache operations become
    silent no-ops; the pipeline continues without caching."""
    async def get(self, key):            return None
    async def setex(self, key, ttl, v):  pass
    async def delete(self, *keys):       return 0
    async def exists(self, *keys):       return 0
    async def incr(self, key):           return 0
    async def expire(self, key, ttl):    return 0
    async def ping(self):                raise ConnectionError("NullRedis")


_null_redis = _NullRedis()


def is_null_redis(r) -> bool:
    """True when the injected Redis is the no-op fallback (Redis unreachable).
    Use this in OTP endpoints to return HTTP 503 instead of silently failing."""
    return isinstance(r, _NullRedis)


# ── Real client (lazy-connect — no I/O until first command) ──────────────────

redis_client: aioredis.Redis = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=5,
    socket_keepalive=True,
    health_check_interval=30,
)


async def get_redis():
    """FastAPI dependency — yields the real Redis client, or NullRedis on failure."""
    try:
        await redis_client.ping()
        yield redis_client
    except Exception as exc:
        logger.warning("vaidya.redis.unavailable", error=str(exc),
                       hint="caching disabled for this request")
        yield _null_redis
