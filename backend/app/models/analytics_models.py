"""
Vaidya — Analytics ORM models
Tables: outbreak_baselines, outbreak_alerts, health_officer_webhooks

These are kept separate from models.py to allow optional import in alembic/env.py
without crashing if dependencies are missing.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text, JSON, Index,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ── Outbreak baseline (rolling 60-day district averages) ──────────────────────
class OutbreakBaseline(Base):
    __tablename__ = "outbreak_baselines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    district_code = Column(String(10), nullable=False, index=True)
    diagnosis = Column(String(200), nullable=False)
    # Rolling stats
    mean_daily_cases = Column(Float, nullable=False, default=0.0)
    std_daily_cases = Column(Float, nullable=False, default=0.0)
    ewma = Column(Float, nullable=False, default=0.0)          # exponential WMA
    sample_days = Column(Integer, nullable=False, default=0)
    computed_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_outbreak_baselines_district_diagnosis", "district_code", "diagnosis"),
    )


# ── Outbreak alert (triggered when spike > 2σ above baseline) ────────────────
class OutbreakAlert(Base):
    __tablename__ = "outbreak_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    district_code = Column(String(10), nullable=False, index=True)
    state_code = Column(String(5), nullable=True)
    diagnosis = Column(String(200), nullable=False)

    # Detection metadata
    z_score = Column(Float, nullable=False)          # how many σ above baseline
    observed_cases = Column(Integer, nullable=False)
    expected_cases = Column(Float, nullable=False)
    severity = Column(
        String(10), nullable=False, default="moderate"
    )  # low / moderate / high / critical

    # Status
    active = Column(Boolean, nullable=False, default=True)
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    # Spatial cluster info (DBSCAN)
    cluster_lat = Column(Float, nullable=True)
    cluster_lng = Column(Float, nullable=True)
    cluster_radius_km = Column(Float, nullable=True)

    # Webhook delivery
    webhook_sent = Column(Boolean, default=False)
    webhook_sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_outbreak_alerts_district", "district_code"),
        Index("ix_outbreak_alerts_active", "active"),
        Index("ix_outbreak_alerts_created_at", "created_at"),
    )


# ── Health officer webhook (where to POST outbreak alerts) ────────────────────
class HealthOfficerWebhook(Base):
    __tablename__ = "health_officer_webhooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    district_code = Column(String(10), nullable=False, unique=True, index=True)
    state_code = Column(String(5), nullable=True)
    officer_name = Column(String(200), nullable=True)
    officer_email = Column(String(200), nullable=True)
    webhook_url = Column(String(500), nullable=False)
    secret_token = Column(String(100), nullable=True)    # HMAC signing secret
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_ping_at = Column(DateTime(timezone=True), nullable=True)
    last_ping_ok = Column(Boolean, nullable=True)
