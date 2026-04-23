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

    # Create any missing tables on every startup.
    # create_all() uses IF NOT EXISTS — safe to run in all environments.
    # Alembic migrations track schema history; this is a belt-and-suspenders
    # guard so new models (e.g. `users`) appear without a manual migrate step.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("vaidya.db.tables_synced")

    # Verify Redis connection (non-fatal — Redis is optional in local dev)
    try:
        await redis_client.ping()
        logger.info("vaidya.redis.connected")
    except Exception as exc:
        logger.warning("vaidya.redis.unavailable", error=str(exc),
                       hint="caching disabled — start Redis for full functionality")

    # Eagerly warm NLP model cache so first request doesn't pay load cost
    from app.services.diagnosis.classifier import _load_model, nlp_models_loaded
    _load_model()
    if nlp_models_loaded():
        logger.info("vaidya.models.nlp_ready")
    else:
        logger.warning("vaidya.models.nlp_missing",
                       hint="place final_nlp_model.pkl, label_encoder.pkl, final_symptom_list.pkl in models/nlp/")

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

        from app.services.diagnosis.classifier import nlp_models_loaded
        return {
            "status": "ok",
            "version": settings.VERSION,
            "env": settings.ENV,
            "redis": "ok" if redis_ok else "degraded",
            "models": "ok" if nlp_models_loaded() else "degraded",
        }

    return app


app = create_app()
