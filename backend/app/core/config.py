"""
Vaidya — centralised configuration
All secrets pulled from environment variables / .env file
"""

from functools import lru_cache
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────────
    ENV: str = "development"
    VERSION: str = "0.1.0"
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    DEBUG: bool = False

    # ── Database ─────────────────────────────────────────────────────────────────
    # Leave empty to use the SQLite fallback (sqlite+aiosqlite:///./vaidya_local.db)
    # Set in .env to use PostgreSQL: DATABASE_URL=postgresql+asyncpg://...
    DATABASE_URL: str = ""
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── Redis ─────────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://:redis_secret@localhost:6379/0"
    REDIS_TTL_SYMPTOMS: int = 600       # 10 min cache for identical symptom text
    REDIS_TTL_HOSPITALS: int = 86400    # 24h cache for hospital lookup by GPS cell
    REDIS_TTL_GEOCODE:   int = 3600     # 1h cache for reverse geocode results

    # ── CORS ─────────────────────────────────────────────────────────────────────
    # Override in .env:  ALLOWED_ORIGINS=https://myapp.com,http://192.168.1.42:8081
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8081",    # Expo web
        "http://localhost:19000",   # Expo Go
        "http://localhost:19006",   # Expo web legacy
        "http://10.0.2.2:8081",    # Android emulator → host Expo
        "https://vaidya.health",
    ]

    # ── Gemini (LLM) ─────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""            # Google AI Studio key — free tier: 15 RPM
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TIMEOUT: int = 30            # seconds
    WHISPER_MODEL: str = "tiny"   # faster-whisper size: tiny|base|small|medium|large-v3
    # DEPRECATED — Ollama fully replaced by Gemini. These settings are retained
    # only so that any operator .env files with OLLAMA_* vars don't cause startup
    # errors (pydantic-settings extra="ignore" handles unknown keys, but explicit
    # declaration is safer). Do NOT use these in new code.
    OLLAMA_BASE_URL: str = ""   # unused — Gemini handles all LLM calls
    OLLAMA_MODEL: str = ""      # unused
    OLLAMA_TIMEOUT: int = 60    # re-used as fallback httpx timeout for extractor

    # ── Models (paths inside container) ─────────────────────────────────────────
    MODEL_DIR: str = "/app/models"

    # NLP (nlp2.ipynb — Cell 14 save names)
    NLP_MODEL_PATH: str        = "/app/models/nlp/final_nlp_model.pkl"
    NLP_ENCODER_PATH: str      = "/app/models/nlp/label_encoder.pkl"
    NLP_SYMPTOM_LIST_PATH: str = "/app/models/nlp/final_symptom_list.pkl"

    # Audio (audio.ipynb — Cell 13 save names)
    AUDIO_MODEL_PATH: str         = "/app/models/audio/audio_model.pkl"
    AUDIO_SCALER_PATH: str        = "/app/models/audio/audio_scaler.pkl"
    AUDIO_LABEL_ENCODER_PATH: str = "/app/models/audio/audio_label_encoder.pkl"

    # Vision (Computer_Vision_AIforHealth.ipynb — Cell 4 save name)
    VISION_MODEL_PATH: str = "/app/models/vision/hybrid_multitask_model.pth"

    # ── Diagnosis confidence threshold ──────────────────────────────────────────
    CONFIDENCE_THRESHOLD: float = 0.60  # below this → LLM fallback

    # ── External APIs (all free) ─────────────────────────────────────────────────
    ESANJEEVANI_BASE_URL: str = "https://esanjeevaniopd.in/api"
    OVERPASS_API_URL: str = "https://overpass-api.de/api/interpreter"
    NOMINATIM_URL: str = "https://nominatim.openstreetmap.org"
    # Google Maps API key — same key as frontend (app.json). Needs Places API enabled.
    GOOGLE_MAPS_API_KEY: str = "AIzaSyCDzqroisSBOKa86sJUIRoB-4Mjlwk0_l0"

    # ── Notifications (FCM HTTP v1 API — replaces deprecated Legacy Server Key) ─────
    # The Legacy FCM Server Key (AAAAxxx) was shut down June 2024.
    # Use Firebase Admin SDK credentials (service account JSON) instead.
    # GET FROM: Firebase Console → Project Settings → Service Accounts → Generate new private key
    GOOGLE_APPLICATION_CREDENTIALS: str = ""   # path to service-account.json file
    FCM_PROJECT_ID: str = ""                   # Firebase project ID (e.g. vaidya-health-prod)
    TWILIO_ACCOUNT_SID: str = ""               # Twilio SMS (free trial)
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Fast2SMS — free Indian SMS gateway for OTP delivery
    # Get key at: https://www.fast2sms.com/ → API → Dev API
    FAST2SMS_API_KEY: str = ""

    # Firebase Admin SDK — base64-encoded service account JSON
    # Generate at: Firebase Console → Project Settings → Service Accounts → Generate new private key
    # Then base64-encode: base64 -i serviceAccount.json
    FIREBASE_SERVICE_ACCOUNT_JSON: str = ""

    # ── ABDM (Ayushman Bharat Digital Mission) ───────────────────────────────────
    ABDM_BASE_URL: str = "https://sandbox.abdm.gov.in/api/v3"
    ABDM_CLIENT_ID: str = ""
    # ABDM rate limits: 100 req/min per client_id (sandbox)
    # See: https://sandbox.abdm.gov.in/abdm-docs/
    ABDM_CLIENT_SECRET: str = ""

    # ── Sentry (free tier observability) ────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── Rate limiting ─────────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Auth ──────────────────────────────────────────────────────────────────────
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7   # 7 days

    @model_validator(mode="before")
    @classmethod
    def parse_origins(cls, data):
        import json as _json
        v = data.get("ALLOWED_ORIGINS") if isinstance(data, dict) else None
        if not isinstance(v, str):
            return data
        stripped = v.strip()
        if not stripped:
            data["ALLOWED_ORIGINS"] = [
                "http://localhost:3000",
                "http://localhost:8081",
                "http://localhost:19000",
                "http://localhost:19006",
                "http://10.0.2.2:8081",
            ]
        elif stripped in ("*", '["*"]'):
            data["ALLOWED_ORIGINS"] = ["*"]
        elif stripped.startswith("["):
            try:
                data["ALLOWED_ORIGINS"] = _json.loads(stripped)
            except ValueError:
                data["ALLOWED_ORIGINS"] = [i.strip() for i in stripped.split(",")]
        else:
            data["ALLOWED_ORIGINS"] = [i.strip() for i in stripped.split(",")]
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
