"""
Vaidya — /api/v1/auth

POST /otp/request     — generate and store OTP (6-digit, 5-min TTL)
POST /otp/verify      — verify OTP
POST /register        — create account (requires valid OTP in store)
POST /login           — authenticate and get JWT
POST /password/reset  — reset password using OTP
POST /password/change — change password for authenticated user
"""

import random
import string
import time
import uuid as _uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    get_current_user_id,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.models.models import User

router = APIRouter()
logger = structlog.get_logger(__name__)

OTP_TTL = 300        # 5 minutes
OTP_PREFIX = "vaidya:otp:"

# ── In-memory OTP fallback (used when Redis is unavailable) ───────────────────
# Maps phone → (otp_code, expiry_unix_timestamp)
_mem_otp: dict[str, tuple[str, float]] = {}


async def _store_otp(redis, phone: str, otp: str) -> None:
    try:
        await redis.setex(f"{OTP_PREFIX}{phone}", OTP_TTL, otp)
    except Exception:
        _mem_otp[phone] = (otp, time.time() + OTP_TTL)


async def _get_otp(redis, phone: str) -> Optional[str]:
    try:
        return await redis.get(f"{OTP_PREFIX}{phone}")
    except Exception:
        entry = _mem_otp.get(phone)
        if entry and entry[1] > time.time():
            return entry[0]
        return None


async def _delete_otp(redis, phone: str) -> None:
    try:
        await redis.delete(f"{OTP_PREFIX}{phone}")
    except Exception:
        _mem_otp.pop(phone, None)


# ── Schemas ────────────────────────────────────────────────────────────────────

class OtpRequestBody(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    type: str  = Field(..., pattern="^(register|reset)$")


class OtpVerifyBody(BaseModel):
    phone: str
    otp: str = Field(..., min_length=6, max_length=6)


class RegisterBody(BaseModel):
    name:     str = Field(..., min_length=1,  max_length=200)
    phone:    str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=6,  max_length=128)


class LoginBody(BaseModel):
    phone:    str
    password: str


class ResetPasswordBody(BaseModel):
    phone:        str
    otp:          str
    new_password: str = Field(..., min_length=6, max_length=128)


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password:     str = Field(..., min_length=6, max_length=128)


class UserOut(BaseModel):
    id:        str
    name:      str
    phone:     str
    age_group: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserOut


# ── Helpers ────────────────────────────────────────────────────────────────────

def _gen_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/otp/request")
async def otp_request(body: OtpRequestBody, redis=Depends(get_redis)):
    otp = _gen_otp()
    await _store_otp(redis, body.phone, otp)
    logger.info("vaidya.otp.issued", phone=body.phone[-4:], type=body.type)

    if settings.TWILIO_ACCOUNT_SID:
        import httpx as _httpx
        try:
            async with _httpx.AsyncClient() as _client:
                await _client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                    data={
                        "From": settings.TWILIO_FROM_NUMBER,
                        "To":   f"+91{body.phone}",
                        "Body": f"Your Vaidya OTP is {otp}. Valid for 5 minutes. Do not share.",
                    },
                    auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                    timeout=10,
                )
            msg = f"OTP sent to +91 {body.phone[-4:].rjust(len(body.phone), '*')}"
        except Exception as _exc:
            logger.warning("vaidya.otp.sms_failed", error=str(_exc))
            msg = f"OTP for +91{body.phone}: {otp}"  # fallback: surface in response
    else:
        # No SMS provider configured — surface code in response for demo
        msg = f"OTP for +91{body.phone}: {otp}"

    return {"message": msg, "expires_in": OTP_TTL}


@router.post("/otp/verify")
async def otp_verify(body: OtpVerifyBody, redis=Depends(get_redis)):
    stored = await _get_otp(redis, body.phone)
    if stored is None:
        return {"valid": False, "message": "OTP expired. Please request a new code."}
    if stored != body.otp:
        return {"valid": False, "message": "Invalid OTP. Please check and try again."}
    return {"valid": True, "message": "OTP verified successfully"}


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterBody,
    redis=Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    stored = await _get_otp(redis, body.phone)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired. Please go back and request a new code.",
        )

    result = await db.execute(select(User).where(User.phone == body.phone))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this mobile number already exists.",
        )

    user = User(
        name=body.name,
        phone=body.phone,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await _delete_otp(redis, body.phone)

    token = create_access_token(str(user.id), {"phone": user.phone})
    logger.info("vaidya.auth.registered", user_id=str(user.id))
    return AuthResponse(
        access_token=token,
        user=UserOut(id=str(user.id), name=user.name, phone=user.phone),
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginBody, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == body.phone))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid mobile number or password.",
        )

    token = create_access_token(str(user.id), {"phone": user.phone})
    logger.info("vaidya.auth.login", user_id=str(user.id))
    return AuthResponse(
        access_token=token,
        user=UserOut(id=str(user.id), name=user.name, phone=user.phone),
    )


@router.post("/password/reset")
async def password_reset(
    body: ResetPasswordBody,
    redis=Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    stored = await _get_otp(redis, body.phone)
    if stored is None or stored != body.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP.",
        )

    result = await db.execute(select(User).where(User.phone == body.phone))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this number.",
        )

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    await _delete_otp(redis, body.phone)
    logger.info("vaidya.auth.password_reset", user_id=str(user.id))
    return {"message": "Password reset successfully."}


@router.post("/password/change")
async def password_change(
    body: ChangePasswordBody,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = _uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    logger.info("vaidya.auth.password_changed", user_id=user_id)
    return {"message": "Password changed successfully."}
