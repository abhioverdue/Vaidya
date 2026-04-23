"""
Vaidya — Triage Severity Engine  (Module 6 — complete)

Maps diagnosis + red flags + self-severity + audio signals → 5-level triage.
Assigns nearest ASHA worker via Haversine distance query on PostgreSQL.
Dispatches FCM push + Twilio SMS notifications via Celery.
Schedules follow-up reminders.

Triage levels:
  1 — Self-care at home
  2 — Monitor — revisit if worse in 24–48h
  3 — Visit PHC or GP within 48 hours
  4 — Seek urgent care within 24 hours
  5 — Emergency — go to hospital NOW or call 108

Design:
  The rule engine deliberately uses a priority cascade — each rule either
  returns immediately or falls through to the next. This makes the logic
  auditable line-by-line, which is important for CDSCO SaMD compliance.
  No ML is used in triage — only deterministic rules so decisions can be
  explained and challenged by clinicians.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AshaWorker, TriageEvent, TriageSession
from app.schemas.schemas import DiagnosisResult, TriageResponse

logger = structlog.get_logger(__name__)

# ── Disease classification tables ──────────────────────────────────────────────

# Always urgent (≥ level 3 regardless of confidence, level 4 at high confidence)
URGENT_DISEASES = {
    "Heart attack", "Myocardial Infarction", "Acute MI",
    "Pneumonia", "Dengue", "Dengue Fever",
    "Typhoid", "Typhoid Fever", "Enteric Fever",
    "Malaria", "Falciparum Malaria",
    "Tuberculosis", "Pulmonary Tuberculosis",
    "Meningitis", "Bacterial Meningitis",
    "Septicemia", "Sepsis",
    "Hepatitis", "Hepatitis A", "Hepatitis B", "Hepatitis E",
    "Chronic Cholestasis",
    "Paralysis (brain hemorrhage)", "Stroke",
    "Cholera", "Leptospirosis",
    "Acute Liver Failure", "Liver Failure",
    "Pulmonary Embolism", "Deep Vein Thrombosis",
    "Appendicitis", "Acute Appendicitis",
    "Anaphylaxis",
}

# Safe for home management at low self-reported severity
SELF_CARE_DISEASES = {
    "Common Cold", "Viral Upper Respiratory Tract Infection",
    "Acne", "Pimples",
    "Drug Reaction", "Allergic Drug Reaction",
    "Impetigo",
    "Chicken pox", "Chickenpox",
    "Fungal infection", "Tinea",
    "Allergy", "Allergic Rhinitis",
    "Gastritis", "Acute Gastritis",
    "Migraine",
    "GERD", "Acid Reflux",
    "Constipation",
}

# Red flag keywords that each trigger level 5 override
LEVEL_5_KEYWORDS = [
    "cardiac", "cardiac event", "heart attack", "myocardial",
    "meningitis", "subarachnoid", "brain hemorrhage",
    "loss of consciousness", "unconscious",
    "anaphylaxis", "throat swelling",
    "stroke", "face drooping", "slurred speech",
    "coughing blood", "haemoptysis",
    "sepsis", "septicemia",
]

# Red flag keywords that trigger level 4 (urgent, not emergency)
LEVEL_4_KEYWORDS = [
    "chest pain", "breathlessness", "difficulty breathing",
    "high fever", "jaundice", "hepatic",
    "blood in urine", "blood in stool", "bloody",
    "platelet", "dengue", "malaria",
    "diabetic wound", "pressure wound",
    "tb", "tuberculosis", "haemoptysis",
]

# Triage labels (displayed to patient)
TRIAGE_LABELS = {
    1: "Self-care — manage at home",
    2: "Monitor — rest and observe; revisit if worse",
    3: "Visit PHC or GP within 48 hours",
    4: "Seek urgent care within 24 hours — do not delay",
    5: "EMERGENCY — go to hospital NOW or call 108",
}

# Hours until ASHA follow-up per level
FOLLOWUP_HOURS = {1: 72, 2: 48, 3: 24, 4: 8, 5: 2}

# Earth radius for Haversine
_EARTH_RADIUS_KM = 6371.0


# ── Haversine distance ─────────────────────────────────────────────────────────

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two GPS coordinates in km."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi   = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Core triage rule engine ────────────────────────────────────────────────────

def compute_triage_level(
    diagnosis:      DiagnosisResult,
    self_severity:  Optional[int],
    audio_hint:     Optional[int] = None,
) -> int:
    """
    Priority-cascade rule engine — returns triage level 1–5.
    Each rule either returns immediately or falls through.

    Priority order:
      1. Red flags                (highest priority — immediate override)
      2. Self-reported extreme severity (≥ 9)
      3. Urgent disease list (confidence-weighted)
      4. Self-care disease list
      5. Low confidence / undetermined
      6. Self-severity moderate path
      7. Audio signal hint
      8. Safe default
    """

    # ── Rule 1: Red flags ────────────────────────────────────────────────────
    if diagnosis.red_flags:
        flags_text = " ".join(f.lower() for f in diagnosis.red_flags)

        # Level 5: life-threatening patterns
        if any(kw in flags_text for kw in LEVEL_5_KEYWORDS):
            logger.debug("vaidya.triage.rule", rule="red_flag_level5", flags=diagnosis.red_flags[:2])
            return 5

        # Level 4: urgent patterns
        if any(kw in flags_text for kw in LEVEL_4_KEYWORDS):
            logger.debug("vaidya.triage.rule", rule="red_flag_level4")
            return 4

        # Any red flag → at least level 4
        return 4

    # ── Rule 2: Patient-reported extreme severity ────────────────────────────
    if self_severity is not None and self_severity >= 9:
        logger.debug("vaidya.triage.rule", rule="extreme_severity", severity=self_severity)
        return 4

    # ── Rule 3: Urgent disease list ─────────────────────────────────────────
    disease = diagnosis.primary_diagnosis or ""
    disease_lower = disease.lower()

    is_urgent = any(d.lower() in disease_lower for d in URGENT_DISEASES)
    if is_urgent:
        if diagnosis.confidence >= 0.70:
            logger.debug("vaidya.triage.rule", rule="urgent_high_conf", disease=disease)
            return 4
        # Urgent disease at lower confidence — still needs PHC, not emergency
        logger.debug("vaidya.triage.rule", rule="urgent_low_conf", disease=disease)
        return 3

    # ── Rule 4: Self-care disease list ──────────────────────────────────────
    is_self_care = any(d.lower() in disease_lower for d in SELF_CARE_DISEASES)
    if is_self_care:
        if self_severity is not None and self_severity >= 6:
            return 2
        return 1

    # ── Rule 5: Low confidence / undetermined ───────────────────────────────
    if (
        diagnosis.confidence < 0.40
        or "undetermined" in disease_lower
        or "unknown" in disease_lower
        or disease == ""
    ):
        logger.debug("vaidya.triage.rule", rule="low_confidence", confidence=diagnosis.confidence)
        return 3

    # ── Rule 6: Self-severity path ───────────────────────────────────────────
    if self_severity is not None:
        if self_severity >= 8:
            return 4
        if self_severity >= 6:
            return 3
        if self_severity >= 4:
            return 2
        return 1

    # ── Rule 7: Audio signal hint ────────────────────────────────────────────
    if audio_hint is not None and audio_hint >= 3:
        return audio_hint   # use the hint directly

    # ── Rule 8: Safe default ─────────────────────────────────────────────────
    return 2


def build_triage_reasoning(
    diagnosis:     DiagnosisResult,
    self_severity: Optional[int],
    level:         int,
) -> str:
    """
    Build a human-readable explanation of the triage decision.
    Kept to 2–3 sentences for readability on a mobile screen.
    """
    parts = []

    if diagnosis.red_flags:
        first_flag = diagnosis.red_flags[0]
        parts.append(f"Warning: {first_flag}.")

    parts.append(
        f"{diagnosis.primary_diagnosis} identified "
        f"({round(diagnosis.confidence * 100)}% confidence)."
    )

    if self_severity is not None:
        parts.append(f"Patient reported severity {self_severity}/10.")

    action = {
        1: "Rest at home and monitor symptoms.",
        2: "Monitor closely — visit a doctor if symptoms worsen within 24–48h.",
        3: "Please visit your nearest PHC or doctor within 48 hours.",
        4: "Seek medical care within 24 hours — do not delay.",
        5: "This is an emergency. Call 108 or go to the nearest hospital immediately.",
    }[level]

    parts.append(action)
    return " ".join(parts)


# ── ASHA worker assignment ─────────────────────────────────────────────────────

async def find_nearest_asha(
    patient_lat:  float,
    patient_lng:  float,
    district_code: Optional[str],
    db:           AsyncSession,
    max_radius_km: float = 25.0,
) -> Optional[dict]:
    """
    Find the nearest active ASHA worker to the patient's GPS coordinates.

    Strategy:
      1. Try native SQL Haversine query (fast, O(n) but n is small per district)
      2. Fall back to Python-side Haversine if DB query fails
      3. Prefer workers in same district_code for cultural/language match
    """
    try:
        # Haversine in SQL using the law of cosines approximation
        # (PostGIS not required — works on plain PostgreSQL)
        result = await db.execute(
            text("""
                SELECT
                    id,
                    name,
                    phone,
                    village,
                    district_code,
                    fcm_token,
                    latitude,
                    longitude,
                    (
                        6371.0 * acos(
                            LEAST(1.0,
                                cos(radians(:lat)) * cos(radians(latitude)) *
                                cos(radians(longitude) - radians(:lng)) +
                                sin(radians(:lat)) * sin(radians(latitude))
                            )
                        )
                    ) AS distance_km
                FROM asha_workers
                WHERE active = TRUE
                  AND (district_code = :district OR :district IS NULL)
                ORDER BY distance_km ASC
                LIMIT 3
            """),
            {"lat": patient_lat, "lng": patient_lng, "district": district_code},
        )
        rows = result.mappings().all()

        if not rows:
            # Broaden search — remove district filter
            result2 = await db.execute(
                text("""
                    SELECT id, name, phone, village, district_code, fcm_token,
                           latitude, longitude,
                           (6371.0 * acos(LEAST(1.0,
                               cos(radians(:lat)) * cos(radians(latitude)) *
                               cos(radians(longitude) - radians(:lng)) +
                               sin(radians(:lat)) * sin(radians(latitude))
                           ))) AS distance_km
                    FROM asha_workers
                    WHERE active = TRUE
                    ORDER BY distance_km ASC
                    LIMIT 1
                """),
                {"lat": patient_lat, "lng": patient_lng},
            )
            rows = result2.mappings().all()

        if not rows:
            return None

        nearest = rows[0]
        dist = float(nearest["distance_km"])

        if dist > max_radius_km:
            logger.warning(
                "vaidya.triage.asha_too_far",
                distance_km=round(dist, 1),
                max_km=max_radius_km,
            )
            # Still return — patient should know there's an ASHA even if far
            # (in practice for rural India 25km may be the nearest worker)

        return {
            "id":           str(nearest["id"]),
            "name":         nearest["name"],
            "phone":        nearest["phone"],
            "village":      nearest["village"],
            "district_code": nearest["district_code"],
            "fcm_token":    nearest["fcm_token"],
            "distance_km":  round(dist, 2),
            "latitude":     float(nearest["latitude"]),
            "longitude":    float(nearest["longitude"]),
        }

    except Exception as exc:
        logger.error("vaidya.triage.asha_query_failed", error=str(exc))

        # Python-side fallback — load all active workers and sort
        try:
            all_workers = (await db.execute(
                select(AshaWorker).where(AshaWorker.active == True).limit(200)
            )).scalars().all()

            if not all_workers:
                return None

            with_dist = [
                (w, haversine_km(patient_lat, patient_lng, w.latitude, w.longitude))
                for w in all_workers
            ]
            with_dist.sort(key=lambda x: x[1])
            w, dist = with_dist[0]

            return {
                "id":           str(w.id),
                "name":         w.name,
                "phone":        w.phone,
                "village":      w.village,
                "district_code": w.district_code,
                "fcm_token":    w.fcm_token,
                "distance_km":  round(dist, 2),
                "latitude":     w.latitude,
                "longitude":    w.longitude,
            }
        except Exception as exc2:
            logger.error("vaidya.triage.asha_python_fallback_failed", error=str(exc2))
            return None


# ── Notification dispatch ──────────────────────────────────────────────────────

def dispatch_asha_notification(
    session_id:    str,
    asha_worker:   dict,
    triage_level:  int,
    diagnosis:     str,
    patient_info:  Optional[dict] = None,
) -> None:
    """
    Enqueue FCM push + Twilio SMS notification to the assigned ASHA worker.
    This is a fire-and-forget Celery dispatch — does not block the API response.
    Only fires for triage level 3+ (clinically relevant threshold).
    """
    if triage_level < 3:
        logger.debug("vaidya.triage.notification_skipped", level=triage_level)
        return

    from app.worker.tasks import (
        notify_asha_fcm,
        notify_asha_sms,
        schedule_followup,
    )

    worker_id   = asha_worker.get("id", "")
    fcm_token   = asha_worker.get("fcm_token")
    phone       = asha_worker.get("phone", "")
    worker_name = asha_worker.get("name", "ASHA worker")

    logger.info(
        "vaidya.triage.notification_dispatch",
        session_id=session_id[:8],
        worker=worker_name,
        level=triage_level,
        has_fcm=bool(fcm_token),
        has_phone=bool(phone),
    )

    # FCM push notification (primary channel — instant)
    if fcm_token:
        notify_asha_fcm.apply_async(
            args=[session_id, worker_id, fcm_token, triage_level, diagnosis],
            countdown=0,
            queue="notifications",
        )

    # Twilio SMS fallback (for ASHA workers without smartphone)
    if phone:
        notify_asha_sms.apply_async(
            args=[session_id, phone, worker_name, triage_level, diagnosis],
            countdown=2,   # slight delay so FCM goes first
            queue="notifications",
        )

    # Schedule follow-up reminder
    follow_up_delay = FOLLOWUP_HOURS[triage_level] * 3600
    schedule_followup.apply_async(
        args=[session_id, worker_id, triage_level],
        countdown=follow_up_delay,
        queue="followups",
    )


# ── Triage event logger ────────────────────────────────────────────────────────

async def log_triage_event(
    session_id:    UUID,
    triage_level:  int,
    diagnosis:     str,
    district_code: Optional[str],
    state_code:    Optional[str],
    language:      str,
    age_group:     Optional[str],
    db:            AsyncSession,
) -> None:
    """
    Write an anonymised TriageEvent row for district-level analytics.
    No PII — just disease, level, district, language.
    Used by the health officer dashboard and outbreak detection (Module 9).
    """
    try:
        event = TriageEvent(
            session_id=session_id,
            event_time=datetime.now(timezone.utc),
            district_code=district_code,
            state_code=state_code,
            diagnosis=diagnosis[:200] if diagnosis else None,
            triage_level=triage_level,
            input_language=language,
            age_group=age_group,
        )
        db.add(event)
        logger.debug("vaidya.triage.event_logged", level=triage_level, district=district_code)
    except Exception as exc:
        logger.warning("vaidya.triage.event_log_failed", error=str(exc))


# ── Main public API ────────────────────────────────────────────────────────────

async def compute_triage(
    diagnosis:       DiagnosisResult,
    self_severity:   Optional[int],
    patient_id:      Optional[UUID],
    db:              AsyncSession,
    patient_lat:     Optional[float] = None,
    patient_lng:     Optional[float] = None,
    district_code:   Optional[str] = None,
    state_code:      Optional[str] = None,
    language:        str = "en",
    age_group:       Optional[str] = None,
    session_id:      Optional[UUID] = None,
    audio_hint:      Optional[int] = None,
) -> TriageResponse:
    """
    Full triage pipeline:
      1. Compute triage level via rule cascade
      2. Build human-readable reasoning
      3. Find nearest ASHA worker (Haversine SQL query)
      4. Dispatch FCM + SMS notifications via Celery
      5. Log anonymised TriageEvent for analytics
      6. Return TriageResponse

    Args:
        diagnosis:     fused DiagnosisResult from fusion engine
        self_severity: patient-reported 1–10 severity
        patient_id:    patient UUID (optional — for anonymous sessions)
        db:            async SQLAlchemy session
        patient_lat:   GPS latitude (from mobile app)
        patient_lng:   GPS longitude (from mobile app)
        district_code: NHM district code (fallback if no GPS)
        state_code:    state code for ASHA filtering
        language:      patient language for notification localisation
        age_group:     "child"|"adult"|"senior" for analytics
        session_id:    triage session UUID (for event logging)
        audio_hint:    triage level hint from audio model (1–5)
    """
    # ── Step 1: Compute level ────────────────────────────────────────────────
    level = compute_triage_level(diagnosis, self_severity, audio_hint)
    label = TRIAGE_LABELS[level]

    logger.info(
        "vaidya.triage.computed",
        level=level,
        label=label,
        disease=diagnosis.primary_diagnosis,
        confidence=round(diagnosis.confidence, 3),
        self_severity=self_severity,
        red_flags=len(diagnosis.red_flags),
    )

    # ── Step 2: Build reasoning ──────────────────────────────────────────────
    reasoning = build_triage_reasoning(diagnosis, self_severity, level)

    # ── Step 3: ASHA assignment ──────────────────────────────────────────────
    asha_assigned = None
    if level >= 3:  # only for PHC+ triage levels
        if patient_lat is not None and patient_lng is not None:
            asha_assigned = await find_nearest_asha(
                patient_lat=patient_lat,
                patient_lng=patient_lng,
                district_code=district_code,
                db=db,
            )
        elif district_code:
            # No GPS — find any active ASHA in the same district
            try:
                result = await db.execute(
                    select(AshaWorker)
                    .where(AshaWorker.active == True)
                    .where(AshaWorker.district_code == district_code)
                    .limit(1)
                )
                worker = result.scalar_one_or_none()
                if worker:
                    asha_assigned = {
                        "id":           str(worker.id),
                        "name":         worker.name,
                        "phone":        worker.phone,
                        "village":      worker.village,
                        "district_code": worker.district_code,
                        "fcm_token":    worker.fcm_token,
                        "distance_km":  None,
                    }
            except Exception as exc:
                logger.warning("vaidya.triage.district_asha_failed", error=str(exc))

    # ── Step 4: Dispatch notifications ──────────────────────────────────────
    if asha_assigned and session_id:
        try:
            dispatch_asha_notification(
                session_id=str(session_id),
                asha_worker=asha_assigned,
                triage_level=level,
                diagnosis=diagnosis.primary_diagnosis,
            )
        except Exception as exc:
            logger.warning("vaidya.triage.notification_dispatch_failed", error=str(exc))

    # ── Step 5: Log triage event ─────────────────────────────────────────────
    if session_id:
        await log_triage_event(
            session_id=session_id,
            triage_level=level,
            diagnosis=diagnosis.primary_diagnosis,
            district_code=district_code,
            state_code=state_code,
            language=language,
            age_group=age_group,
            db=db,
        )

    # ── Step 6: Build follow-up timestamp ───────────────────────────────────
    follow_up_at = datetime.now(timezone.utc) + timedelta(hours=FOLLOWUP_HOURS[level])

    # Strip FCM token from public response
    asha_public = None
    if asha_assigned:
        asha_public = {
            "name":         asha_assigned["name"],
            "phone":        asha_assigned["phone"],
            "village":      asha_assigned.get("village"),
            "district_code": asha_assigned.get("district_code"),
            "distance_km":  asha_assigned.get("distance_km"),
        }

    return TriageResponse(
        level=level,
        label=label,
        reasoning=reasoning,
        asha_assigned=asha_public,
        follow_up_at=follow_up_at,
    )
