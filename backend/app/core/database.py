"""
Vaidya — async database engine (SQLAlchemy 2.x)

PostgreSQL (asyncpg) is used when DATABASE_URL is set in the environment.
If DATABASE_URL is empty or unset, SQLite via aiosqlite is used for local
development so the server starts without any external dependencies.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ── URL resolution ─────────────────────────────────────────────────────────────
_SQLITE_URL = "sqlite+aiosqlite:///./vaidya_local.db"

_db_url: str = settings.DATABASE_URL.strip() if settings.DATABASE_URL else ""
if not _db_url:
    _db_url = _SQLITE_URL

is_sqlite: bool = _db_url.startswith("sqlite")

# ── Engine ─────────────────────────────────────────────────────────────────────
if is_sqlite:
    # SQLite does not support pool_size / max_overflow.
    # StaticPool keeps a single connection — fine for dev/test.
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        _db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=settings.DEBUG,
        future=True,
    )
else:
    engine = create_async_engine(
        _db_url,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=settings.DEBUG,
        future=True,
        connect_args={"ssl": "require"},
    )

# ── Session factory ────────────────────────────────────────────────────────────
AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ── Base declarative class (all models inherit from this) ──────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI dependency ─────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """Yield an async DB session; rolls back on exception, closes on exit."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
