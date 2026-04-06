"""
Vaidya Health Analytics — API Endpoints
═══════════════════════════════════════════════════════════════════════════════

Module: /api/v1/analytics

Endpoints:
    GET  /dashboard/district    — Real-time district health dashboard
    GET  /outbreaks/active      — List active outbreak alerts
    GET  /outbreaks/{id}        — Get outbreak alert details
    POST /outbreaks/{id}/acknowledge — Acknowledge outbreak (DHO action)
    GET  /hotspots              — Geospatial disease hotspots
    GET  /trends                — Time-series trends for diseases
    GET  /asha/performance      — ASHA worker performance metrics
    GET  /predictions           — Disease forecasting (next 7 days)
    GET  /triage/stream         — M9 live triage SSE stream for health officer dashboard
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.analytics_models import OutbreakAlert, OutbreakBaseline, HealthOfficerWebhook  # noqa: F401

logger = structlog.get_logger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class DistrictDashboardResponse(BaseModel):
    district_code: str
    state_code: Optional[str]
    period_hours: int

    # Overall metrics
    total_cases: int
    emergency_cases: int
    urgent_cases: int
    avg_triage_level: float

    # Triage breakdown
    triage_by_level: dict[str, int]

    # Top diseases
    top_diseases: List[dict]

    # Active outbreaks
    active_outbreaks: int
    outbreak_alerts: List[dict]

    # Temporal trend
    hourly_trend: List[dict]

    last_updated: datetime


class OutbreakAlertResponse(BaseModel):
    id: str
    alert_time: datetime
    district_code: str
    state_code: Optional[str]
    diagnosis: str

    # Metrics
    current_cases: int
    baseline_mean: float
    z_score: Optional[float]
    percent_increase: Optional[float]

    # Alert metadata
    severity: str
    alert_threshold: str
    status: str

    # Notifications
    asha_notified: bool
    district_officer_notified: bool
    state_officer_notified: bool

    # Actions
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[datetime]

    # Additional data
    affected_areas: Optional[dict]
    hours_since_alert: float


class HotspotResponse(BaseModel):
    id: str
    detected_at: datetime
    district_code: str
    diagnosis: str

    # Spatial data
    center_lat: float
    center_lng: float
    radius_km: float

    # Cluster metrics
    case_count: int
    time_window_hours: int
    density_score: float

    # Statistical significance
    p_value: Optional[float]
    relative_risk: Optional[float]


class TrendDataPoint(BaseModel):
    timestamp: datetime
    case_count: int
    avg_severity: Optional[float]


class DiseaseTrendResponse(BaseModel):
    district_code: str
    diagnosis: str
    start_date: datetime
    end_date: datetime

    data_points: List[TrendDataPoint]

    # Statistical summary
    total_cases: int
    mean_daily: float
    trend_direction: str  # increasing, stable, decreasing
    growth_rate: Optional[float]


class AshaPerformanceResponse(BaseModel):
    asha_worker_id: str
    name: str
    district_code: str

    # Period metrics
    period_days: int
    total_assignments: int
    acknowledged_count: int
    completed_count: int

    # Performance indicators
    acknowledgment_rate: float
    completion_rate: float
    avg_response_time_mins: float

    # Outcomes
    referrals: int
    self_care_advised: int


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: DISTRICT DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/dashboard/district",
    response_model=DistrictDashboardResponse,
    summary="Real-time district health dashboard",
)
async def get_district_dashboard(
    district_code: str = Query(..., min_length=2, max_length=10),
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """
    Comprehensive district health dashboard with:
    - Triage volume and severity breakdown
    - Top diseases
    - Active outbreak alerts
    - Hourly trend visualization

    Used by: District Health Officers, ASHA supervisors
    """
    logger.info("analytics.dashboard.requested", district=district_code, hours=hours)

    # Overall metrics from continuous aggregate
    summary_query = text("""
        SELECT
            SUM(total_cases) AS total_cases,
            SUM(level_5_emergency) AS emergency_cases,
            SUM(level_4_urgent) AS urgent_cases,
            AVG(avg_triage_level) AS avg_triage_level
        FROM triage_summary_15min
        WHERE district_code = :district
          AND bucket >= NOW() - INTERVAL '1 hour' * :hours
    """)

    result = await db.execute(summary_query, {"district": district_code, "hours": hours})
    summary = result.fetchone()

    # Triage breakdown
    triage_query = text("""
        SELECT
            SUM(level_1_self_care) AS level_1,
            SUM(level_2_monitor) AS level_2,
            SUM(level_3_see_gp) AS level_3,
            SUM(level_4_urgent) AS level_4,
            SUM(level_5_emergency) AS level_5
        FROM triage_summary_15min
        WHERE district_code = :district
          AND bucket >= NOW() - INTERVAL '1 hour' * :hours
    """)

    result = await db.execute(triage_query, {"district": district_code, "hours": hours})
    triage = result.fetchone()

    triage_by_level = {
        "1": triage.level_1 or 0,
        "2": triage.level_2 or 0,
        "3": triage.level_3 or 0,
        "4": triage.level_4 or 0,
        "5": triage.level_5 or 0,
    }

    # Top diseases
    diseases_query = text("""
        SELECT
            diagnosis,
            SUM(case_count) AS total_cases,
            ROUND(AVG(avg_triage_level), 2) AS avg_triage
        FROM diagnosis_counts_hourly
        WHERE district_code = :district
          AND bucket >= NOW() - INTERVAL '1 hour' * :hours
        GROUP BY diagnosis
        ORDER BY total_cases DESC
        LIMIT 10
    """)

    result = await db.execute(diseases_query, {"district": district_code, "hours": hours})
    top_diseases = [
        {
            "diagnosis": row.diagnosis,
            "case_count": row.total_cases,
            "avg_triage_level": float(row.avg_triage),
        }
        for row in result.fetchall()
    ]

    # Active outbreaks
    outbreaks_query = text("""
        SELECT
            id, alert_time, diagnosis, severity, current_cases,
            z_score, asha_notified
        FROM outbreak_alerts
        WHERE district_code = :district
          AND status = 'active'
          AND alert_time >= NOW() - INTERVAL '7 days'
        ORDER BY severity DESC, alert_time DESC
    """)

    result = await db.execute(outbreaks_query, {"district": district_code})
    outbreak_alerts = [
        {
            "id": str(row.id),
            "alert_time": row.alert_time.isoformat(),
            "diagnosis": row.diagnosis,
            "severity": row.severity,
            "current_cases": row.current_cases,
            "z_score": float(row.z_score) if row.z_score else None,
            "hours_since": (datetime.utcnow() - row.alert_time).total_seconds() / 3600,
        }
        for row in result.fetchall()
    ]

    # Hourly trend (last 24 hours)
    trend_query = text("""
        SELECT
            bucket,
            SUM(total_cases) AS total_cases,
            AVG(avg_triage_level) AS avg_triage
        FROM triage_summary_15min
        WHERE district_code = :district
          AND bucket >= NOW() - INTERVAL '24 hours'
        GROUP BY bucket
        ORDER BY bucket
    """)

    result = await db.execute(trend_query, {"district": district_code})
    hourly_trend = [
        {
            "timestamp": row.bucket.isoformat(),
            "cases": row.total_cases,
            "avg_triage": round(float(row.avg_triage), 2),
        }
        for row in result.fetchall()
    ]

    return DistrictDashboardResponse(
        district_code=district_code,
        state_code=None,  # TODO: lookup from district table
        period_hours=hours,
        total_cases=summary.total_cases or 0,
        emergency_cases=summary.emergency_cases or 0,
        urgent_cases=summary.urgent_cases or 0,
        avg_triage_level=round(float(summary.avg_triage_level or 0), 2),
        triage_by_level=triage_by_level,
        top_diseases=top_diseases,
        active_outbreaks=len(outbreak_alerts),
        outbreak_alerts=outbreak_alerts,
        hourly_trend=hourly_trend,
        last_updated=datetime.utcnow(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: OUTBREAK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/outbreaks/active",
    response_model=List[OutbreakAlertResponse],
    summary="List all active outbreak alerts",
)
async def list_active_outbreaks(
    district_code: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, pattern="^(warning|moderate|severe|critical)$"),
    days_back: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """
    List active outbreak alerts with optional filters.
    Returns alerts from last N days, newest first.
    """
    conditions = [
        "status = 'active'",
        f"alert_time >= NOW() - INTERVAL '{days_back} days'",
    ]

    params = {}

    if district_code:
        conditions.append("district_code = :district")
        params["district"] = district_code

    if severity:
        conditions.append("severity = :severity")
        params["severity"] = severity

    where_clause = " AND ".join(conditions)

    query = text(f"""
        SELECT
            id, alert_time, district_code, state_code, diagnosis,
            current_cases, baseline_mean, z_score, percent_increase,
            severity, alert_threshold, status,
            asha_notified, district_officer_notified, state_officer_notified,
            acknowledged_by, acknowledged_at, affected_areas,
            EXTRACT(EPOCH FROM (NOW() - alert_time))/3600 AS hours_since
        FROM outbreak_alerts
        WHERE {where_clause}
        ORDER BY severity DESC, alert_time DESC
        LIMIT 100
    """)

    result = await db.execute(query, params)

    alerts = []
    for row in result.fetchall():
        alerts.append(
            OutbreakAlertResponse(
                id=str(row.id),
                alert_time=row.alert_time,
                district_code=row.district_code,
                state_code=row.state_code,
                diagnosis=row.diagnosis,
                current_cases=row.current_cases,
                baseline_mean=float(row.baseline_mean),
                z_score=float(row.z_score) if row.z_score else None,
                percent_increase=float(row.percent_increase) if row.percent_increase else None,
                severity=row.severity,
                alert_threshold=row.alert_threshold,
                status=row.status,
                asha_notified=row.asha_notified,
                district_officer_notified=row.district_officer_notified,
                state_officer_notified=row.state_officer_notified,
                acknowledged_by=row.acknowledged_by,
                acknowledged_at=row.acknowledged_at,
                affected_areas=row.affected_areas,
                hours_since_alert=float(row.hours_since),
            )
        )

    return alerts


@router.get(
    "/outbreaks/{alert_id}",
    response_model=OutbreakAlertResponse,
    summary="Get outbreak alert details",
)
async def get_outbreak_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about a specific outbreak alert."""
    try:
        alert_uuid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(400, "Invalid alert ID")

    query = text("""
        SELECT
            id, alert_time, district_code, state_code, diagnosis,
            current_cases, baseline_mean, z_score, percent_increase,
            severity, alert_threshold, status,
            asha_notified, district_officer_notified, state_officer_notified,
            acknowledged_by, acknowledged_at, affected_areas,
            EXTRACT(EPOCH FROM (NOW() - alert_time))/3600 AS hours_since
        FROM outbreak_alerts
        WHERE id = :id
    """)

    result = await db.execute(query, {"id": str(alert_uuid)})
    row = result.fetchone()

    if not row:
        raise HTTPException(404, f"Alert {alert_id} not found")

    return OutbreakAlertResponse(
        id=str(row.id),
        alert_time=row.alert_time,
        district_code=row.district_code,
        state_code=row.state_code,
        diagnosis=row.diagnosis,
        current_cases=row.current_cases,
        baseline_mean=float(row.baseline_mean),
        z_score=float(row.z_score) if row.z_score else None,
        percent_increase=float(row.percent_increase) if row.percent_increase else None,
        severity=row.severity,
        alert_threshold=row.alert_threshold,
        status=row.status,
        asha_notified=row.asha_notified,
        district_officer_notified=row.district_officer_notified,
        state_officer_notified=row.state_officer_notified,
        acknowledged_by=row.acknowledged_by,
        acknowledged_at=row.acknowledged_at,
        affected_areas=row.affected_areas,
        hours_since_alert=float(row.hours_since),
    )


class AcknowledgeOutbreakRequest(BaseModel):
    officer_id: str
    notes: Optional[str] = Field(None, max_length=1000)


@router.post(
    "/outbreaks/{alert_id}/acknowledge",
    summary="Acknowledge outbreak alert (DHO action)",
)
async def acknowledge_outbreak(
    alert_id: str,
    payload: AcknowledgeOutbreakRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Acknowledge an outbreak alert.
    Used by District Health Officers to confirm they've reviewed the alert
    and initiated investigation.
    """
    try:
        alert_uuid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(400, "Invalid alert ID")

    query = text("""
        UPDATE outbreak_alerts
        SET acknowledged_by = :officer_id,
            acknowledged_at = NOW(),
            notes = COALESCE(notes || E'\\n', '') || :new_notes
        WHERE id = :id
          AND status = 'active'
        RETURNING id
    """)

    result = await db.execute(
        query,
        {
            "id": str(alert_uuid),
            "officer_id": payload.officer_id,
            "new_notes": f"[{datetime.utcnow().isoformat()}] Acknowledged by {payload.officer_id}: {payload.notes or 'No notes'}",
        },
    )

    if not result.fetchone():
        raise HTTPException(404, "Alert not found or already resolved")

    await db.commit()

    logger.info(
        "outbreak.alert.acknowledged",
        alert_id=alert_id[:8],
        officer=payload.officer_id,
    )

    return {
        "status": "acknowledged",
        "alert_id": alert_id,
        "acknowledged_by": payload.officer_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: GEOSPATIAL HOTSPOTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/hotspots",
    response_model=List[HotspotResponse],
    summary="Get geospatial disease hotspots",
)
async def get_disease_hotspots(
    district_code: str = Query(...),
    diagnosis: Optional[str] = Query(None),
    hours_back: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detected disease clusters (hotspots) in a district.
    Returns spatial clusters detected by DBSCAN algorithm.
    """
    conditions = [
        "district_code = :district",
        "detected_at >= NOW() - INTERVAL '1 hour' * :hours",
        "status = 'active'",
    ]

    params = {"district": district_code, "hours": hours_back}

    if diagnosis:
        conditions.append("diagnosis = :diagnosis")
        params["diagnosis"] = diagnosis

    where_clause = " AND ".join(conditions)

    query = text(f"""
        SELECT
            id,
            detected_at,
            district_code,
            diagnosis,
            ST_Y(cluster_center::geometry) AS center_lat,
            ST_X(cluster_center::geometry) AS center_lng,
            cluster_radius_km,
            case_count,
            time_window_hours,
            density_score,
            p_value,
            relative_risk
        FROM disease_clusters
        WHERE {where_clause}
        ORDER BY case_count DESC
        LIMIT 50
    """)

    result = await db.execute(query, params)

    hotspots = []
    for row in result.fetchall():
        hotspots.append(
            HotspotResponse(
                id=str(row.id),
                detected_at=row.detected_at,
                district_code=row.district_code,
                diagnosis=row.diagnosis,
                center_lat=float(row.center_lat),
                center_lng=float(row.center_lng),
                radius_km=float(row.cluster_radius_km),
                case_count=row.case_count,
                time_window_hours=row.time_window_hours,
                density_score=float(row.density_score),
                p_value=float(row.p_value) if row.p_value else None,
                relative_risk=float(row.relative_risk) if row.relative_risk else None,
            )
        )

    return hotspots


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: DISEASE TRENDS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/trends",
    response_model=DiseaseTrendResponse,
    summary="Time-series trend for a disease",
)
async def get_disease_trend(
    district_code: str = Query(...),
    diagnosis: str = Query(...),
    days_back: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """
    Get time-series trend data for a specific disease in a district.
    Returns daily case counts with trend analysis.
    """
    query = text("""
        SELECT
            DATE_TRUNC('day', bucket) AS day,
            SUM(case_count) AS daily_cases,
            AVG(avg_triage_level) AS avg_severity
        FROM diagnosis_counts_hourly
        WHERE district_code = :district
          AND diagnosis = :diagnosis
          AND bucket >= NOW() - INTERVAL '1 day' * :days
        GROUP BY day
        ORDER BY day
    """)

    result = await db.execute(
        query,
        {"district": district_code, "diagnosis": diagnosis, "days": days_back},
    )

    data_points = []
    case_counts = []

    for row in result.fetchall():
        data_points.append(
            TrendDataPoint(
                timestamp=row.day,
                case_count=row.daily_cases,
                avg_severity=float(row.avg_severity) if row.avg_severity else None,
            )
        )
        case_counts.append(row.daily_cases)

    if not data_points:
        raise HTTPException(404, "No data found for specified parameters")

    # Calculate trend
    total_cases = sum(case_counts)
    mean_daily = total_cases / len(case_counts)

    # Simple linear trend
    if len(case_counts) >= 7:
        recent_avg = sum(case_counts[-7:]) / 7
        earlier_avg = sum(case_counts[:7]) / 7

        if recent_avg > earlier_avg * 1.2:
            trend_direction = "increasing"
            growth_rate = ((recent_avg - earlier_avg) / earlier_avg) * 100
        elif recent_avg < earlier_avg * 0.8:
            trend_direction = "decreasing"
            growth_rate = ((recent_avg - earlier_avg) / earlier_avg) * 100
        else:
            trend_direction = "stable"
            growth_rate = 0.0
    else:
        trend_direction = "insufficient_data"
        growth_rate = None

    return DiseaseTrendResponse(
        district_code=district_code,
        diagnosis=diagnosis,
        start_date=data_points[0].timestamp,
        end_date=data_points[-1].timestamp,
        data_points=data_points,
        total_cases=total_cases,
        mean_daily=round(mean_daily, 2),
        trend_direction=trend_direction,
        growth_rate=round(growth_rate, 2) if growth_rate is not None else None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: ASHA WORKER PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/asha/performance",
    response_model=List[AshaPerformanceResponse],
    summary="ASHA worker performance metrics",
)
async def get_asha_performance(
    district_code: str = Query(...),
    days_back: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """
    Get performance metrics for ASHA workers in a district.
    Useful for ASHA supervisors and district coordinators.
    """
    query = text("""
        SELECT
            aw.id AS asha_worker_id,
            aw.name,
            aw.district_code,
            SUM(total_assignments) AS total_assignments,
            SUM(acknowledged_count) AS acknowledged_count,
            SUM(completed_count) AS completed_count,
            AVG(avg_response_time_mins) AS avg_response_time,
            SUM(referrals) AS referrals
        FROM asha_performance_daily apd
        JOIN asha_workers aw ON apd.asha_worker_id = aw.id
        WHERE aw.district_code = :district
          AND apd.bucket >= NOW() - INTERVAL '1 day' * :days
        GROUP BY aw.id, aw.name, aw.district_code
        HAVING SUM(total_assignments) > 0
        ORDER BY total_assignments DESC
        LIMIT 100
    """)

    result = await db.execute(query, {"district": district_code, "days": days_back})

    performance_list = []
    for row in result.fetchall():
        total_assignments = row.total_assignments or 0
        acknowledged = row.acknowledged_count or 0
        completed = row.completed_count or 0

        performance_list.append(
            AshaPerformanceResponse(
                asha_worker_id=str(row.asha_worker_id),
                name=row.name,
                district_code=row.district_code,
                period_days=days_back,
                total_assignments=total_assignments,
                acknowledged_count=acknowledged,
                completed_count=completed,
                acknowledgment_rate=round((acknowledged / total_assignments * 100), 2)
                if total_assignments > 0
                else 0.0,
                completion_rate=round((completed / total_assignments * 100), 2)
                if total_assignments > 0
                else 0.0,
                avg_response_time_mins=round(float(row.avg_response_time or 0), 1),
                referrals=row.referrals or 0,
                self_care_advised=0,  # TODO: add to events table
            )
        )

    return performance_list


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION M9: LIVE TRIAGE SSE STREAM — Health Officer Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

class TriageEvent(BaseModel):
    event_type: str  # "triage_case" | "outbreak_alert" | "heartbeat"
    timestamp: str
    district_code: Optional[str] = None
    triage_level: Optional[int] = None
    disease_prediction: Optional[str] = None
    confidence: Optional[float] = None
    village_code: Optional[str] = None
    patient_age_group: Optional[str] = None
    alert_message: Optional[str] = None


async def _triage_event_generator(
    district_code: str,
    db: AsyncSession,
    poll_interval: float = 5.0,
) -> AsyncGenerator[str, None]:
    """
    Poll the database for new triage cases and outbreak alerts every
    `poll_interval` seconds and yield SSE-formatted events.

    SSE wire format:
        event: <event_type>
        data: <json>

        (blank line terminates the event)
    """
    last_seen_ts: datetime = datetime.utcnow()

    # Send initial connection confirmation
    yield (
        "event: connected\n"
        f"data: {json.dumps({'district_code': district_code, 'ts': last_seen_ts.isoformat()})}\n\n"
    )

    heartbeat_counter = 0

    while True:
        try:
            # ── New triage cases since last poll ──────────────────────────────
            cases_q = text("""
                SELECT
                    te.id,
                    te.created_at,
                    te.district_code,
                    te.triage_level,
                    te.top_disease,
                    te.confidence,
                    te.village_code,
                    CASE
                        WHEN te.patient_age < 5  THEN 'infant'
                        WHEN te.patient_age < 18 THEN 'child'
                        WHEN te.patient_age < 60 THEN 'adult'
                        ELSE 'elderly'
                    END AS age_group
                FROM triage_events te
                WHERE te.district_code = :district
                  AND te.created_at > :since
                ORDER BY te.created_at ASC
                LIMIT 50
            """)

            cases_result = await db.execute(
                cases_q,
                {"district": district_code, "since": last_seen_ts},
            )
            rows = cases_result.fetchall()

            for row in rows:
                payload = TriageEvent(
                    event_type="triage_case",
                    timestamp=row.created_at.isoformat(),
                    district_code=row.district_code,
                    triage_level=row.triage_level,
                    disease_prediction=row.top_disease,
                    confidence=float(row.confidence) if row.confidence else None,
                    village_code=row.village_code,
                    patient_age_group=row.age_group,
                )
                yield f"event: triage_case\ndata: {payload.model_dump_json()}\n\n"
                last_seen_ts = max(last_seen_ts, row.created_at)

            # ── Active outbreak alerts ─────────────────────────────────────────
            alerts_q = text("""
                SELECT
                    oa.id,
                    oa.disease_code,
                    oa.district_code,
                    oa.severity,
                    oa.alert_message,
                    oa.triggered_at
                FROM outbreak_alerts oa
                WHERE oa.district_code = :district
                  AND oa.status = 'active'
                  AND oa.triggered_at > :since
                ORDER BY oa.triggered_at DESC
                LIMIT 10
            """)

            alerts_result = await db.execute(
                alerts_q,
                {"district": district_code, "since": last_seen_ts - timedelta(seconds=poll_interval)},
            )
            for alert_row in alerts_result.fetchall():
                alert_payload = TriageEvent(
                    event_type="outbreak_alert",
                    timestamp=alert_row.triggered_at.isoformat(),
                    district_code=alert_row.district_code,
                    disease_prediction=alert_row.disease_code,
                    alert_message=alert_row.alert_message,
                )
                yield f"event: outbreak_alert\ndata: {alert_payload.model_dump_json()}\n\n"

            # ── Heartbeat every ~30 s (6 × 5 s polls) ────────────────────────
            heartbeat_counter += 1
            if heartbeat_counter >= 6:
                heartbeat_counter = 0
                hb = json.dumps({"ts": datetime.utcnow().isoformat(), "district": district_code})
                yield f"event: heartbeat\ndata: {hb}\n\n"

        except Exception as exc:  # noqa: BLE001
            logger.warning("vaidya.analytics.sse_stream_error", error=str(exc))
            err_payload = json.dumps({"error": str(exc), "ts": datetime.utcnow().isoformat()})
            yield f"event: error\ndata: {err_payload}\n\n"

        await asyncio.sleep(poll_interval)


@router.get(
    "/triage/stream",
    summary="M9 — Live triage SSE stream for health officer dashboard",
    response_class=StreamingResponse,
    tags=["analytics", "sse"],
    responses={
        200: {
            "description": "Server-Sent Events stream of live triage cases and outbreak alerts",
            "content": {"text/event-stream": {}},
        }
    },
)
async def triage_live_stream(
    district_code: str = Query(..., description="District code to stream events for"),
    poll_interval: float = Query(5.0, ge=1.0, le=30.0, description="DB poll interval in seconds"),
    db: AsyncSession = Depends(get_db),
):
    """
    M9 — Health Officer Live Triage Stream
    ────────────────────────────────────────────────────────────────────────────
    Returns a persistent Server-Sent Events (SSE) stream of real-time triage
    events and outbreak alerts for the given district.  Intended for the health
    officer dashboard to show incoming cases without polling.

    **Event types emitted:**
    - `connected`     — sent once on connection with district info
    - `triage_case`   — new triage case (level, disease, village, age group)
    - `outbreak_alert`— newly triggered outbreak alert for the district
    - `heartbeat`     — keepalive ping every ~30 s
    - `error`         — non-fatal DB error (stream continues)

    **Frontend usage (EventSource):**
    ```js
    const es = new EventSource(
      `/api/v1/analytics/triage/stream?district_code=TN-CBE`
    );
    es.addEventListener('triage_case', (e) => {
      const ev = JSON.parse(e.data);
      dispatch(addTriageEvent(ev));
    });
    es.addEventListener('outbreak_alert', (e) => {
      const alert = JSON.parse(e.data);
      dispatch(showOutbreakBanner(alert));
    });
    es.addEventListener('heartbeat', () => console.debug('SSE alive'));
    es.onerror = () => es.close();
    ```
    """
    return StreamingResponse(
        _triage_event_generator(district_code, db, poll_interval),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # nginx SSE pass-through
            "Connection": "keep-alive",
        },
    )
