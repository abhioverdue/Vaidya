"""
Vaidya — centralised configuration
All secrets pulled from environment variables / .env file
"""

from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, field_validator
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
    DATABASE_URL: str = (
        "postgresql+asyncpg://vaidya:vaidya_secret@localhost:5432/vaidya"
    )
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
        "http://127.0.0.1:3000",
        "http://localhost:8081",    # Expo web
        "http://127.0.0.1:8081",
        "http://localhost:19000",   # Expo Go
        "http://127.0.0.1:19000",
        "http://localhost:19006",   # Expo web legacy
        "http://127.0.0.1:19006",
        "http://10.0.2.2:8081",    # Android emulator → host Expo
        "https://vaidya.health",
    ]

    # ── Gemini (LLM) ─────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""            # Google AI Studio key — free tier: 15 RPM
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_TIMEOUT: int = 30            # seconds
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

    # ── Notifications (FCM HTTP v1 API — replaces deprecated Legacy Server Key) ─────
    # The Legacy FCM Server Key (AAAAxxx) was shut down June 2024.
    # Use Firebase Admin SDK credentials (service account JSON) instead.
    # GET FROM: Firebase Console → Project Settings → Service Accounts → Generate new private key
    GOOGLE_APPLICATION_CREDENTIALS: str = ""   # path to service-account.json file
    FCM_PROJECT_ID: str = ""                   # Firebase project ID (e.g. vaidya-health-prod)
    TWILIO_ACCOUNT_SID: str = ""               # Twilio SMS (free trial)
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

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

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def parse_database_url(cls, v):
        if isinstance(v, str) and not v.strip():
            return (
                "postgresql+asyncpg://vaidya:vaidya_secret@localhost:5432/vaidya"
            )
        return v

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def parse_redis_url(cls, v):
        if isinstance(v, str) and not v.strip():
            return "redis://:redis_secret@localhost:6379/0"
        return v

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            parsed = [i.strip() for i in v.split(",") if i.strip()]
            return parsed if parsed else [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:8081",
                "http://127.0.0.1:8081",
                "http://localhost:19000",
                "http://127.0.0.1:19000",
                "http://localhost:19006",
                "http://127.0.0.1:19006",
                "http://10.0.2.2:8081",
                "https://vaidya.health",
            ]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
