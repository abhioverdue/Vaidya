"""
Vaidya — security utilities
JWT token creation/validation, password hashing, Redis rate limiting
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.redis import get_redis

logger = structlog.get_logger(__name__)

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


# ── Password ───────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ────────────────────────────────────────────────────────────────────────

def create_access_token(subject: str, extra: dict | None = None) -> str:
    payload = {
        "sub": subject,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    return payload["sub"]


# ── Rate limiting (Redis sliding window) ──────────────────────────────────────

async def rate_limit(request: Request, redis=Depends(get_redis)) -> None:
    """60 requests/minute per IP — stored as Redis sorted set.
    Skips silently when Redis is unavailable (NullRedis or None)."""
    from app.core.redis import is_null_redis
    if redis is None or is_null_redis(redis):
        return

    from redis.exceptions import ConnectionError as RedisConnectionError, RedisError
    try:
        ip = request.client.host if request.client else "unknown"
        key = f"rl:{ip}"
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        window_ms = 60_000

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, now_ms - window_ms)
        pipe.zadd(key, {str(now_ms): now_ms})
        pipe.zcard(key)
        pipe.expire(key, 70)
        results = await pipe.execute()

        count = results[2]
        if count > settings.RATE_LIMIT_PER_MINUTE:
            logger.warning("vaidya.rate_limit.exceeded", ip=ip, count=count)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please wait before retrying.",
                headers={"Retry-After": "60"},
            )
    except (RedisConnectionError, RedisError) as exc:
        logger.warning("vaidya.rate_limit.redis_unavailable", error=str(exc))
