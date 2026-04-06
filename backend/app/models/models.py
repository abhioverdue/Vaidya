"""
Vaidya — SQLAlchemy ORM models
Tables: patients, sessions, triage_events, hospitals, asha_workers,
        consent_log, audit_log
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, JSON, Index, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ── Patient ───────────────────────────────────────────────────────────────────
class Patient(Base):
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    abdm_health_id = Column(String(50), unique=True, nullable=True, index=True)
    phone_hash = Column(String(64), nullable=True, index=True)   # SHA-256, not raw
    preferred_language = Column(
        Enum("en", "hi", "ta", name="language_enum"), default="en"
    )
    district_code = Column(String(10), nullable=True)             # NHM district code
    state_code = Column(String(5), nullable=True)
    age_group = Column(
        Enum("child", "adult", "senior", name="age_group_enum"), nullable=True
    )
    gender = Column(
        Enum("male", "female", "other", "undisclosed", name="gender_enum"),
        default="undisclosed",
    )
    pmjay_eligible = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    sessions = relationship("TriageSession", back_populates="patient", lazy="dynamic")
    consents = relationship("ConsentLog", back_populates="patient")


# ── Triage session ─────────────────────────────────────────────────────────────
class TriageSession(Base):
    __tablename__ = "triage_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=True)

    # Raw input
    input_language = Column(String(5), nullable=False)
    raw_text = Column(Text, nullable=True)          # deleted after 30 days (DPDP)
    audio_file_path = Column(String(500), nullable=True)
    image_file_path = Column(String(500), nullable=True)

    # Extracted symptoms
    extracted_keywords = Column(JSON, default=list)    # ["fever", "cough", ...]
    symptom_vector = Column(JSON, default=dict)         # {fever: 1, cough: 1, ...}
    duration_text = Column(String(100), nullable=True)
    self_severity = Column(Integer, nullable=True)      # 1-10 from patient

    # Diagnosis output
    primary_diagnosis = Column(String(200), nullable=True)
    differential_diagnosis = Column(JSON, default=list)
    model_confidence = Column(Float, nullable=True)
    diagnosis_source = Column(
        Enum("xgboost", "audio", "vision", "llm_fallback", "llm_gemini", "fusion",
             name="diagnosis_source_enum"),
        nullable=True,
    )
    red_flags = Column(JSON, default=list)

    # Triage
    triage_level = Column(Integer, nullable=True)       # 1=self-care … 5=emergency
    triage_label = Column(String(50), nullable=True)

    # Care routing
    recommended_hospital_ids = Column(JSON, default=list)
    teleconsult_booking_id = Column(String(100), nullable=True)
    asha_worker_id = Column(
        UUID(as_uuid=True), ForeignKey("asha_workers.id"), nullable=True
    )

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    patient = relationship("Patient", back_populates="sessions")
    asha_worker = relationship("AshaWorker")
    triage_event = relationship("TriageEvent", back_populates="session", uselist=False)

    __table_args__ = (
        Index("ix_triage_sessions_created_at", "created_at"),
        Index("ix_triage_sessions_patient_id", "patient_id"),
    )


# ── Triage event (TimescaleDB hypertable — set in init.sql) ───────────────────
class TriageEvent(Base):
    __tablename__ = "triage_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("triage_sessions.id"), nullable=False
    )
    event_time = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Anonymised analytics (no PII)
    district_code = Column(String(10), nullable=True, index=True)
    state_code = Column(String(5), nullable=True)
    diagnosis = Column(String(200), nullable=True)
    triage_level = Column(Integer, nullable=True)
    input_language = Column(String(5), nullable=True)
    age_group = Column(String(10), nullable=True)

    session = relationship("TriageSession", back_populates="triage_event")

    __table_args__ = (
        Index("ix_triage_events_event_time", "event_time"),
        Index("ix_triage_events_district", "district_code"),
        Index("ix_triage_events_diagnosis", "diagnosis"),
    )


# ── Hospital ──────────────────────────────────────────────────────────────────
class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    osm_id = Column(String(50), unique=True, nullable=True)
    name = Column(String(300), nullable=False)
    name_hi = Column(String(300), nullable=True)
    name_ta = Column(String(300), nullable=True)
    hospital_type = Column(
        Enum("phc", "chc", "district", "private", "esic", "other",
             name="hospital_type_enum"),
        default="other",
    )
    address = Column(Text, nullable=True)
    district_code = Column(String(10), nullable=True, index=True)
    state_code = Column(String(5), nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    phone = Column(String(20), nullable=True)
    ambulance_108 = Column(Boolean, default=False)
    open_24h = Column(Boolean, default=False)
    specialties = Column(JSON, default=list)            # ["respiratory", "paediatrics"]
    pmjay_empanelled = Column(Boolean, default=False)
    aarogyasri_empanelled = Column(Boolean, default=False)
    last_verified = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_hospitals_location", "latitude", "longitude"),
        Index("ix_hospitals_district", "district_code"),
    )


# ── ASHA worker ────────────────────────────────────────────────────────────────
class AshaWorker(Base):
    __tablename__ = "asha_workers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nhm_id = Column(String(50), unique=True, nullable=True)     # NHM open data ID
    name = Column(String(200), nullable=False)
    phone = Column(String(20), nullable=False)
    fcm_token = Column(String(500), nullable=True)              # for push notifications
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    village = Column(String(200), nullable=True)
    district_code = Column(String(10), nullable=True, index=True)
    state_code = Column(String(5), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_asha_location", "latitude", "longitude"),
    )


# ── Consent log (DPDP Act 2023) ───────────────────────────────────────────────
class ConsentLog(Base):
    __tablename__ = "consent_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    consent_type = Column(
        Enum("data_processing", "anonymised_analytics", "asha_contact",
             name="consent_type_enum"),
        nullable=False,
    )
    granted = Column(Boolean, nullable=False)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    version = Column(String(10), default="1.0")      # policy version

    patient = relationship("Patient", back_populates="consents")


# ── Audit log (immutable append-only trail for CDSCO compliance) ──────────────
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(String(100), nullable=True)
    actor_id = Column(String(100), nullable=True)
    ip_address = Column(String(45), nullable=True)
    payload_hash = Column(String(64), nullable=True)   # SHA-256 of request body
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_log_timestamp", "timestamp"),
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )
