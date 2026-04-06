"""
Vaidya — /api/v1/patients  (Module 7 — complete)

POST /                  — create or upsert a patient record (keyed on ABDM Health ID)
GET  /{id}              — fetch patient profile (no raw PII in response)
PATCH /{id}             — update language / district / demographics
GET  /{id}/sessions     — anonymised session history for returning patient
POST /consent           — record DPDP Act 2023 consent decision
DELETE /{id}            — right-to-delete (DPDP §12): wipes PII, keeps aggregates
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import ConsentLog, Patient, TriageSession

router = APIRouter()
logger = structlog.get_logger(__name__)


# ── Request / Response schemas ─────────────────────────────────────────────────

class PatientCreate(BaseModel):
    abdm_health_id:     Optional[str]  = Field(None, max_length=50)
    phone_number:       Optional[str]  = Field(None, min_length=10, max_length=15)
    preferred_language: str            = Field("en", pattern="^(en|hi|ta)$")
    district_code:      Optional[str]  = Field(None, max_length=10)
    state_code:         Optional[str]  = Field(None, max_length=5)
    age_group:          Optional[str]  = Field(None, pattern="^(child|adult|senior)$")
    gender:             Optional[str]  = Field(None, pattern="^(male|female|other|undisclosed)$")
    pmjay_eligible:     bool           = False


class PatientUpdate(BaseModel):
    preferred_language: Optional[str] = Field(None, pattern="^(en|hi|ta)$")
    district_code:      Optional[str] = Field(None, max_length=10)
    state_code:         Optional[str] = Field(None, max_length=5)
    age_group:          Optional[str] = Field(None, pattern="^(child|adult|senior)$")
    gender:             Optional[str] = Field(None, pattern="^(male|female|other|undisclosed)$")
    pmjay_eligible:     Optional[bool] = None


class PatientResponse(BaseModel):
    id:                 str
    abdm_health_id:     Optional[str]
    preferred_language: str
    district_code:      Optional[str]
    state_code:         Optional[str]
    age_group:          Optional[str]
    gender:             Optional[str]
    pmjay_eligible:     bool
    created_at:         datetime
    updated_at:         Optional[datetime]

    class Config:
        from_attributes = True


class SessionSummary(BaseModel):
    session_id:         str
    created_at:         datetime
    primary_diagnosis:  Optional[str]
    triage_level:       Optional[int]
    triage_label:       Optional[str]
    input_language:     str


class ConsentRequest(BaseModel):
    patient_id:   str
    consent_type: str = Field(..., pattern="^(data_processing|anonymised_analytics|asha_contact)$")
    granted:      bool


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hash_phone(phone: str) -> str:
    normalised = "".join(c for c in phone if c.isdigit())
    return hashlib.sha256(normalised.encode()).hexdigest()


def _patient_to_response(p: Patient) -> PatientResponse:
    return PatientResponse(
        id=str(p.id),
        abdm_health_id=p.abdm_health_id,
        preferred_language=p.preferred_language,
        district_code=p.district_code,
        state_code=p.state_code,
        age_group=p.age_group,
        gender=p.gender,
        pmjay_eligible=p.pmjay_eligible,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


# ── POST / ─────────────────────────────────────────────────────────────────────

@router.post("/", response_model=PatientResponse, status_code=201,
             summary="Create or upsert a patient record (ABDM Health ID keyed)")
async def create_patient(payload: PatientCreate, request: Request,
                          db: AsyncSession = Depends(get_db)):
    phone_hash = _hash_phone(payload.phone_number) if payload.phone_number else None

    if payload.abdm_health_id:
        r = await db.execute(select(Patient).where(Patient.abdm_health_id == payload.abdm_health_id))
        existing = r.scalar_one_or_none()
        if existing:
            return _patient_to_response(existing)

    if phone_hash:
        r = await db.execute(select(Patient).where(Patient.phone_hash == phone_hash))
        existing = r.scalar_one_or_none()
        if existing:
            return _patient_to_response(existing)

    patient = Patient(
        abdm_health_id=payload.abdm_health_id,
        phone_hash=phone_hash,
        preferred_language=payload.preferred_language,
        district_code=payload.district_code,
        state_code=payload.state_code,
        age_group=payload.age_group,
        gender=payload.gender or "undisclosed",
        pmjay_eligible=payload.pmjay_eligible,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    logger.info("vaidya.patients.created", id=str(patient.id)[:8])
    return _patient_to_response(patient)


# ── GET /{id} ──────────────────────────────────────────────────────────────────

@router.get("/{patient_id}", response_model=PatientResponse,
            summary="Fetch patient profile (no PII in response)")
async def get_patient(patient_id: str, db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid patient_id UUID")
    r = await db.execute(select(Patient).where(Patient.id == pid))
    patient = r.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return _patient_to_response(patient)


# ── PATCH /{id} ────────────────────────────────────────────────────────────────

@router.patch("/{patient_id}", response_model=PatientResponse,
              summary="Update patient demographics / language preference")
async def update_patient(patient_id: str, payload: PatientUpdate,
                          db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid patient_id UUID")
    r = await db.execute(select(Patient).where(Patient.id == pid))
    patient = r.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(patient, field, value)
    patient.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(patient)
    return _patient_to_response(patient)


# ── GET /{id}/sessions ─────────────────────────────────────────────────────────

@router.get("/{patient_id}/sessions", response_model=List[SessionSummary],
            summary="Anonymised triage session history for a returning patient")
async def get_patient_sessions(patient_id: str,
                                limit: int = Query(20, ge=1, le=100),
                                offset: int = Query(0, ge=0),
                                db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid patient_id UUID")
    r = await db.execute(
        select(TriageSession)
        .where(TriageSession.patient_id == pid)
        .order_by(TriageSession.created_at.desc())
        .offset(offset).limit(limit)
    )
    sessions = r.scalars().all()
    return [
        SessionSummary(
            session_id=str(s.id),
            created_at=s.created_at,
            primary_diagnosis=s.primary_diagnosis,
            triage_level=s.triage_level,
            triage_label=s.triage_label,
            input_language=s.input_language,
        )
        for s in sessions
    ]


# ── POST /consent ──────────────────────────────────────────────────────────────

@router.post("/consent", status_code=201,
             summary="Record DPDP Act 2023 consent decision (grant or withdraw)")
async def record_consent(payload: ConsentRequest, request: Request,
                          db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(payload.patient_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid patient_id UUID")
    r = await db.execute(select(Patient).where(Patient.id == pid))
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found")
    ip = request.client.host if request.client else None
    db.add(ConsentLog(patient_id=pid, consent_type=payload.consent_type,
                      granted=payload.granted, ip_address=ip, version="1.0"))
    await db.commit()
    logger.info("vaidya.patients.consent_recorded", patient=str(pid)[:8],
                type=payload.consent_type, granted=payload.granted)
    return {"status": "recorded", "consent_type": payload.consent_type,
            "granted": payload.granted, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── DELETE /{id} — DPDP §12 right to erasure ──────────────────────────────────

@router.delete("/{patient_id}",
               summary="Right-to-delete: wipe PII, preserve anonymised aggregates (DPDP §12)")
async def delete_patient(patient_id: str, db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid patient_id UUID")
    r = await db.execute(select(Patient).where(Patient.id == pid))
    patient = r.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Wipe identifying fields — keep anonymised triage aggregates
    patient.abdm_health_id = None
    patient.phone_hash = None
    patient.updated_at = datetime.now(timezone.utc)

    sr = await db.execute(select(TriageSession).where(TriageSession.patient_id == pid))
    for s in sr.scalars().all():
        s.raw_text = None
        s.audio_file_path = None
        s.image_file_path = None

    await db.commit()
    logger.info("vaidya.patients.pii_erased", patient=str(pid)[:8])
    return {
        "status": "erased",
        "patient_id": patient_id,
        "erased_fields": ["abdm_health_id", "phone_hash", "raw_text",
                          "audio_file_path", "image_file_path"],
        "retained": "anonymised triage aggregates (TriageEvent, AuditLog, ConsentLog)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
