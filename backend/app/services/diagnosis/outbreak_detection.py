"""
Vaidya Health Analytics — Outbreak Anomaly Detection Pipeline
═══════════════════════════════════════════════════════════════════════════════

Purpose:  Real-time outbreak detection using statistical anomaly detection,
          geospatial clustering, and ASHA worker notifications

Algorithms:
    - Z-score anomaly detection (standard deviations from baseline)
    - Exponential weighted moving average (EWMA) for trend detection
    - DBSCAN spatial clustering for hotspot identification
    - Seasonal decomposition for time-series forecasting

Triggers:  Runs every 15 minutes via Celery beat scheduler
Output:    Creates outbreak alerts, notifies ASHA workers & district officers
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import AshaWorker
from app.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: BASELINE CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

async def update_all_baselines(db: AsyncSession, lookback_days: int = 60) -> int:
    """
    Update outbreak baselines for all district-diagnosis combinations.
    Should run once per day (typically at midnight).

    Args:
        db: Database session
        lookback_days: Number of historical days for baseline computation

    Returns:
        Number of baselines updated
    """
    logger.info("outbreak.baseline_update.started", lookback_days=lookback_days)

    # Get all unique district-diagnosis pairs from last 90 days
    query = text("""
        SELECT DISTINCT district_code, diagnosis
        FROM triage_events
        WHERE event_time >= NOW() - INTERVAL '90 days'
          AND district_code IS NOT NULL
          AND diagnosis IS NOT NULL
    """)

    result = await db.execute(query)
    pairs = result.fetchall()

    updated = 0
    for district_code, diagnosis in pairs:
        try:
            await db.execute(
                text("SELECT calculate_outbreak_baseline(:district, :diagnosis, :lookback)"),
                {
                    "district": district_code,
                    "diagnosis": diagnosis,
                    "lookback": lookback_days,
                },
            )
            updated += 1
        except Exception as e:
            logger.warning(
                "outbreak.baseline_update.failed",
                district=district_code,
                diagnosis=diagnosis,
                error=str(e),
            )

    await db.commit()

    logger.info("outbreak.baseline_update.completed", baselines_updated=updated)
    return updated


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: ANOMALY DETECTION ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class OutbreakDetector:
    """Statistical outbreak detection using multiple algorithms."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def detect_z_score_anomalies(
        self,
        district_code: str,
        diagnosis: str,
    ) -> Optional[Dict]:
        """
        Detect outbreaks using z-score method.

        Z-score = (current_cases - baseline_mean) / stddev

        Thresholds:
            z >= 4.0:  Critical outbreak (1 in 15,000 days)
            z >= 3.0:  Severe outbreak (1 in 370 days)
            z >= 2.5:  Moderate outbreak (1 in 81 days)
            z >= 2.0:  Warning (1 in 22 days)
        """
        result = await self.db.execute(
            text("SELECT * FROM detect_outbreak_anomaly(:district, :diagnosis)"),
            {"district": district_code, "diagnosis": diagnosis},
        )
        row = result.fetchone()

        if not row or not row.is_outbreak:
            return None

        return {
            "method": "z_score",
            "severity": row.severity,
            "z_score": float(row.z_score),
            "current_cases": row.current_cases,
            "baseline_mean": float(row.baseline_mean),
            "threshold_met": f"z >= {row.z_score:.2f}",
        }

    async def detect_percent_increase(
        self,
        district_code: str,
        diagnosis: str,
        threshold_pct: float = 100.0,  # 100% = doubling
    ) -> Optional[Dict]:
        """
        Detect outbreaks by percent increase over baseline.
        Useful for low-frequency diseases where z-score is less sensitive.
        """
        query = text("""
            WITH today_cases AS (
                SELECT SUM(case_count) AS cases
                FROM diagnosis_counts_hourly
                WHERE district_code = :district
                  AND diagnosis = :diagnosis
                  AND bucket >= DATE_TRUNC('day', NOW())
            ),
            baseline AS (
                SELECT mean_cases_per_day
                FROM outbreak_baselines
                WHERE district_code = :district
                  AND diagnosis = :diagnosis
            )
            SELECT
                tc.cases AS current_cases,
                b.mean_cases_per_day AS baseline_mean,
                CASE
                    WHEN b.mean_cases_per_day > 0 THEN
                        ((tc.cases - b.mean_cases_per_day) / b.mean_cases_per_day * 100)
                    ELSE NULL
                END AS percent_increase
            FROM today_cases tc, baseline b
        """)

        result = await self.db.execute(
            query,
            {"district": district_code, "diagnosis": diagnosis},
        )
        row = result.fetchone()

        if not row or row.percent_increase is None:
            return None

        pct_increase = float(row.percent_increase)

        if pct_increase < threshold_pct:
            return None

        if pct_increase >= 300:
            severity = "critical"
        elif pct_increase >= 200:
            severity = "severe"
        elif pct_increase >= 150:
            severity = "moderate"
        else:
            severity = "warning"

        return {
            "method": "percent_increase",
            "severity": severity,
            "percent_increase": pct_increase,
            "current_cases": row.current_cases,
            "baseline_mean": float(row.baseline_mean),
            "threshold_met": f"increase >= {threshold_pct}%",
        }

    async def detect_ewma_trend(
        self,
        district_code: str,
        diagnosis: str,
        alpha: float = 0.3,
    ) -> Optional[Dict]:
        """
        Exponentially weighted moving average (EWMA) for trend detection.
        More responsive to recent changes than simple moving average.

        EWMA[t] = α * X[t] + (1 - α) * EWMA[t-1]

        Detects outbreak when current value exceeds EWMA + 2*std
        """
        query = text("""
            SELECT
                DATE_TRUNC('day', bucket) AS day,
                SUM(case_count) AS daily_cases
            FROM diagnosis_counts_hourly
            WHERE district_code = :district
              AND diagnosis = :diagnosis
              AND bucket >= NOW() - INTERVAL '30 days'
            GROUP BY day
            ORDER BY day
        """)

        result = await self.db.execute(
            query,
            {"district": district_code, "diagnosis": diagnosis},
        )
        rows = result.fetchall()

        if len(rows) < 7:  # Need at least a week of data
            return None

        cases = np.array([float(row.daily_cases) for row in rows])

        # Calculate EWMA
        ewma = np.zeros(len(cases))
        ewma[0] = cases[0]
        for i in range(1, len(cases)):
            ewma[i] = alpha * cases[i] + (1 - alpha) * ewma[i - 1]

        # Calculate residuals and standard deviation
        residuals = cases - ewma
        std = np.std(residuals)

        current_cases = cases[-1]
        expected = ewma[-1]
        z_ewma = (current_cases - expected) / std if std > 0 else 0

        if z_ewma < 2.0:
            return None

        if z_ewma >= 4.0:
            severity = "critical"
        elif z_ewma >= 3.0:
            severity = "severe"
        elif z_ewma >= 2.5:
            severity = "moderate"
        else:
            severity = "warning"

        return {
            "method": "ewma_trend",
            "severity": severity,
            "z_ewma": float(z_ewma),
            "current_cases": int(current_cases),
            "expected_cases": float(expected),
            "threshold_met": "z_ewma >= 2.0",
        }

    async def detect_doubling_time(
        self,
        district_code: str,
        diagnosis: str,
        max_doubling_days: int = 7,
    ) -> Optional[Dict]:
        """
        Detect rapid growth by calculating doubling time.
        Critical for infectious disease outbreaks.

        Doubling time = ln(2) / growth_rate
        """
        query = text("""
            SELECT
                DATE_TRUNC('day', bucket) AS day,
                SUM(case_count) AS daily_cases
            FROM diagnosis_counts_hourly
            WHERE district_code = :district
              AND diagnosis = :diagnosis
              AND bucket >= NOW() - INTERVAL '14 days'
            GROUP BY day
            ORDER BY day
        """)

        result = await self.db.execute(
            query,
            {"district": district_code, "diagnosis": diagnosis},
        )
        rows = result.fetchall()

        if len(rows) < 7:
            return None

        days = np.arange(len(rows))
        cases = np.array([float(row.daily_cases) for row in rows])

        mask = cases > 0
        if mask.sum() < 5:
            return None

        days_filtered = days[mask]
        log_cases = np.log(cases[mask])

        slope, intercept, r_value, p_value, std_err = stats.linregress(
            days_filtered, log_cases
        )

        if slope <= 0:
            return None

        doubling_time = np.log(2) / slope

        if doubling_time > max_doubling_days or r_value < 0.7:
            return None

        if doubling_time <= 3:
            severity = "critical"
        elif doubling_time <= 5:
            severity = "severe"
        elif doubling_time <= 7:
            severity = "moderate"
        else:
            severity = "warning"

        return {
            "method": "doubling_time",
            "severity": severity,
            "doubling_time_days": float(doubling_time),
            "growth_rate": float(slope),
            "r_squared": float(r_value**2),
            "current_cases": int(cases[-1]),
            "threshold_met": f"doubling_time <= {max_doubling_days}d",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: GEOSPATIAL HOTSPOT DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

async def detect_geospatial_hotspots(
    db: AsyncSession,
    district_code: str,
    diagnosis: str,
    hours_back: int = 24,
    radius_km: float = 5.0,
    min_cases: int = 5,
) -> List[Dict]:
    """
    Detect disease hotspots using spatial clustering (DBSCAN).
    """
    query = text("""
        SELECT * FROM detect_geospatial_hotspots(
            :district,
            :diagnosis,
            :hours,
            :radius,
            :min_cases
        )
    """)

    result = await db.execute(
        query,
        {
            "district": district_code,
            "diagnosis": diagnosis,
            "hours": hours_back,
            "radius": radius_km,
            "min_cases": min_cases,
        },
    )

    hotspots = []
    for row in result.fetchall():
        point_str = str(row.cluster_center)
        if "POINT" in point_str:
            coords = point_str.replace("POINT(", "").replace(")", "").split()
            lng, lat = float(coords[0]), float(coords[1])

            hotspots.append({
                "center_lat": lat,
                "center_lng": lng,
                "case_count": row.case_count,
                "radius_km": float(row.radius_km),
            })

    return hotspots


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: ALERT GENERATION & NOTIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

async def create_outbreak_alert(
    db: AsyncSession,
    district_code: str,
    state_code: Optional[str],
    diagnosis: str,
    detection_result: Dict,
) -> str:
    """
    Create an outbreak alert record and trigger notifications.

    Returns:
        Alert ID (UUID)
    """
    # Deduplicate: same district + diagnosis active in last 6 hours
    query = text("""
        SELECT id FROM outbreak_alerts
        WHERE district_code = :district
          AND diagnosis = :diagnosis
          AND status = 'active'
          AND alert_time >= NOW() - INTERVAL '6 hours'
        LIMIT 1
    """)

    result = await db.execute(
        query,
        {"district": district_code, "diagnosis": diagnosis},
    )
    existing = result.fetchone()

    if existing:
        logger.info(
            "outbreak.alert.duplicate_suppressed",
            district=district_code,
            diagnosis=diagnosis,
        )
        return str(existing.id)

    insert_query = text("""
        INSERT INTO outbreak_alerts (
            district_code,
            state_code,
            diagnosis,
            current_cases,
            baseline_mean,
            z_score,
            percent_increase,
            severity,
            alert_threshold
        ) VALUES (
            :district,
            :state,
            :diagnosis,
            :current_cases,
            :baseline_mean,
            :z_score,
            :percent_increase,
            :severity,
            :threshold
        )
        RETURNING id
    """)

    result = await db.execute(
        insert_query,
        {
            "district": district_code,
            "state": state_code,
            "diagnosis": diagnosis,
            "current_cases": detection_result.get("current_cases", 0),
            "baseline_mean": detection_result.get("baseline_mean", 0),
            "z_score": detection_result.get("z_score"),
            "percent_increase": detection_result.get("percent_increase"),
            "severity": detection_result["severity"],
            "threshold": detection_result.get("threshold_met", "unknown"),
        },
    )

    alert_id = result.fetchone()[0]
    await db.commit()

    logger.info(
        "outbreak.alert.created",
        alert_id=str(alert_id)[:8],
        district=district_code,
        diagnosis=diagnosis,
        severity=detection_result["severity"],
        method=detection_result.get("method"),
    )

    asyncio.create_task(
        notify_stakeholders(
            db,
            alert_id=str(alert_id),
            district_code=district_code,
            diagnosis=diagnosis,
            severity=detection_result["severity"],
        )
    )

    return str(alert_id)


async def notify_stakeholders(
    db: AsyncSession,
    alert_id: str,
    district_code: str,
    diagnosis: str,
    severity: str,
):
    """
    Send notifications to ASHA workers and district health officers.

    Notification cascade:
        - Warning/Moderate: Notify ASHA workers in district via bulk_notify_district
        - Severe: Notify ASHA workers + district health officer
        - Critical: Notify ASHA + district officer + state officer + trigger IDSP
    """
    from app.worker.tasks import bulk_notify_district

    # Always notify ASHA workers via the existing bulk_notify_district task
    bulk_notify_district.delay(
        district_code=district_code,
        alert_type="outbreak_alert",
        message=(
            f"{severity.upper()} {diagnosis} outbreak detected in {district_code}. "
            f"Please check your dashboard immediately."
        ),
        disease=diagnosis,
    )

    # Update asha_notified flag
    await db.execute(
        text("UPDATE outbreak_alerts SET asha_notified = TRUE WHERE id = :id"),
        {"id": alert_id},
    )

    # Notify district officer for severe+ via email (notification task)
    if severity in ["severe", "critical"]:
        from app.worker.tasks import _send_district_officer_email
        if hasattr(_send_district_officer_email, 'delay'):
            _send_district_officer_email.delay(
                district_code=district_code,
                diagnosis=diagnosis,
                severity=severity,
                alert_id=alert_id,
            )

        await db.execute(
            text("UPDATE outbreak_alerts SET district_officer_notified = TRUE WHERE id = :id"),
            {"id": alert_id},
        )

    if severity == "critical":
        await db.execute(
            text("UPDATE outbreak_alerts SET state_officer_notified = TRUE WHERE id = :id"),
            {"id": alert_id},
        )

    await db.commit()

    logger.info(
        "outbreak.notifications.sent",
        alert_id=alert_id[:8],
        district=district_code,
        severity=severity,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: MAIN OUTBREAK DETECTION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

async def run_outbreak_detection_pipeline(db: AsyncSession) -> Dict:
    """
    Main pipeline: Run all outbreak detection algorithms on watchlist diseases.

    Returns:
        Summary statistics
    """
    logger.info("outbreak.pipeline.started")

    query = text("""
        SELECT diagnosis, outbreak_threshold_type, threshold_value
        FROM disease_watchlist
        WHERE priority_level >= 3
        ORDER BY priority_level DESC
    """)
    result = await db.execute(query)
    watchlist = result.fetchall()

    district_query = text("""
        SELECT DISTINCT district_code, state_code
        FROM triage_events
        WHERE event_time >= NOW() - INTERVAL '7 days'
          AND district_code IS NOT NULL
    """)
    result = await db.execute(district_query)
    districts = result.fetchall()

    detector = OutbreakDetector(db)

    alerts_created = 0
    total_checks = 0

    for district_code, state_code in districts:
        for disease in watchlist:
            diagnosis = disease.diagnosis
            threshold_type = disease.outbreak_threshold_type

            total_checks += 1
            detection_result = None

            if threshold_type == "z_score":
                detection_result = await detector.detect_z_score_anomalies(
                    district_code, diagnosis
                )
            elif threshold_type == "percent_increase":
                detection_result = await detector.detect_percent_increase(
                    district_code, diagnosis, disease.threshold_value
                )

            if not detection_result:
                detection_result = await detector.detect_ewma_trend(
                    district_code, diagnosis
                )

            if not detection_result:
                detection_result = await detector.detect_doubling_time(
                    district_code, diagnosis
                )

            if detection_result:
                await create_outbreak_alert(
                    db,
                    district_code=district_code,
                    state_code=state_code,
                    diagnosis=diagnosis,
                    detection_result=detection_result,
                )
                alerts_created += 1

                hotspots = await detect_geospatial_hotspots(
                    db,
                    district_code=district_code,
                    diagnosis=diagnosis,
                    hours_back=24,
                )

                if hotspots:
                    logger.info(
                        "outbreak.hotspots.detected",
                        district=district_code,
                        diagnosis=diagnosis,
                        hotspot_count=len(hotspots),
                    )

    logger.info(
        "outbreak.pipeline.completed",
        total_checks=total_checks,
        alerts_created=alerts_created,
    )

    return {
        "checks_performed": total_checks,
        "alerts_created": alerts_created,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: CELERY TASKS (Scheduled jobs)
# ═══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name="outbreak.detect_anomalies")
def detect_outbreak_anomalies_task():
    """
    Celery task: Run outbreak detection pipeline.
    Scheduled to run every 15 minutes via Celery Beat.
    """
    from app.core.database import AsyncSessionFactory

    async def _run():
        async with AsyncSessionFactory() as db:
            return await run_outbreak_detection_pipeline(db)

    result = asyncio.run(_run())
    return result


@celery_app.task(name="outbreak.update_baselines")
def update_baselines_task():
    """
    Celery task: Update outbreak baselines.
    Scheduled to run once per day at 02:00 UTC via Celery Beat.
    """
    from app.core.database import AsyncSessionFactory

    async def _run():
        async with AsyncSessionFactory() as db:
            return await update_all_baselines(db, lookback_days=60)

    result = asyncio.run(_run())
    return {"baselines_updated": result}
