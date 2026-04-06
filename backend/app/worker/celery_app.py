"""
Vaidya — Celery worker
Tasks: ASHA push notifications, follow-up reminders, nightly data aggregation,
       outbreak anomaly detection (TimescaleDB analytics module)
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "vaidya",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.worker.tasks",
        "app.services.diagnosis.outbreak_detection",  # outbreak pipeline
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_queues={
        "notifications": {"exchange": "notifications", "routing_key": "notifications"},
        "followups":     {"exchange": "followups",     "routing_key": "followups"},
        "maintenance":   {"exchange": "maintenance",   "routing_key": "maintenance"},
        "analytics":     {"exchange": "analytics",     "routing_key": "analytics"},
    },
    task_default_queue="notifications",
    task_routes={
        # Existing notification tasks
        "app.worker.tasks.notify_asha_fcm":                    {"queue": "notifications"},
        "app.worker.tasks.notify_asha_sms":                    {"queue": "notifications"},
        "app.worker.tasks.bulk_notify_district":               {"queue": "notifications"},
        "app.worker.tasks.schedule_followup":                  {"queue": "followups"},
        "app.worker.tasks.send_followup_reminders":            {"queue": "maintenance"},
        "app.worker.tasks.aggregate_district_stats":           {"queue": "maintenance"},
        "app.worker.tasks.cleanup_raw_text":                   {"queue": "maintenance"},
        "app.worker.tasks._clear_stale_fcm_token":             {"queue": "maintenance"},
        "app.worker.tasks._send_district_officer_email":      {"queue": "notifications"},
        # Analytics / outbreak tasks
        "outbreak.detect_anomalies":                           {"queue": "analytics"},
        "outbreak.update_baselines":                           {"queue": "analytics"},
    },
    # Beat schedule
    beat_schedule={
        # ── Existing maintenance tasks ──────────────────────────────────────────
        "nightly-district-aggregation": {
            "task": "app.worker.tasks.aggregate_district_stats",
            "schedule": crontab(hour=1, minute=0),    # 1 AM IST
        },
        "cleanup-raw-text": {
            "task": "app.worker.tasks.cleanup_raw_text",
            "schedule": crontab(hour=2, minute=0),    # 2 AM IST — DPDP compliance
        },
        "send-followup-reminders": {
            "task": "app.worker.tasks.send_followup_reminders",
            "schedule": crontab(minute="*/30"),        # every 30 min
        },
        # ── Analytics / outbreak detection tasks ────────────────────────────────
        "detect-outbreaks-every-15-min": {
            "task": "outbreak.detect_anomalies",
            "schedule": crontab(minute="*/15"),        # every 15 minutes
        },
        "update-outbreak-baselines-daily": {
            "task": "outbreak.update_baselines",
            "schedule": crontab(hour=2, minute=30),   # 2:30 AM IST daily
        },
    },
)
