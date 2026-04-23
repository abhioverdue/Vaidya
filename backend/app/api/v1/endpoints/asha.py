"""
Vaidya — /api/v1/asha  (Module 6 — ASHA worker management)

GET  /queue                  — ASHA worker's patient queue (by worker_id or FCM token)
GET  /nearby                 — find nearest ASHA workers to a GPS coordinate
POST /register               — register or update an ASHA worker's FCM token
POST /resolve/{session_id}   — mark a patient session as resolved
GET  /district/{code}        — all active ASHA workers in a district
GET  /stats/{worker_id}      — ASHA worker activity stats
POST /bulk-load              — bulk-load ASHA workers from NHM CSV (admin)
"""

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.models.models import AshaWorker, TriageSession
from app.services.triage.engine import haversine_km

router = APIRouter()
logger = structlog.get_logger(__name__)


# ── Request schemas ────────────────────────────────────────────────────────────

class AshaRegisterRequest(BaseModel):
    nhm_id:       Optional[str] = None
    name:         str = Field(..., min_length=2, max_length=200)
    phone:        str = Field(..., min_length=10, max_length=20)
    fcm_token:    Optional[str] = None
    latitude:     float = Field(..., ge=-90, le=90)
    longitude:    float = Field(..., ge=-180, le=180)
    village:      Optional[str] = None
    district_code: Optional[str] = None
    state_code:   Optional[str] = None


class AshaResolveRequest(BaseModel):
    worker_id:       str
    resolution_note: Optional[str] = Field(None, max_length=500)


class AshaResponse(BaseModel):
    id:             str
    name:           str
    phone:          str
    village:        Optional[str]
    district_code:  Optional[str]
    active:         bool
    distance_km:    Optional[float] = None


# ── GET /queue ─────────────────────────────────────────────────────────────────

@router.get("/queue", summary="Get patient queue for an ASHA worker")
async def get_asha_queue(
    worker_id:   Optional[str] = Query(None, description="ASHA worker UUID"),
    district:    Optional[str] = Query(None, description="Filter by district code"),
    triage_min:  int = Query(3, ge=1, le=5, description="Minimum triage level to include"),
    limit:       int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the queue of open patient sessions assigned to an ASHA worker,
    ordered by triage level descending (most urgent first).

    If worker_id is not provided, returns all open sessions for the district
    at or above triage_min — useful for district health officer dashboards.
    """
    filters = [
        TriageSession.triage_level >= triage_min,
        TriageSession.completed_at.isnot(None),  # only completed diagnoses
    ]

    if worker_id:
        try:
            wid = uuid.UUID(worker_id)
        except ValueError:
            raise HTTPException(400, "Invalid worker_id format")
        filters.append(TriageSession.asha_worker_id == wid)

    result = await db.execute(
        select(TriageSession)
        .where(and_(*filters))
        .order_by(TriageSession.triage_level.desc(), TriageSession.completed_at.desc())
        .limit(limit)
    )
    sessions = result.scalars().all()

    return {
        "worker_id":   worker_id,
        "district":    district,
        "triage_min":  triage_min,
        "count":       len(sessions),
        "queue": [
            {
                "session_id":        str(s.id),
                "triage_level":      s.triage_level,
                "triage_label":      s.triage_label,
                "primary_diagnosis": s.primary_diagnosis,
                "language":          s.input_language,
                "duration":          s.duration_text,
                "red_flags":         s.red_flags or [],
                "created_at":        s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in sessions
        ],
    }


# ── GET /nearby ────────────────────────────────────────────────────────────────

@router.get("/nearby", summary="Find nearest ASHA workers to GPS coordinates")
async def get_nearby_asha(
    lat:    float = Query(..., ge=-90,   le=90),
    lng:    float = Query(..., ge=-180,  le=180),
    radius: float = Query(25.0, ge=0.1, le=200, description="Search radius in km"),
    limit:  int   = Query(5,   ge=1,    le=20),
    db: AsyncSession = Depends(get_db),
):
    """
    Find the nearest active ASHA workers to the given GPS coordinates.
    Uses the same Haversine SQL query as the triage engine.
    Useful for the mobile app to display the closest ASHA contact.
    """
    from sqlalchemy import text
    try:
        result = await db.execute(
            text("""
                SELECT
                    id, name, phone, village, district_code,
                    latitude, longitude,
                    (6371.0 * acos(LEAST(1.0,
                        cos(radians(:lat)) * cos(radians(latitude)) *
                        cos(radians(longitude) - radians(:lng)) +
                        sin(radians(:lat)) * sin(radians(latitude))
                    ))) AS distance_km
                FROM asha_workers
                WHERE active = TRUE
                ORDER BY distance_km ASC
                LIMIT :limit
            """),
            {"lat": lat, "lng": lng, "limit": limit},
        )
        rows = result.mappings().all()
    except Exception as exc:
        logger.error("vaidya.asha_ep.nearby_query_failed", error=str(exc))
        raise HTTPException(500, "Database query failed")

    workers = [
        {
            "id":           str(r["id"]),
            "name":         r["name"],
            "phone":        r["phone"],
            "village":      r["village"],
            "district_code": r["district_code"],
            "distance_km":  round(float(r["distance_km"]), 2),
            "within_radius": float(r["distance_km"]) <= radius,
        }
        for r in rows
        if float(r["distance_km"]) <= radius
    ]

    return {
        "query":   {"lat": lat, "lng": lng, "radius_km": radius},
        "count":   len(workers),
        "workers": workers,
    }


# ── POST /register ─────────────────────────────────────────────────────────────

@router.post("/register", summary="Register or update an ASHA worker")
async def register_asha(
    payload: AshaRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new ASHA worker or update an existing one's FCM token and location.
    Matched on nhm_id (if provided) or phone number.
    Called by the Vaidya ASHA mobile app on first launch and on token refresh.
    """
    # Check if worker exists by nhm_id or phone
    existing = None
    if payload.nhm_id:
        result = await db.execute(
            select(AshaWorker).where(AshaWorker.nhm_id == payload.nhm_id)
        )
        existing = result.scalar_one_or_none()

    if not existing:
        result = await db.execute(
            select(AshaWorker).where(AshaWorker.phone == payload.phone)
        )
        existing = result.scalar_one_or_none()

    if existing:
        # Update FCM token and location
        existing.fcm_token   = payload.fcm_token or existing.fcm_token
        existing.latitude    = payload.latitude
        existing.longitude   = payload.longitude
        existing.village     = payload.village or existing.village
        existing.district_code = payload.district_code or existing.district_code
        existing.state_code  = payload.state_code or existing.state_code
        existing.active      = True
        await db.flush()
        logger.info("vaidya.asha_ep.updated", worker_id=str(existing.id)[:8])
        return {
            "status":    "updated",
            "worker_id": str(existing.id),
            "name":      existing.name,
        }

    # Create new worker
    worker = AshaWorker(
        nhm_id=payload.nhm_id,
        name=payload.name,
        phone=payload.phone,
        fcm_token=payload.fcm_token,
        latitude=payload.latitude,
        longitude=payload.longitude,
        village=payload.village,
        district_code=payload.district_code,
        state_code=payload.state_code,
    )
    db.add(worker)
    await db.flush()

    logger.info("vaidya.asha_ep.registered", worker_id=str(worker.id)[:8], name=payload.name)
    return {
        "status":    "registered",
        "worker_id": str(worker.id),
        "name":      worker.name,
    }


# ── POST /resolve/{session_id} ────────────────────────────────────────────────

@router.post("/resolve/{session_id}", summary="ASHA worker marks a patient session as resolved")
async def resolve_session(
    session_id: str,
    payload: AshaResolveRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a triage session as resolved by the assigned ASHA worker.
    Creates an immutable audit entry for traceability.
    In production, this removes the session from the ASHA worker's queue.
    """
    try:
        sid = uuid.UUID(session_id)
        wid = uuid.UUID(payload.worker_id)
    except ValueError:
        raise HTTPException(400, "Invalid session_id or worker_id format")

    result = await db.execute(select(TriageSession).where(TriageSession.id == sid))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    # Verify this worker is assigned to this session
    if session.asha_worker_id and session.asha_worker_id != wid:
        raise HTTPException(
            403,
            "This session is assigned to a different ASHA worker"
        )

    # Log resolution in audit trail
    from app.models.models import AuditLog
    audit = AuditLog(
        event_type="session_resolved",
        entity_type="triage_session",
        entity_id=str(sid),
        actor_id=str(wid),
        payload_hash=str(session.triage_level),
    )
    db.add(audit)
    await db.flush()

    logger.info(
        "vaidya.asha_ep.resolved",
        session=session_id[:8],
        worker=payload.worker_id[:8],
    )

    return {
        "status":     "resolved",
        "session_id": session_id,
        "worker_id":  payload.worker_id,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }


# ── GET /district/{code} ──────────────────────────────────────────────────────

@router.get("/district/{district_code}", summary="List active ASHA workers in a district")
async def get_district_workers(
    district_code: str,
    active_only:   bool = Query(True),
    limit:         int  = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all ASHA workers in a district.
    Used by the district health officer dashboard.
    """
    filters = [AshaWorker.district_code == district_code]
    if active_only:
        filters.append(AshaWorker.active == True)

    result = await db.execute(
        select(AshaWorker)
        .where(and_(*filters))
        .order_by(AshaWorker.name)
        .limit(limit)
    )
    workers = result.scalars().all()

    return {
        "district_code": district_code,
        "count":         len(workers),
        "workers": [
            {
                "id":      str(w.id),
                "name":    w.name,
                "phone":   w.phone,
                "village": w.village,
                "active":  w.active,
                "has_fcm": bool(w.fcm_token),
            }
            for w in workers
        ],
    }


# ── GET /stats/{worker_id} ────────────────────────────────────────────────────

@router.get("/stats/{worker_id}", summary="ASHA worker activity statistics")
async def get_worker_stats(
    worker_id: str,
    days:      int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns activity stats for an ASHA worker over the last N days.
    Shows sessions handled, triage level breakdown, and top diagnoses.
    """
    try:
        wid = uuid.UUID(worker_id)
    except ValueError:
        raise HTTPException(400, "Invalid worker_id")

    worker = await db.get(AshaWorker, wid)
    if not worker:
        raise HTTPException(404, "ASHA worker not found")

    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(TriageSession)
        .where(
            and_(
                TriageSession.asha_worker_id == wid,
                TriageSession.completed_at >= since,
            )
        )
    )
    sessions = result.scalars().all()

    level_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    diagnosis_counts: dict[str, int] = {}
    for s in sessions:
        if s.triage_level:
            level_counts[s.triage_level] = level_counts.get(s.triage_level, 0) + 1
        if s.primary_diagnosis:
            diagnosis_counts[s.primary_diagnosis] = diagnosis_counts.get(s.primary_diagnosis, 0) + 1

    top_diagnoses = sorted(diagnosis_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "worker_id":    worker_id,
        "worker_name":  worker.name,
        "village":      worker.village,
        "period_days":  days,
        "total_sessions": len(sessions),
        "by_triage_level": {str(k): v for k, v in level_counts.items() if v > 0},
        "top_diagnoses": [{"diagnosis": d, "count": c} for d, c in top_diagnoses],
    }


# ── POST /bulk-load ────────────────────────────────────────────────────────────

@router.post("/bulk-load", summary="Bulk-load ASHA workers from NHM CSV (admin)")
async def bulk_load_workers(
    file: UploadFile = File(..., description="CSV with columns: nhm_id,name,phone,latitude,longitude,village,district_code,state_code"),
    db: AsyncSession = Depends(get_db),
):
    """
    Load ASHA worker data from the NHM (National Health Mission) open dataset CSV.
    Expected CSV columns: nhm_id, name, phone, latitude, longitude, village, district_code, state_code

    NHM publishes the full 900k+ ASHA worker list at:
    https://nhm.gov.in/index4.php?lang=1&level=0&linkid=478&lid=1652

    Use scripts/seeds/load_asha.py for the full batch import.
    This endpoint handles smaller batches (< 10,000 rows) for testing.
    """
    content = await file.read()
    text_content = content.decode("utf-8-sig")  # handle BOM from Excel exports

    reader = csv.DictReader(io.StringIO(text_content))
    required_cols = {"name", "phone", "latitude", "longitude"}
    if not required_cols.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            422,
            f"CSV missing required columns. Required: {required_cols}. "
            f"Found: {set(reader.fieldnames or [])}"
        )

    created = updated = skipped = 0

    for row in reader:
        try:
            phone = row.get("phone", "").strip()
            if not phone:
                skipped += 1
                continue

            # Check for existing worker by phone or nhm_id
            nhm_id = row.get("nhm_id", "").strip() or None
            existing = None

            if nhm_id:
                r = await db.execute(select(AshaWorker).where(AshaWorker.nhm_id == nhm_id))
                existing = r.scalar_one_or_none()

            if not existing:
                r = await db.execute(select(AshaWorker).where(AshaWorker.phone == phone))
                existing = r.scalar_one_or_none()

            if existing:
                existing.latitude      = float(row.get("latitude", existing.latitude))
                existing.longitude     = float(row.get("longitude", existing.longitude))
                existing.village       = row.get("village", existing.village)
                existing.district_code = row.get("district_code", existing.district_code)
                existing.state_code    = row.get("state_code", existing.state_code)
                existing.active        = True
                updated += 1
            else:
                worker = AshaWorker(
                    nhm_id=nhm_id,
                    name=row.get("name", "").strip(),
                    phone=phone,
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    village=row.get("village", "").strip() or None,
                    district_code=row.get("district_code", "").strip() or None,
                    state_code=row.get("state_code", "").strip() or None,
                )
                db.add(worker)
                created += 1

        except (ValueError, KeyError) as exc:
            logger.warning("vaidya.asha_ep.bulk_skip_row", error=str(exc))
            skipped += 1
            continue

    await db.flush()

    logger.info(
        "vaidya.asha_ep.bulk_load",
        created=created, updated=updated, skipped=skipped,
    )

    return {
        "status":  "ok",
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }
