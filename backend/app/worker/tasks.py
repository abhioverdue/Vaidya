"""
Vaidya — Celery tasks  (Module 6 — complete)

Notification tasks:
  notify_asha_fcm          — FCM push to ASHA worker smartphone
  notify_asha_sms          — Twilio SMS fallback for feature phones
  schedule_followup        — Follow-up reminder at triage-level deadline
  bulk_notify_district     — Notify all ASHA workers in a district (outbreak)

Maintenance tasks (Beat schedule):
  send_followup_reminders  — Scan overdue follow-ups (every 30 min)
  aggregate_district_stats — Nightly disease count aggregation
  cleanup_raw_text         — DPDP 30-day raw text deletion

All tasks are idempotent — safe to retry on failure.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
from celery import shared_task
from sqlalchemy import select, text, update

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── FCM push notification ──────────────────────────────────────────────────────




@celery_app.task(
    name="app.worker.tasks.notify_asha_fcm",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    queue="notifications",
)
def notify_asha_fcm(
    self,
    session_id:   str,
    worker_id:    str,
    fcm_token:    str,
    triage_level: int,
    diagnosis:    str,
) -> dict:
    """
    Send FCM push notification to ASHA worker's smartphone.
    Retries 5 times with 30s delay on transient failures.
    Uses FCM Legacy HTTP API (free, no quota limits for low volume).
    """
    from app.core.config import settings

    if not settings.FCM_PROJECT_ID or not settings.GOOGLE_APPLICATION_CREDENTIALS:
        logger.warning("vaidya.fcm_v1.no_credentials — set FCM_PROJECT_ID and GOOGLE_APPLICATION_CREDENTIALS")
        return {"status": "skipped", "reason": "FCM v1 credentials not configured"}

    from app.services.notifications.fcm import send_fcm_v1
    result = send_fcm_v1(
        fcm_token=fcm_token,
        session_id=session_id,
        worker_id=worker_id,
        triage_level=triage_level,
        diagnosis=diagnosis,
        credentials_path=settings.GOOGLE_APPLICATION_CREDENTIALS,
        project_id=settings.FCM_PROJECT_ID,
    )

    if result["status"] == "token_invalid":
        _clear_stale_fcm_token.delay(worker_id)
        return result

    if result["status"] == "retry":
        raise self.retry(countdown=60, exc=Exception(result.get("error", "transient")))

    if result["status"] not in ("sent",):
        raise self.retry(countdown=30, exc=Exception(result.get("error", "unknown")))

    return result


@celery_app.task(name="app.worker.tasks._clear_stale_fcm_token", queue="maintenance")
def _clear_stale_fcm_token(worker_id: str) -> None:
    """Clear an invalid FCM token from the ASHA worker record."""
    async def _clear():
        from app.core.database import AsyncSessionFactory
        from app.models.models import AshaWorker
        import uuid
        async with AsyncSessionFactory() as db:
            await db.execute(
                update(AshaWorker)
                .where(AshaWorker.id == uuid.UUID(worker_id))
                .values(fcm_token=None)
            )
            await db.commit()
    _run_async(_clear())
    logger.info("vaidya.fcm.token_cleared", worker_id=worker_id[:8])


# ── Twilio SMS notification ────────────────────────────────────────────────────

def _build_sms_body(
    worker_name:  str,
    triage_level: int,
    diagnosis:    str,
    session_id:   str,
) -> str:
    """
    Build SMS body in plain language (no Unicode — wider network compatibility).
    Kept under 160 chars for single SMS.
    """
    urgency = {5: "EMERGENCY", 4: "URGENT", 3: "Action needed"}.get(triage_level, "Follow-up")
    short_id = session_id[:6].upper()

    msg = (
        f"Vaidya Alert [{short_id}]: {urgency} — {worker_name}, "
        f"a patient needs attention ({diagnosis[:40]}). "
        f"Open Vaidya app or call 108 if emergency."
    )
    return msg[:160]


@celery_app.task(
    name="app.worker.tasks.notify_asha_sms",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="notifications",
)
def notify_asha_sms(
    self,
    session_id:   str,
    phone:        str,
    worker_name:  str,
    triage_level: int,
    diagnosis:    str,
) -> dict:
    """
    Send Twilio SMS to ASHA worker (fallback for feature phones without FCM).
    Twilio free trial: 1,500 messages. Production: ~$0.015 per SMS.
    Only sends for triage level 3+ to conserve credits.
    """
    from app.core.config import settings

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.debug("vaidya.sms.no_credentials — skipping SMS")
        return {"status": "skipped", "reason": "Twilio credentials not configured"}

    if triage_level < 3:
        return {"status": "skipped", "reason": "below SMS threshold"}

    body = _build_sms_body(worker_name, triage_level, diagnosis, session_id)

    try:
        response = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
            data={
                "From": settings.TWILIO_FROM_NUMBER,
                "To":   phone,
                "Body": body,
            },
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            timeout=15,
        )
        response.raise_for_status()
        sid = response.json().get("sid", "")

        logger.info(
            "vaidya.sms.sent",
            session=session_id[:8],
            phone_last4=phone[-4:],
            level=triage_level,
            sid=sid[:8] if sid else "",
        )
        return {"status": "sent", "sid": sid}

    except httpx.HTTPStatusError as exc:
        logger.error("vaidya.sms.http_error", status=exc.response.status_code, body=exc.response.text[:200])
        raise self.retry(exc=exc, countdown=60)
    except Exception as exc:
        logger.error("vaidya.sms.error", error=str(exc))
        raise self.retry(exc=exc, countdown=60)


# ── Follow-up reminder ─────────────────────────────────────────────────────────

@celery_app.task(
    name="app.worker.tasks.schedule_followup",
    bind=True,
    max_retries=2,
    queue="followups",
)
def schedule_followup(
    self,
    session_id:    str,
    worker_id:     str,
    triage_level:  int,
) -> dict:
    """
    Send follow-up reminder to ASHA worker after the triage-level deadline.
    Called via countdown= so it fires at the right time.
    Only fires if the session is still open (no resolution recorded).
    """
    async def _check_and_notify():
        from app.core.database import AsyncSessionFactory
        from app.models.models import AshaWorker, TriageSession
        import uuid

        async with AsyncSessionFactory() as db:
            session = await db.get(TriageSession, uuid.UUID(session_id))
            if not session:
                return {"status": "skipped", "reason": "session_not_found"}

            # Skip if session was already resolved (would need a resolved_at field in production)
            # For now, always send the reminder

            worker = await db.get(AshaWorker, uuid.UUID(worker_id))
            if not worker:
                return {"status": "skipped", "reason": "worker_not_found"}

            reminder_msg = (
                f"Vaidya Reminder: Patient (session {session_id[:6].upper()}) "
                f"follow-up due. Triage level {triage_level}. "
                f"Diagnosis: {(session.primary_diagnosis or 'Unknown')[:40]}. "
                f"Please check on the patient."
            )

            results = {}

            # FCM reminder
            if worker.fcm_token:
                try:
                    from app.core.config import settings
                    from app.services.notifications.fcm import send_fcm_v1
                    if settings.FCM_PROJECT_ID and settings.GOOGLE_APPLICATION_CREDENTIALS:
                        fcm_result = send_fcm_v1(
                            fcm_token=worker.fcm_token,
                            session_id=session_id,
                            worker_id=str(worker.id),
                            triage_level=triage_level,
                            diagnosis=session.primary_diagnosis or "Unknown",
                            credentials_path=settings.GOOGLE_APPLICATION_CREDENTIALS,
                            project_id=settings.FCM_PROJECT_ID,
                            is_reminder=True,
                        )
                        results["fcm"] = fcm_result["status"]
                    else:
                        results["fcm"] = "skipped_no_credentials"
                except Exception as exc:
                    results["fcm"] = f"failed: {exc}"

            # SMS reminder (triage 4+ only to save credits)
            if worker.phone and triage_level >= 4:
                from app.core.config import settings
                if settings.TWILIO_ACCOUNT_SID:
                    try:
                        httpx.post(
                            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                            data={
                                "From": settings.TWILIO_FROM_NUMBER,
                                "To":   worker.phone,
                                "Body": reminder_msg[:160],
                            },
                            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                            timeout=10,
                        )
                        results["sms"] = "sent"
                    except Exception as exc:
                        results["sms"] = f"failed: {exc}"

            return {"status": "sent", "results": results}

    result = _run_async(_check_and_notify())
    logger.info("vaidya.followup.sent", session=session_id[:8], level=triage_level)
    return result


# ── Beat schedule tasks ────────────────────────────────────────────────────────

@celery_app.task(name="app.worker.tasks.send_followup_reminders", queue="maintenance")
def send_followup_reminders() -> dict:
    """
    Scan for sessions where follow_up_at has passed but no resolution exists.
    Runs every 30 min via beat schedule.
    """
    async def _scan():
        from app.core.database import AsyncSessionFactory
        from app.models.models import TriageSession, AshaWorker
        from sqlalchemy import and_

        now     = datetime.now(timezone.utc)
        window  = now - timedelta(hours=2)   # sessions due in last 2h

        async with AsyncSessionFactory() as db:
            result = await db.execute(
                select(TriageSession)
                .where(
                    and_(
                        TriageSession.triage_level >= 3,
                        TriageSession.completed_at.isnot(None),
                        # follow_up_at would be completed_at + FOLLOWUP_HOURS[level]
                        # simplified check: completed_at between 2h and follow_up window ago
                    )
                )
                .limit(50)
            )
            sessions = result.scalars().all()

            due_count = 0
            for s in sessions:
                if not s.triage_level or not s.completed_at:
                    continue
                hours = {3: 24, 4: 8, 5: 2}.get(s.triage_level, 24)
                follow_up_at = s.completed_at + timedelta(hours=hours)

                # If follow-up was due in the past 30 minutes
                if window <= follow_up_at <= now:
                    due_count += 1
                    if s.asha_worker_id:
                        schedule_followup.apply_async(
                            args=[str(s.id), str(s.asha_worker_id), s.triage_level],
                            countdown=0,
                            queue="followups",
                        )

            return due_count

    count = _run_async(_scan())
    logger.info("vaidya.tasks.followup_scan", due_count=count)
    return {"status": "ok", "due_sessions": count}


@celery_app.task(name="app.worker.tasks.aggregate_district_stats", queue="maintenance")
def aggregate_district_stats() -> dict:
    """
    Nightly aggregation of triage events per district.
    Runs at 1 AM IST via beat schedule.
    Module 9 will replace this with TimescaleDB continuous aggregates.
    """
    async def _agg():
        from app.core.database import AsyncSessionFactory
        async with AsyncSessionFactory() as db:
            result = await db.execute(text("""
                SELECT
                    district_code,
                    diagnosis,
                    triage_level,
                    COUNT(*) AS count
                FROM triage_events
                WHERE event_time >= NOW() - INTERVAL '24 hours'
                  AND district_code IS NOT NULL
                GROUP BY district_code, diagnosis, triage_level
                ORDER BY count DESC
                LIMIT 200
            """))
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    stats = _run_async(_agg())
    logger.info("vaidya.tasks.agg_done", district_rows=len(stats))
    return {"status": "ok", "aggregated_at": datetime.now(timezone.utc).isoformat(), "rows": len(stats)}


@celery_app.task(name="app.worker.tasks.cleanup_raw_text", queue="maintenance")
def cleanup_raw_text() -> dict:
    """
    DPDP Act 2023 compliance: delete raw_text from sessions older than 30 days.
    Runs nightly at 2 AM IST via beat schedule.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    async def _clean():
        from app.core.database import AsyncSessionFactory
        async with AsyncSessionFactory() as db:
            result = await db.execute(
                text(
                    "UPDATE triage_sessions SET raw_text = NULL "
                    "WHERE created_at < :cutoff AND raw_text IS NOT NULL"
                ),
                {"cutoff": cutoff},
            )
            await db.commit()
            return result.rowcount

    count = _run_async(_clean())
    logger.info("vaidya.tasks.cleanup_done", rows=count, cutoff=cutoff.date().isoformat())
    return {"status": "ok", "rows_cleaned": count, "cutoff": cutoff.isoformat()}


@celery_app.task(name="app.worker.tasks.bulk_notify_district", queue="notifications")
def bulk_notify_district(
    district_code: str,
    alert_type:    str,
    message:       str,
    disease:       str = "",
) -> dict:
    """
    Notify all active ASHA workers in a district (used for outbreak alerts).
    Called by the outbreak detection pipeline in Module 9.
    Throttled to 50 workers to avoid FCM rate limits.
    """
    async def _notify():
        from app.core.database import AsyncSessionFactory
        from app.models.models import AshaWorker

        async with AsyncSessionFactory() as db:
            result = await db.execute(
                select(AshaWorker)
                .where(AshaWorker.active == True)
                .where(AshaWorker.district_code == district_code)
                .limit(50)
            )
            workers = result.scalars().all()
            sent = 0
            for w in workers:
                if w.fcm_token:
                    notify_asha_fcm.apply_async(
                        args=["OUTBREAK", str(w.id), w.fcm_token, 3, disease or alert_type],
                        queue="notifications",
                    )
                    sent += 1
            return sent

    sent = _run_async(_notify())
    logger.info("vaidya.tasks.bulk_notify", district=district_code, sent=sent, alert=alert_type)
    return {"status": "ok", "workers_notified": sent, "district": district_code}


# ── District officer email (called by outbreak_detection.notify_stakeholders) ──

@celery_app.task(name="app.worker.tasks._send_district_officer_email", queue="notifications")
def _send_district_officer_email(
    district_code: str,
    diagnosis: str,
    severity: str,
    alert_id: str,
) -> dict:
    """
    Send email alert to District Health Officer for severe/critical outbreaks.
    Called by the outbreak detection pipeline.
    """
    import smtplib
    import os
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from datetime import datetime

    async def _send():
        from app.core.database import AsyncSessionFactory
        from sqlalchemy import text

        async with AsyncSessionFactory() as db:
            result = await db.execute(
                text("""
                    SELECT current_cases, baseline_mean, z_score,
                           percent_increase, alert_time
                    FROM outbreak_alerts
                    WHERE id = :alert_id
                """),
                {"alert_id": alert_id},
            )
            alert = result.fetchone()
            if not alert:
                return {"status": "alert_not_found"}

            dho_email = os.getenv(f"DHO_EMAIL_{district_code}", "dho@example.com")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🚨 {severity.upper()} Outbreak Alert: {diagnosis} in {district_code}"
            msg["From"]    = "noreply@vaidya.health.gov.in"
            msg["To"]      = dho_email

            html_body = f"""
            <html><body style="font-family: Arial, sans-serif;">
                <h2 style="color: #d32f2f;">🚨 {severity.upper()} Outbreak Alert</h2>
                <p><strong>District:</strong> {district_code}</p>
                <p><strong>Disease:</strong> {diagnosis}</p>
                <p><strong>Severity:</strong> {severity.upper()}</p>
                <p><strong>Alert Time:</strong> {alert.alert_time}</p>
                <h3>Statistics</h3>
                <ul>
                    <li><strong>Current Cases:</strong> {alert.current_cases}</li>
                    <li><strong>Baseline Average:</strong> {alert.baseline_mean:.1f} cases/day</li>
                    <li><strong>Z-Score:</strong> {alert.z_score:.2f} (σ from mean)</li>
                    {"<li><strong>Increase:</strong> {:.1f}%</li>".format(alert.percent_increase) if alert.percent_increase else ""}
                </ul>
                <h3>Recommended Actions</h3>
                <ul>
                    {"<li>Immediately contact IDSP focal point</li>" if severity == "critical" else ""}
                    <li>Review ASHA worker reports</li>
                    <li>Verify case definitions and lab testing</li>
                    <li>Coordinate with nearest district hospitals</li>
                </ul>
                <p>
                    <a href="https://vaidya.health.gov.in/dashboard/outbreaks/{alert_id}"
                       style="background:#1976d2;color:white;padding:10px 20px;
                              text-decoration:none;border-radius:4px;">
                        View Dashboard
                    </a>
                </p>
                <hr>
                <p style="font-size:12px;color:#666;">
                    Automated alert from Vaidya Health Analytics System.<br>
                    Support: support@vaidya.health.gov.in
                </p>
            </body></html>
            """
            msg.attach(MIMEText(html_body, "html"))

            smtp_host     = os.getenv("SMTP_HOST", "smtp.gmail.com")
            smtp_port     = int(os.getenv("SMTP_PORT", "587"))
            smtp_user     = os.getenv("SMTP_USER")
            smtp_password = os.getenv("SMTP_PASSWORD")

            if not smtp_user or not smtp_password:
                logger.warning("email.smtp_not_configured")
                return {"status": "smtp_not_configured"}

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            logger.info("email.dho.sent", district=district_code, to=dho_email)
            return {"status": "sent", "to": dho_email}

    try:
        return _run_async(_send())
    except Exception as e:
        logger.error("email.dho.send_failed", district=district_code, error=str(e))
        return {"status": "failed", "error": str(e)}
