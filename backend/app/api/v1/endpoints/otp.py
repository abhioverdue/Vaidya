"""
Vaidya — OTP endpoints
POST /send           — generate random code, store in Redis (or memory), deliver via Fast2SMS
POST /verify         — validate code against Redis (or memory)
POST /reset-password — validate code then update Firebase password via Admin SDK
"""
import base64
import json
import random
import time
from typing import Dict, Tuple

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.redis import get_redis, is_null_redis

router = APIRouter()
logger = structlog.get_logger(__name__)

# ── In-memory OTP store (fallback when Redis is unavailable) ──────────────────
# _mem_otp:  phone → (otp_str, expiry_unix_ts)
# _mem_rl:   phone → (request_count, window_start_unix_ts)
_mem_otp: Dict[str, Tuple[str, float]] = {}
_mem_rl:  Dict[str, Tuple[int, float]] = {}


def _mem_set_otp(phone: str, otp: str, ttl: int = 300) -> None:
    _mem_otp[phone] = (otp, time.time() + ttl)


def _mem_get_otp(phone: str) -> str | None:
    entry = _mem_otp.get(phone)
    if entry and time.time() < entry[1]:
        return entry[0]
    _mem_otp.pop(phone, None)
    return None


def _mem_del_otp(phone: str) -> None:
    _mem_otp.pop(phone, None)


def _mem_rate_limit(phone: str, max_count: int = 3, window: int = 600) -> int:
    """Increment and return the request count for this phone within the window."""
    now = time.time()
    count, start = _mem_rl.get(phone, (0, now))
    if now - start > window:
        count, start = 0, now
    count += 1
    _mem_rl[phone] = (count, start)
    return count


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen_otp() -> str:
    return f"{random.randint(100000, 999999)}"


def _normalise_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


async def _send_fast2sms(phone: str, otp: str) -> bool:
    if not settings.FAST2SMS_API_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(
                "https://www.fast2sms.com/dev/bulkV2",
                headers={"authorization": settings.FAST2SMS_API_KEY},
                json={"variables_values": otp, "route": "otp", "numbers": phone},
            )
            ok = r.status_code == 200 and r.json().get("return") is True
            logger.info("vaidya.otp.fast2sms", sent=ok, phone_tail=phone[-4:])
            return ok
    except Exception as exc:
        logger.warning("vaidya.otp.fast2sms_failed", error=str(exc))
        return False


# ── Firebase Admin (lazy-init, module-level singleton) ───────────────────────

_fb_ready = False


def _ensure_firebase_admin() -> bool:
    global _fb_ready
    if _fb_ready:
        return True
    if not settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials as fb_creds

        if not firebase_admin._apps:
            sa = json.loads(base64.b64decode(settings.FIREBASE_SERVICE_ACCOUNT_JSON))
            firebase_admin.initialize_app(fb_creds.Certificate(sa))
        _fb_ready = True
        return True
    except Exception as exc:
        logger.error("vaidya.firebase_admin.init_failed", error=str(exc))
        return False


async def _firebase_update_password(phone: str, new_password: str) -> bool:
    if not _ensure_firebase_admin():
        return False
    try:
        from firebase_admin import auth as fb_auth

        email = f"{phone}@vaidya.app"
        user = fb_auth.get_user_by_email(email)
        fb_auth.update_user(user.uid, password=new_password)
        logger.info("vaidya.firebase_admin.password_updated", phone_tail=phone[-4:])
        return True
    except Exception as exc:
        logger.error("vaidya.firebase_admin.update_failed", error=str(exc))
        return False


# ── Request / response models ─────────────────────────────────────────────────

class OtpSendReq(BaseModel):
    phone: str
    type: str = "register"


class OtpVerifyReq(BaseModel):
    phone: str
    otp: str


class OtpResetReq(BaseModel):
    phone: str
    otp: str
    new_password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/send")
async def otp_send(body: OtpSendReq, redis=Depends(get_redis)):
    use_mem = is_null_redis(redis)

    phone = _normalise_phone(body.phone)
    if not phone.isdigit() or len(phone) != 10:
        raise HTTPException(400, "Enter a valid 10-digit mobile number")

    # Rate limit: max 3 OTP requests per phone per 10 minutes
    if use_mem:
        count = _mem_rate_limit(phone)
    else:
        rl_key = f"otp_rl:{phone}"
        count = await redis.incr(rl_key)
        if count == 1:
            await redis.expire(rl_key, 600)

    if count > 3:
        raise HTTPException(429, "Too many OTP requests. Please wait 10 minutes before trying again.")

    otp = _gen_otp()
    if use_mem:
        _mem_set_otp(phone, otp, ttl=300)
        logger.info("vaidya.otp.mem_store", phone_tail=phone[-4:])
    else:
        await redis.setex(f"otp:{phone}", 300, otp)

    sms_sent = await _send_fast2sms(phone, otp)

    return {
        "message": (
            "OTP sent to your registered mobile number."
            if sms_sent
            else "OTP generated for your session."
        ),
        "expires_in": 300,
        # demo_otp is only returned when real SMS couldn't be delivered.
        # It is null when sms_sent=True so nothing leaks in production.
        "demo_otp": None if sms_sent else otp,
    }


@router.post("/verify")
async def otp_verify(body: OtpVerifyReq, redis=Depends(get_redis)):
    phone = _normalise_phone(body.phone)

    if is_null_redis(redis):
        stored = _mem_get_otp(phone)
    else:
        stored = await redis.get(f"otp:{phone}")

    if not stored or stored != body.otp:
        return {"valid": False, "message": "Invalid or expired OTP. Please try again."}
    # Keep entry alive so reset-password can re-verify in the same session
    return {"valid": True, "message": "OTP verified successfully."}


@router.post("/reset-password")
async def otp_reset_password(body: OtpResetReq, redis=Depends(get_redis)):
    phone = _normalise_phone(body.phone)
    use_mem = is_null_redis(redis)

    if use_mem:
        stored = _mem_get_otp(phone)
    else:
        stored = await redis.get(f"otp:{phone}")

    if not stored or stored != body.otp:
        raise HTTPException(400, "Invalid or expired OTP")

    if len(body.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    updated = await _firebase_update_password(phone, body.new_password)
    if not updated:
        raise HTTPException(
            503,
            "Password reset is unavailable right now. Please try the in-app Change Password instead.",
        )

    if use_mem:
        _mem_del_otp(phone)
    else:
        await redis.delete(f"otp:{phone}")
    return {"message": "Password reset successfully. You can now sign in with your new password."}
