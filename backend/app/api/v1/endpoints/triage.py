"""
Vaidya — /api/v1/triage  (Module 6 — complete)

POST /assess            — run triage rule engine on a DiagnosisResult
GET  /session/{id}      — get triage result for a past session
POST /override          — clinician override of triage level (with audit)
GET  /levels            — return triage level definitions
GET  /stats/district    — district-level triage counts (last 24h)
POST /emergency         — fast-track level-5 emergency path
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import get_current_user_id
from app.models.models import AuditLog, TriageSession
from app.schemas.schemas import DiagnosisResult, TriageResponse
from app.services.triage.engine import (
    FOLLOWUP_HOURS,
    TRIAGE_LABELS,
    URGENT_DISEASES,
    SELF_CARE_DISEASES,
    compute_triage,
    compute_triage_level,
    build_triage_reasoning,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


# ── Request schemas ────────────────────────────────────────────────────────────

class TriageAssessRequest(BaseModel):
    diagnosis:      DiagnosisResult
    self_severity:  Optional[int]  = Field(None, ge=1, le=10)
    patient_lat:    Optional[float] = Field(None, ge=-90, le=90)
    patient_lng:    Optional[float] = Field(None, ge=-180, le=180)
    district_code:  Optional[str]  = None
    state_code:     Optional[str]  = None
    language:       str            = Field("en", pattern="^(en|hi|ta)$")
    age_group:      Optional[str]  = Field(None, pattern="^(child|adult|senior)$")
    patient_id:     Optional[str]  = None
    session_id:     Optional[str]  = None
    audio_hint:     Optional[int]  = Field(None, ge=1, le=5)


class TriageOverrideRequest(BaseModel):
    session_id:       str
    new_level:        int = Field(..., ge=1, le=5)
    override_reason:  str = Field(..., min_length=10, max_length=500)
    clinician_id:     str


class EmergencyAlertRequest(BaseModel):
    patient_lat:   Optional[float] = Field(None, ge=-90, le=90)
    patient_lng:   Optional[float] = Field(None, ge=-180, le=180)
    district_code: Optional[str]   = None
    description:   Optional[str]   = Field(None, max_length=500)
    language:      str             = Field("en", pattern="^(en|hi|ta)$")


class TriageStatsResponse(BaseModel):
    district_code:  str
    period_hours:   int
    total_sessions: int
    by_level:       dict[str, int]
    top_diagnoses:  list[dict]


# ── POST /assess ───────────────────────────────────────────────────────────────

@router.post(
    "/assess",
    response_model=TriageResponse,
    summary="Assess triage level from a diagnosis result",
)
async def assess_triage(
    payload: TriageAssessRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Run the triage rule engine on a DiagnosisResult.

    This is the standalone triage endpoint — call it directly if you have
    a diagnosis but want to recompute or re-run triage separately from the
    full /diagnose/predict pipeline.

    Priority cascade:
      1. Red flags → level 4 or 5
      2. Self-severity ≥ 9 → level 4
      3. Urgent disease (high confidence) → level 4
      4. Urgent disease (low confidence) → level 3
      5. Self-care disease → level 1 or 2
      6. Low confidence / undetermined → level 3
      7. Self-severity gradient → level 1–4
      8. Audio model hint → passed through
      9. Safe default → level 2

    ASHA worker is assigned if triage level ≥ 3 and GPS or district_code provided.
    FCM + SMS notifications dispatched asynchronously via Celery.
    """
    pid = uuid.UUID(payload.patient_id) if payload.patient_id else None
    sid = uuid.UUID(payload.session_id) if payload.session_id else None

    result = await compute_triage(
        diagnosis=payload.diagnosis,
        self_severity=payload.self_severity,
        patient_id=pid,
        db=db,
        patient_lat=payload.patient_lat,
        patient_lng=payload.patient_lng,
        district_code=payload.district_code,
        state_code=payload.state_code,
        language=payload.language,
        age_group=payload.age_group,
        session_id=sid,
        audio_hint=payload.audio_hint,
    )

    logger.info(
        "vaidya.triage_ep.assessed",
        level=result.level,
        disease=payload.diagnosis.primary_diagnosis,
        has_asha=result.asha_assigned is not None,
    )

    return result


# ── GET /session/{id} ─────────────────────────────────────────────────────────

@router.get(
    "/session/{session_id}",
    response_model=TriageResponse,
    summary="Get triage result for a past session",
)
async def get_session_triage(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the triage result for a completed session."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(400, "Invalid session ID")

    result = await db.execute(
        select(TriageSession).where(TriageSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    if not session.triage_level:
        raise HTTPException(404, "Triage not yet computed for this session")

    return TriageResponse(
        level=session.triage_level,
        label=TRIAGE_LABELS.get(session.triage_level, "Unknown"),
        reasoning=f"Retrieved from session record. Diagnosis: {session.primary_diagnosis}.",
        asha_assigned=None,
        follow_up_at=None,
    )


# ── POST /override ─────────────────────────────────────────────────────────────

@router.post(
    "/override",
    summary="Clinician override of triage level (creates audit log entry)",
)
async def override_triage(
    payload: TriageOverrideRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Allow a clinician to override the AI triage level.
    Creates an immutable audit log entry for CDSCO SaMD compliance.
    The original AI level is preserved in the audit trail.
    """
    try:
        sid = uuid.UUID(payload.session_id)
    except ValueError:
        raise HTTPException(400, "Invalid session ID")

    result = await db.execute(
        select(TriageSession).where(TriageSession.id == sid)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    original_level = session.triage_level

    # Update triage level
    session.triage_level = payload.new_level
    session.triage_label = TRIAGE_LABELS[payload.new_level]

    # Immutable audit log
    audit = AuditLog(
        event_type="triage_override",
        entity_type="triage_session",
        entity_id=str(sid),
        actor_id=payload.clinician_id,
        payload_hash=str(original_level),   # original level in hash field for simplicity
    )
    db.add(audit)
    await db.flush()

    logger.info(
        "vaidya.triage_ep.override",
        session=payload.session_id[:8],
        from_level=original_level,
        to_level=payload.new_level,
        clinician=payload.clinician_id,
    )

    return {
        "status":         "overridden",
        "session_id":     payload.session_id,
        "original_level": original_level,
        "new_level":      payload.new_level,
        "new_label":      TRIAGE_LABELS[payload.new_level],
        "reason":         payload.override_reason,
        "audit_logged":   True,
    }


# ── GET /levels ────────────────────────────────────────────────────────────────

@router.get("/levels", summary="Return all triage level definitions")
async def get_triage_levels():
    """Reference endpoint — returns triage level labels and follow-up hours."""
    return {
        "levels": [
            {
                "level":          lvl,
                "label":          TRIAGE_LABELS[lvl],
                "follow_up_hours": FOLLOWUP_HOURS[lvl],
                "asha_notified":  lvl >= 3,
                "108_recommended": lvl >= 5,
            }
            for lvl in range(1, 6)
        ],
        "urgent_disease_count": len(URGENT_DISEASES),
        "self_care_disease_count": len(SELF_CARE_DISEASES),
    }


# ── GET /stats/district ────────────────────────────────────────────────────────

@router.get(
    "/stats/district",
    summary="District-level triage stats (last N hours)",
)
async def get_district_stats(
    district_code: str = Query(..., min_length=2),
    hours:         int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns anonymised triage counts for a district in the last N hours.
    Used by the district health officer dashboard (Module 9 full analytics).
    """
    try:
        result = await db.execute(
            text("""
                SELECT
                    triage_level,
                    COUNT(*) AS count
                FROM triage_events
                WHERE district_code = :district
                  AND event_time >= NOW() - (INTERVAL '1 hour' * :hours)
                GROUP BY triage_level
                ORDER BY triage_level
            """),
            {"district": district_code, "hours": hours},
        )
        rows = result.mappings().all()
    except Exception:
        rows = []

    by_level = {str(r["triage_level"]): r["count"] for r in rows}
    total    = sum(v for v in by_level.values())

    try:
        diag_result = await db.execute(
            text("""
                SELECT diagnosis, COUNT(*) AS count
                FROM triage_events
                WHERE district_code = :district
                  AND event_time >= NOW() - INTERVAL '24 hours'
                  AND diagnosis IS NOT NULL
                GROUP BY diagnosis
                ORDER BY count DESC
                LIMIT 5
            """),
            {"district": district_code},
        )
        top_dx = [{"diagnosis": r["diagnosis"], "count": r["count"]}
                  for r in diag_result.mappings().all()]
    except Exception:
        top_dx = []

    return TriageStatsResponse(
        district_code=district_code,
        period_hours=hours,
        total_sessions=total,
        by_level=by_level,
        top_diagnoses=top_dx,
    )


# ── POST /emergency ────────────────────────────────────────────────────────────

@router.post(
    "/emergency",
    summary="Fast-track emergency alert — immediately notifies nearest ASHA + 108",
)
async def emergency_alert(
    payload: EmergencyAlertRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Emergency fast-track path — bypasses diagnosis and directly creates a
    level-5 triage event, notifies nearest ASHA worker, and returns 108 info.

    Use when a patient or bystander reports an emergency without time for
    full symptom assessment (e.g. unconscious patient, trauma, stroke signs).
    """
    session_id = uuid.uuid4()

    # Minimal diagnosis result for emergency
    emergency_dx = DiagnosisResult(
        primary_diagnosis="Emergency — clinical assessment required",
        confidence=1.0,
        differential=[],
        diagnosis_source="emergency_override",
        red_flags=[payload.description or "Patient or bystander reported emergency"],
    )

    triage = await compute_triage(
        diagnosis=emergency_dx,
        self_severity=10,
        patient_id=None,
        db=db,
        patient_lat=payload.patient_lat,
        patient_lng=payload.patient_lng,
        district_code=payload.district_code,
        language=payload.language,
        session_id=session_id,
    )

    logger.info(
        "vaidya.triage_ep.emergency",
        session=str(session_id)[:8],
        has_asha=triage.asha_assigned is not None,
        lat=payload.patient_lat,
        lng=payload.patient_lng,
    )

    return {
        "session_id":       str(session_id),
        "triage_level":     5,
        "label":            TRIAGE_LABELS[5],
        "action":           "Call 108 immediately for ambulance",
        "ambulance_number": "108",
        "asha_assigned":    triage.asha_assigned,
        "follow_up_at":     triage.follow_up_at.isoformat() if triage.follow_up_at else None,
        "nearest_hospital": "Proceed to nearest emergency department",
    }
