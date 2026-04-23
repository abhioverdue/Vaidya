"""
Vaidya — FCM HTTP v1 API client
Replaces the deprecated Legacy Server Key (shut down June 2024).

How FCM v1 works vs the old API:
  OLD (dead): POST fcm.googleapis.com/fcm/send
              Authorization: key=AAAAxxxxx  ← Legacy Server Key, DEAD

  NEW (v1):   POST fcm.googleapis.com/v1/projects/{project_id}/messages:send
              Authorization: Bearer {short-lived OAuth2 access token}
              Token obtained from a Google service account JSON — auto-refreshed.

Setup (one-time, 3 steps):
  1. Firebase Console → Project Settings → Service Accounts tab
  2. Click "Generate new private key" → downloads service-account.json (~2KB)
  3. Add to .env:
       GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/service-account.json
       FCM_PROJECT_ID=your-firebase-project-id

The google-auth library handles OAuth2 token refresh automatically.
Tokens expire in 1 hour — cached in memory, refreshed 2 min before expiry.
"""

import time
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ── Token cache ────────────────────────────────────────────────────────────────
_cached_token:    Optional[str] = None
_token_expiry_ts: float         = 0.0
_TOKEN_BUFFER_S:  int           = 120    # refresh 2 min before expiry

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def _get_access_token(credentials_path: str) -> str:
    """
    Get a short-lived OAuth2 Bearer token from the service account JSON.
    Caches in module-level variables — thread-safe for Celery single-threaded workers.
    """
    global _cached_token, _token_expiry_ts

    now = time.monotonic()
    if _cached_token and now < (_token_expiry_ts - _TOKEN_BUFFER_S):
        return _cached_token

    try:
        import datetime as dt
        import google.auth.transport.requests
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=[FCM_SCOPE],
        )
        creds.refresh(google.auth.transport.requests.Request())

        _cached_token    = creds.token
        _token_expiry_ts = (
            now + (creds.expiry - dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)).total_seconds()
            if creds.expiry else now + 3600
        )

        logger.debug(
            "vaidya.fcm_v1.token_refreshed",
            expires_in_s=round(_token_expiry_ts - now),
        )
        return _cached_token

    except ImportError:
        raise RuntimeError(
            "google-auth not installed. Run: pip install google-auth"
        )
    except Exception as exc:
        raise RuntimeError(f"FCM OAuth2 token fetch failed: {exc}") from exc


def _build_message(
    fcm_token:    str,
    session_id:   str,
    worker_id:    str,
    triage_level: int,
    diagnosis:    str,
    is_reminder:  bool = False,
) -> dict:
    """Build FCM HTTP v1 message body for ASHA worker alert."""
    urgency_prefix = {
        5: "🔴 EMERGENCY",
        4: "🟠 URGENT",
        3: "🟡 Action needed",
    }.get(triage_level, "📋 Follow-up")

    body = {
        5: f"Patient needs EMERGENCY care — {diagnosis}. Call 108 NOW.",
        4: f"Patient needs urgent care within 24h — {diagnosis}.",
        3: f"Patient should visit PHC within 48h — {diagnosis}.",
        2: f"Patient monitoring needed — {diagnosis}.",
        1: f"Routine follow-up — {diagnosis}.",
    }.get(triage_level, f"New patient alert — {diagnosis}")

    if is_reminder:
        title = "Vaidya: Follow-up reminder"
        body  = f"Patient follow-up due (Level {triage_level}: {diagnosis[:40]}). Please check in."
    else:
        title = f"Vaidya: {urgency_prefix}"

    return {
        "message": {
            "token": fcm_token,           # v1: token goes here, NOT "to"
            "notification": {
                "title": title,
                "body":  body,
            },
            "data": {                     # v1: all values must be strings
                "session_id":   session_id,
                "worker_id":    worker_id,
                "triage_level": str(triage_level),
                "diagnosis":    diagnosis[:100],
                "action":       "followup_reminder" if is_reminder else "open_session",
            },
            "android": {
                "priority": "high" if (triage_level >= 4 and not is_reminder) else "normal",
                "notification": {
                    "channel_id":              "vaidya_followup" if is_reminder else "vaidya_triage",
                    "notification_priority":   (
                        "PRIORITY_HIGH" if triage_level >= 4 else "PRIORITY_DEFAULT"
                    ),
                    "default_vibrate_timings": True,
                    "sound":                   "default",
                    "click_action":            "OPEN_ASHA_QUEUE",
                },
            },
            "apns": {
                "payload": {
                    "aps": {
                        "alert": {"title": title, "body": body},
                        "sound": "default",
                        "badge": 1,
                    }
                },
                "headers": {
                    "apns-priority": "10" if (triage_level >= 4 and not is_reminder) else "5",
                },
            },
        }
    }


def send_fcm_v1(
    fcm_token:        str,
    session_id:       str,
    worker_id:        str,
    triage_level:     int,
    diagnosis:        str,
    credentials_path: str,
    project_id:       str,
    is_reminder:      bool = False,
) -> dict:
    """
    Send a single FCM notification via HTTP v1 API.
    Synchronous — intended for Celery task context.

    Returns dict with 'status' key:
      'sent'              — delivered successfully
      'token_invalid'     — UNREGISTERED or INVALID_ARGUMENT → clear token from DB
      'retry'             — 429 / 500 / 503 → caller should retry
      'credentials_error' — service account problem
      'timeout'           — FCM API unreachable
      'failed'            — other HTTP error
    """
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

    try:
        token   = _get_access_token(credentials_path)
        payload = _build_message(
            fcm_token, session_id, worker_id, triage_level, diagnosis, is_reminder
        )

        resp = httpx.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            timeout=15,
        )

        if resp.status_code == 200:
            # v1 returns resource name like "projects/.../messages/0:xxxx"
            msg_name = resp.json().get("name", "")
            logger.info(
                "vaidya.fcm_v1.sent",
                session=session_id[:8],
                worker=worker_id[:8],
                level=triage_level,
                reminder=is_reminder,
            )
            return {"status": "sent", "message_name": msg_name}

        # Parse v1 error body
        try:
            err      = resp.json().get("error", {})
            details  = err.get("details", [])
            fcm_code = next(
                (d.get("errorCode") for d in details if "errorCode" in d),
                None,
            )
            message  = err.get("message", resp.text[:200])
        except Exception:
            fcm_code, message = None, resp.text[:200]

        logger.warning(
            "vaidya.fcm_v1.http_error",
            status=resp.status_code,
            fcm_code=fcm_code,
            msg=message[:80],
        )

        # UNREGISTERED = app uninstalled / token rotated → stop retrying, clear token
        if fcm_code in ("UNREGISTERED", "INVALID_ARGUMENT") or resp.status_code == 404:
            return {"status": "token_invalid", "fcm_code": fcm_code}

        # Transient errors → caller retries
        if resp.status_code in (429, 500, 503):
            return {"status": "retry", "http_status": resp.status_code}

        return {"status": "failed", "http_status": resp.status_code, "error": message}

    except RuntimeError as exc:
        logger.error("vaidya.fcm_v1.credentials_error", error=str(exc))
        return {"status": "credentials_error", "error": str(exc)}

    except httpx.TimeoutException:
        logger.warning("vaidya.fcm_v1.timeout")
        return {"status": "timeout"}

    except Exception as exc:
        logger.error("vaidya.fcm_v1.error", error=str(exc))
        return {"status": "error", "error": str(exc)}
