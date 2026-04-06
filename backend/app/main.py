"""
Vaidya — AI Multilingual Medical Triage
Main application entrypoint
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine, Base
from app.core.redis import redis_client
from app.core.logging import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    configure_logging()
    logger.info("vaidya.startup", env=settings.ENV, version=settings.VERSION)

    # Create all tables (Alembic handles migrations in prod)
    if settings.ENV == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("vaidya.db.tables_synced")

    # Verify Redis connection
    await redis_client.ping()
    logger.info("vaidya.redis.connected")

    yield

    # Teardown
    await engine.dispose()
    await redis_client.aclose()
    logger.info("vaidya.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vaidya API",
        description="AI-powered multilingual medical triage for rural India",
        version=settings.VERSION,
        docs_url="/docs" if settings.ENV != "production" else None,
        redoc_url="/redoc" if settings.ENV != "production" else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── CORS ────────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Prometheus metrics ───────────────────────────────────────────────────────
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # ── Routes ───────────────────────────────────────────────────────────────────
    app.include_router(api_router, prefix="/api/v1")

    # ── Health check (no auth, no prefix) ───────────────────────────────────────
    @app.get("/health", tags=["health"])
    async def health(request: Request):
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

        return {
            "status": "ok",
            "version": settings.VERSION,
            "env": settings.ENV,
            "redis": "ok" if redis_ok else "degraded",
        }

    return app


app = create_app()
