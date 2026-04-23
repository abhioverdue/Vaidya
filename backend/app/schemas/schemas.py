"""
Vaidya — Pydantic v2 schemas for all API contracts
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ── Base ───────────────────────────────────────────────────────────────────────

class VaidyaBase(BaseModel):
    model_config = {"from_attributes": True}


# ── Input schemas ──────────────────────────────────────────────────────────────

class TextInputRequest(BaseModel):
    text: str = Field(..., min_length=5, max_length=2000,
                      description="Raw symptom description in any supported language")
    language: Optional[str] = Field(None, pattern="^(en|hi|ta)$",
                                     description="ISO language code; auto-detected if omitted")
    patient_id: Optional[UUID] = None
    self_severity: Optional[int] = Field(None, ge=1, le=10)

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


class VoiceInputResponse(BaseModel):
    transcript: str
    detected_language: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    english_transcript: Optional[str] = None
    translation_method: Optional[str] = None


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=2000)
    source_language: str = Field(..., pattern="^(hi|ta)$")


class TranslateResponse(BaseModel):
    original: str
    translated: str
    source_language: str
    method: str   # "indictrans2" | "local_map" | "passthrough"


class AudioQualityMeta(BaseModel):
    ok: bool
    duration_s: Optional[float] = None
    rms_energy: Optional[float] = None
    reason: Optional[str] = None


# ── NLP / extraction schemas ───────────────────────────────────────────────────

class ExtractedSymptoms(BaseModel):
    symptoms: List[str] = Field(default_factory=list)
    duration: Optional[str] = None
    severity_estimate: Optional[int] = Field(None, ge=1, le=10)
    body_parts: List[str] = Field(default_factory=list)
    raw_keywords: List[str] = Field(default_factory=list)


class SymptomVectorResponse(BaseModel):
    extracted: ExtractedSymptoms
    symptom_vector: dict[str, int]       # {fever: 1, cough: 1, ...}
    matched_count: int
    unmatched_terms: List[str]


# ── Diagnosis schemas ──────────────────────────────────────────────────────────

class DiagnosisResult(BaseModel):
    primary_diagnosis: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    differential: List[dict] = Field(
        default_factory=list,
        description="[{disease: str, confidence: float}, ...]"
    )
    diagnosis_source: str           # xgboost | llm_gemini | fusion
    red_flags: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    precautions: List[str] = Field(default_factory=list)
    # LLM-enriched fields (populated when diagnosis_source == "llm_gemini")
    icd_hint: Optional[str] = None
    triage_level: Optional[int] = Field(None, ge=1, le=5)
    triage_reasoning: Optional[str] = None
    when_to_seek_emergency: Optional[str] = None
    confidence_reason: Optional[str] = None
    disclaimer: str = (
        "This is an AI-assisted triage tool. It is NOT a prescription or a substitute "
        "for a qualified doctor. Please consult a licensed medical professional."
    )


# ── Triage schemas ─────────────────────────────────────────────────────────────

TRIAGE_LABELS = {
    1: "Self-care",
    2: "Monitor at home",
    3: "Visit PHC / GP within 48h",
    4: "Seek care within 24h — urgent",
    5: "Emergency — go to hospital now",
}

class TriageResponse(BaseModel):
    level: int = Field(..., ge=1, le=5)
    label: str
    reasoning: str
    asha_assigned: Optional[dict] = None    # {name, phone, distance_km}
    follow_up_at: Optional[datetime] = None


# ── Full session response ──────────────────────────────────────────────────────

class FullTriageResponse(BaseModel):
    session_id: UUID
    input_language: str
    extracted: ExtractedSymptoms
    diagnosis: DiagnosisResult
    triage: TriageResponse
    audio_result:   Optional[dict] = None
    vision_result:  Optional[dict] = None
    fusion_weights: Optional[dict] = None
    created_at: datetime


# ── Hospital schemas ───────────────────────────────────────────────────────────

class HospitalResult(BaseModel):
    id: UUID
    name: str
    hospital_type: str
    address: Optional[str]
    distance_km: float
    phone: Optional[str]
    ambulance_108: bool
    open_24h: bool
    pmjay_empanelled: bool
    latitude: float
    longitude: float


class HospitalListResponse(BaseModel):
    results: List[HospitalResult]
    total: int
    patient_location: dict       # {lat, lng, district}


# ── Teleconsult schemas ────────────────────────────────────────────────────────

class TeleconsultSlot(BaseModel):
    doctor_name: str
    specialty: str
    languages: List[str]
    available_at: datetime
    platform: str = "eSanjeevani"
    booking_url: Optional[str] = None


class BookingRequest(BaseModel):
    session_id: UUID
    slot_id: str
    patient_name: str
    patient_phone: str


class BookingConfirmation(BaseModel):
    booking_id: str
    doctor_name: str
    scheduled_at: datetime
    join_url: str
    case_summary: str            # Pre-filled for doctor


# ── Patient schemas ────────────────────────────────────────────────────────────

class PatientCreate(BaseModel):
    preferred_language: str = Field("en", pattern="^(en|hi|ta)$")
    age_group: Optional[str] = Field(None, pattern="^(child|adult|senior)$")
    gender: Optional[str] = Field(None, pattern="^(male|female|other|undisclosed)$")
    district_code: Optional[str] = None
    abdm_health_id: Optional[str] = None

class PatientResponse(VaidyaBase):
    id: UUID
    preferred_language: str
    district_code: Optional[str]
    pmjay_eligible: bool
    created_at: datetime


# ── Health / meta ─────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    env: str
    redis: str


# ── Error ─────────────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
