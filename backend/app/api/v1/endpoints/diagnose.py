"""
Vaidya — /api/v1/diagnose  (Module 4 — complete)

POST /predict       — full multimodal triage: text + optional audio + optional image
POST /predict/text  — text-only fast path (no file uploads)
POST /audio         — standalone audio diagnosis
POST /image         — standalone image diagnosis
GET  /explain/{session_id} — explain fusion decision for a session
"""

import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.models import TriageSession
from app.schemas.schemas import (
    DiagnosisResult,
    FullTriageResponse,
    TextInputRequest,
)
from app.services.diagnosis.audio_model import run_audio_model
from app.services.diagnosis.fusion import fuse_signals, run_all_models_concurrent
from app.services.diagnosis.vision_model import run_vision_model
from app.services.nlp.extractor import extract_symptoms
from app.services.triage.engine import compute_triage

router = APIRouter()
logger = structlog.get_logger(__name__)

ALLOWED_AUDIO_MIME = {"audio/wav", "audio/ogg", "audio/mpeg", "audio/webm",
                      "audio/mp4", "audio/x-m4a", "application/octet-stream"}
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
MAX_AUDIO_BYTES    = 15 * 1024 * 1024
MAX_IMAGE_BYTES    = 10 * 1024 * 1024


def _write_tmp(content: bytes, suffix: str) -> str:
    """Write bytes to a temp file, return path."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
        return f.name


def _cleanup(*paths: str):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except Exception:
            pass


# ── POST /predict — full multimodal endpoint ──────────────────────────────────

@router.post(
    "/predict",
    response_model=FullTriageResponse,
    summary="Full multimodal triage — text + optional audio + optional image",
)
async def predict_multimodal(
    # Text (required)
    text: str = Form(..., min_length=5, max_length=2000),
    language: Optional[str] = Form(None, pattern="^(en|hi|ta)$"),
    self_severity: Optional[int] = Form(None, ge=1, le=10),
    patient_id: Optional[str] = Form(None),
    # Optional modalities
    audio_file: Optional[UploadFile] = File(None, description="Respiratory audio (wav/ogg/mp3)"),
    image_file: Optional[UploadFile] = File(None, description="Medical image (X-ray/wound/rash)"),
    image_task: Optional[str] = Form(None, pattern="^(chest|skin|wound)$"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    The main Vaidya triage endpoint — accepts text, and optionally audio and image.

    Pipeline:
      1. Extract symptoms from text (LLM + spaCy → 133-feature vector)
      2. Run XGBoost, audio model, vision model concurrently
      3. Fuse signals with confidence-weighted voting
      4. LLM fallback if fused confidence < threshold
      5. Compute triage severity (1–5) + ASHA assignment
      6. Persist session to PostgreSQL
      7. Return full structured response

    When only text is provided: XGBoost only (fastest path, ~1s).
    With audio: audio corroborates XGBoost respiratory disease hypotheses.
    With image: vision corroborates XGBoost skin/chest/wound hypotheses.
    With all three: full fusion, most accurate.
    """
    session_id = uuid.uuid4()
    log        = logger.bind(session_id=str(session_id))
    log.info("vaidya.diagnose.start", text_len=len(text), has_audio=audio_file is not None, has_image=image_file is not None)

    audio_tmp = image_tmp = None
    cleanup   = []

    try:
        # ── Stage 1: Extract symptoms ────────────────────────────────────────
        extracted, unmatched, symptom_vector = await extract_symptoms(
            text=text,
            language=language,
            redis=redis,
        )
        active_count = sum(symptom_vector.values())
        log.info("vaidya.diagnose.extracted", matched=len(extracted.symptoms), active=active_count)

        # ── Stage 2: Prepare optional modalities ─────────────────────────────
        if audio_file:
            content = await audio_file.read()
            if len(content) > MAX_AUDIO_BYTES:
                raise HTTPException(413, "Audio file too large (max 15MB)")
            if audio_file.content_type not in ALLOWED_AUDIO_MIME:
                raise HTTPException(415, f"Unsupported audio type: {audio_file.content_type}")
            audio_tmp = _write_tmp(content, ".wav")
            cleanup.append(audio_tmp)

        if image_file:
            content = await image_file.read()
            if len(content) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "Image file too large (max 10MB)")
            if image_file.content_type not in ALLOWED_IMAGE_MIME:
                raise HTTPException(415, f"Unsupported image type: {image_file.content_type}")
            suffix = ".jpg" if "jpeg" in (image_file.content_type or "") else ".png"
            image_tmp = _write_tmp(content, suffix)
            cleanup.append(image_tmp)

        # ── Stage 3: Run models concurrently ─────────────────────────────────
        nlp_result, audio_result, vision_result = await run_all_models_concurrent(
            symptom_vector=symptom_vector,
            audio_path=audio_tmp,
            image_path=image_tmp,
            image_task_type=image_task,
        )
        log.info(
            "vaidya.diagnose.models_done",
            nlp_top=nlp_result.primary_diagnosis,
            nlp_conf=round(nlp_result.confidence, 3),
            has_audio_result=audio_result is not None,
            has_vision_result=vision_result is not None,
        )

        # ── Stage 4: Fuse signals ─────────────────────────────────────────────
        diagnosis, fusion_weights = await fuse_signals(
            nlp_result=nlp_result,
            audio_result=audio_result,
            vision_result=vision_result,
            symptom_count=active_count,
            extracted_symptoms=extracted.symptoms,
            extracted_keywords=extracted.raw_keywords,
            self_severity=self_severity,
            language=language or "en",
        )
        log.info(
            "vaidya.diagnose.fused",
            primary=diagnosis.primary_diagnosis,
            confidence=round(diagnosis.confidence, 3),
            source=diagnosis.diagnosis_source,
        )

        # ── Stage 5: Triage ───────────────────────────────────────────────────
        try:
            pid = uuid.UUID(patient_id) if patient_id else None
        except ValueError:
            raise HTTPException(400, f"Invalid patient_id format: {patient_id}")
        
        triage = await compute_triage(
            diagnosis=diagnosis,
            self_severity=self_severity,
            patient_id=pid,
            db=db,
        )

        # ── Stage 6: Persist ──────────────────────────────────────────────────
        now = datetime.now(timezone.utc)
        session = TriageSession(
            id=session_id,
            patient_id=pid,
            input_language=language or "en",
            raw_text=text,
            extracted_keywords=extracted.raw_keywords,
            symptom_vector=symptom_vector,
            duration_text=extracted.duration,
            self_severity=self_severity,
            primary_diagnosis=diagnosis.primary_diagnosis,
            differential_diagnosis=diagnosis.differential,
            model_confidence=diagnosis.confidence,
            diagnosis_source=diagnosis.diagnosis_source,
            red_flags=diagnosis.red_flags,
            triage_level=triage.level,
            triage_label=triage.label,
            completed_at=now,
        )
        db.add(session)
        await db.flush()

        return FullTriageResponse(
            session_id=session_id,
            input_language=language or "en",
            extracted=extracted,
            diagnosis=diagnosis,
            triage=triage,
            audio_result=audio_result,
            vision_result=vision_result,
            fusion_weights=fusion_weights,
            created_at=now,
        )

    finally:
        _cleanup(*cleanup)


# ── POST /predict/text — fast text-only path ──────────────────────────────────

@router.post(
    "/predict/text",
    response_model=FullTriageResponse,
    summary="Text-only triage — fastest path, no file uploads",
)
async def predict_text_only(
    payload: TextInputRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Text-only triage using XGBoost + LLM fallback.
    Identical to /predict with no audio or image files.
    Uses JSON body instead of multipart/form-data — easier for API clients.
    """
    session_id = uuid.uuid4()
    
    try:
        extracted, unmatched, symptom_vector = await extract_symptoms(
            text=payload.text,
            language=payload.language,
            redis=redis,
        )

        from app.services.diagnosis.classifier import run_classifier
        nlp_result = await run_classifier(symptom_vector)

        diagnosis = await fuse_signals(
            nlp_result=nlp_result,
            symptom_count=sum(symptom_vector.values()),
            extracted_symptoms=extracted.symptoms,
            extracted_keywords=extracted.raw_keywords,
            self_severity=payload.self_severity,
            language=payload.language or "en",
        )

        triage = await compute_triage(
            diagnosis=diagnosis,
            self_severity=payload.self_severity,
            patient_id=payload.patient_id,
            db=db,
        )

        now = datetime.now(timezone.utc)
        session = TriageSession(
            id=session_id,
            patient_id=payload.patient_id,
            input_language=payload.language or "en",
            raw_text=payload.text,
            extracted_keywords=extracted.raw_keywords,
            symptom_vector=symptom_vector,
            duration_text=extracted.duration,
            self_severity=payload.self_severity,
            primary_diagnosis=diagnosis.primary_diagnosis,
            differential_diagnosis=diagnosis.differential,
            model_confidence=diagnosis.confidence,
            diagnosis_source=diagnosis.diagnosis_source,
            red_flags=diagnosis.red_flags,
            triage_level=triage.level,
            triage_label=triage.label,
            completed_at=now,
        )
        db.add(session)
        await db.flush()

        return FullTriageResponse(
            session_id=session_id,
            input_language=payload.language or "en",
            extracted=extracted,
            diagnosis=diagnosis,
            triage=triage,
            created_at=now,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("vaidya.predict_text.error", error=str(exc), exc_info=True)
        raise HTTPException(500, "Internal server error during diagnosis")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("vaidya.predict_text.error", error=str(exc), exc_info=True)
        raise HTTPException(500, "Internal server error during diagnosis")


# ── POST /audio — standalone audio diagnosis ──────────────────────────────────

@router.post("/audio", summary="Standalone respiratory audio diagnosis")
async def diagnose_audio(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    """
    Run the audio ensemble model (XGBoost + RandomForest from audio.ipynb).
    Returns 3-class prediction: cough_severe | cough_healthy | other.

    Use /predict with audio_file for fused diagnosis.
    Use this endpoint for standalone audio quality checking or debugging.
    """
    if file.content_type not in ALLOWED_AUDIO_MIME:
        raise HTTPException(415, f"Unsupported audio format: {file.content_type}")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty audio file")

    tmp = _write_tmp(content, ".wav")
    try:
        return await run_audio_model(tmp)
    finally:
        _cleanup(tmp)


# ── POST /image — standalone image diagnosis ──────────────────────────────────

@router.post("/image", summary="Standalone image diagnosis (X-ray / wound / skin)")
async def diagnose_image(
    file: UploadFile = File(...),
    task_type: Optional[str] = Form(None, pattern="^(chest|skin|wound)$"),
    session_id: Optional[str] = Form(None),
):
    """
    Run the hybrid vision model (EfficientNet-B3 + ResNet-50 from Computer_Vision notebook).
    Specify task_type to select the correct classification head:
      chest → bacterial/viral pneumonia vs normal
      skin  → skin disease classification
      wound → wound type classification
    Auto-detected from filename if not specified.

    Use /predict with image_file for fused diagnosis.
    """
    if file.content_type not in ALLOWED_IMAGE_MIME:
        raise HTTPException(415, f"Unsupported image format: {file.content_type}")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty image file")

    suffix = ".jpg" if "jpeg" in (file.content_type or "") else ".png"
    tmp = _write_tmp(content, suffix)
    try:
        return await run_vision_model(tmp, dataset_type=task_type)
    finally:
        _cleanup(tmp)


# ── GET /explain/{session_id} — fusion explainability ────────────────────────

@router.get(
    "/explain/{session_id}",
    summary="Explain fusion decision for a past session",
)
async def explain_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return a human-readable explanation of how Vaidya reached its diagnosis
    for a given session. Shows which modalities contributed and how.
    """
    from sqlalchemy import select

    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(400, "Invalid session ID format")

    result = await db.execute(
        select(TriageSession).where(TriageSession.id == sid)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    source = session.diagnosis_source or "unknown"
    modalities = {
        "xgboost":     "Symptom text analysis",
        "fusion":      "Symptom text + audio/image analysis",
        "llm_fallback": "Open-ended AI reasoning (low symptom confidence)",
        "llm_gemini":  "Gemini AI reasoning (low XGBoost confidence)",
    }.get(source, source)

    return {
        "session_id":         str(session.id),
        "created_at":         session.completed_at.isoformat() if session.completed_at else None,
        "primary_diagnosis":  session.primary_diagnosis,
        "confidence":         session.model_confidence,
        "diagnosis_source":   source,
        "modalities_used":    modalities,
        "symptoms_matched":   len(session.extracted_keywords or []),
        "triage_level":       session.triage_level,
        "red_flags":          session.red_flags or [],
        "disclaimer":         (
            "This AI diagnosis is for triage guidance only. "
            "It is NOT a medical prescription. Always consult a licensed doctor."
        ),
    }
