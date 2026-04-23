"""
Vaidya — /api/v1/care

GET  /hospitals              — ranked hospitals + PHCs via OSM
GET  /teleconsult            — eSanjeevani OPD available slots
POST /teleconsult/book       — reserve a teleconsult slot
GET  /teleconsult/{id}/status — check booking status
POST /teleconsult/{id}/cancel — cancel a booking
GET  /geocode                — reverse geocode lat/lng → district/block
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.redis import get_redis
from app.schemas.schemas import (
    BookingConfirmation,
    HospitalListResponse,
)
from app.services.care.finder import find_nearby_hospitals
from app.services.care.esanjeevani import (
    get_available_slots,
    book_slot,
    get_booking_status,
    cancel_booking,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


# ── Extended booking request ──────────────────────────────────────────────────

class BookingRequestExtended(BaseModel):
    session_id:    UUID
    slot_id:       str
    patient_name:  str     = Field(..., min_length=2, max_length=100)
    patient_phone: str     = Field(..., min_length=10, max_length=15)
    diagnosis:     str     = Field("", max_length=200)
    triage_level:  int     = Field(2, ge=1, le=5)
    language:      str     = Field("en", pattern="^(en|hi|ta)$")


# ── GET /hospitals ────────────────────────────────────────────────────────────

@router.get(
    "/hospitals",
    response_model=HospitalListResponse,
    summary="Find and rank nearby hospitals + PHCs",
)
async def get_hospitals(
    lat:          float = Query(..., ge=-90,   le=90,  description="Patient latitude"),
    lng:          float = Query(..., ge=-180,  le=180, description="Patient longitude"),
    radius_km:    int   = Query(50,  ge=1,    le=200,  description="Search radius (km)"),
    specialty:    Optional[str]  = Query(None, description="Filter by specialty (e.g. respiratory)"),
    triage_level: int   = Query(2,   ge=1,    le=5,    description="Triage urgency 1–5"),
    pmjay:        bool  = Query(False,                 description="Patient has PMJAY coverage"),
    redis=Depends(get_redis),
):
    """
    Returns ranked hospitals and PHCs near the patient's GPS location.

    Ranking: distance × government-type preference × triage urgency × PMJAY coverage.
    - Level 5 (emergency): nearest facility wins regardless of type.
    - Level 1–2 (mild): nearest govt PHC preferred.
    - PMJAY patients: empanelled hospitals boosted.

    Results cached 24h per 1 km GPS grid cell.
    """
    return await find_nearby_hospitals(
        lat=lat,
        lng=lng,
        radius_m=radius_km * 1000,
        specialty=specialty,
        triage_level=triage_level,
        pmjay_eligible=pmjay,
        redis=redis,
    )


# ── GET /teleconsult ──────────────────────────────────────────────────────────

@router.get(
    "/teleconsult",
    summary="Get available eSanjeevani teleconsult slots",
)
async def get_teleconsult_slots(
    specialty: Optional[str] = Query(None,   description="Filter by specialty"),
    language:  str           = Query("en",   pattern="^(en|hi|ta)$"),
    date:      Optional[str] = Query(None,   description="YYYY-MM-DD, defaults to today"),
):
    """
    Fetches available doctor slots from eSanjeevani OPD (free government telemedicine).
    Language filter returns doctors who speak that language.
    Falls back to demo slots when eSanjeevani API is unreachable.
    """
    slots = await get_available_slots(
        specialty=specialty,
        language=language,
        date=date,
    )
    return {
        "slots":   slots,
        "total":   len(slots),
        "platform": "eSanjeevani OPD",
        "cost":    "Free (Government of India)",
        "note":    "Slots are updated every 15 minutes. Book early — queue fills quickly.",
    }


# ── POST /teleconsult/book ────────────────────────────────────────────────────

@router.post(
    "/teleconsult/book",
    response_model=BookingConfirmation,
    summary="Book a teleconsult slot with pre-filled case summary",
)
async def book_teleconsult(payload: BookingRequestExtended):
    """
    Books a slot on eSanjeevani OPD.
    Automatically pre-fills the doctor's case summary with the Vaidya triage result
    (diagnosis, urgency level, session ID) so the doctor has context before the call.

    Returns booking ID and direct join URL.
    """
    result = await book_slot(
        slot_id=payload.slot_id,
        patient_name=payload.patient_name,
        patient_phone=payload.patient_phone,
        session_id=str(payload.session_id),
        diagnosis=payload.diagnosis,
        triage_level=payload.triage_level,
        language=payload.language,
    )

    logger.info(
        "vaidya.care.teleconsult_booked",
        session=str(payload.session_id)[:8],
        booking=result.get("booking_id"),
        status=result.get("status"),
    )

    return BookingConfirmation(
        booking_id=result["booking_id"],
        doctor_name=result.get("doctor_name", "Doctor"),
        scheduled_at=result.get(
            "scheduled_at",
            (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
        ),
        join_url=result.get("join_url", "https://esanjeevaniopd.in"),
        case_summary=result.get("case_summary", ""),
    )


# ── GET /teleconsult/{id}/status ──────────────────────────────────────────────

@router.get(
    "/teleconsult/{booking_id}/status",
    summary="Check teleconsult booking status",
)
async def teleconsult_status(booking_id: str):
    return await get_booking_status(booking_id)


# ── POST /teleconsult/{id}/cancel ─────────────────────────────────────────────

@router.post(
    "/teleconsult/{booking_id}/cancel",
    summary="Cancel a teleconsult booking",
)
async def teleconsult_cancel(
    booking_id: str,
    reason: str = Query("Patient request", max_length=200),
):
    return await cancel_booking(booking_id, reason=reason)


# ── GET /geocode ──────────────────────────────────────────────────────────────

@router.get(
    "/geocode",
    summary="Reverse geocode GPS coordinates to district/block",
)
async def geocode(
    lat: float = Query(..., ge=-90,  le=90),
    lng: float = Query(..., ge=-180, le=180),
    redis=Depends(get_redis),
):
    """
    Converts GPS coordinates to district, block, and state using Nominatim (OSM).
    Used by the frontend to display the patient's location name and by the
    analytics pipeline to populate district_code on triage events.

    Results cached 1 hour per 0.01° grid cell (~1 km resolution).
    """
    from app.services.care.overpass import reverse_geocode

    cache_key = f"geocode:{round(lat, 2)}:{round(lng, 2)}"
    cached    = await redis.get(cache_key)
    if cached:
        import json
        return json.loads(cached)

    result = await reverse_geocode(lat, lng)

    import json
    await redis.setex(cache_key, 3600, json.dumps(result))
    return result
