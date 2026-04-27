"""
Vaidya — /api/v1/diagnose

POST /predict       — full multimodal triage: text + optional audio + optional image
POST /predict/text  — text-only fast path (no file uploads)
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
from app.services.diagnosis.fusion import fuse_signals, run_all_models_concurrent
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

        # ── Stage 3b: Gemini Vision validation + enrichment ──────────────────
        if image_tmp and vision_result and not vision_result.get("error"):
            try:
                from app.services.diagnosis.llm_fallback import (
                    enrich_vision_with_gemini, validate_vision_with_gemini,
                )

                # Validation: only when CNN confidence is low (<60%) — high-confidence
                # CNN predictions are trusted; low-confidence ones get a Gemini sanity check.
                top_pred = vision_result.get("top_prediction", {})
                cnn_conf = top_pred.get("confidence", 1.0) if isinstance(top_pred, dict) else 1.0

                if cnn_conf < 0.60:
                    vision_validation = await validate_vision_with_gemini(
                        image_path=image_tmp,
                        cnn_result=vision_result,
                        symptoms=extracted.symptoms,
                        language=language or "en",
                    )
                    if vision_validation and not vision_validation.get("agrees"):
                        alt_label = vision_validation.get("alternative")
                        if alt_label:
                            # Override the CNN label — fusion will use corrected label
                            # for VISION_CORROBORATION scoring.
                            vision_result = dict(vision_result)
                            vision_result["top_prediction"] = {
                                **top_pred,
                                "label":      alt_label,
                                "confidence": cnn_conf,  # keep original conf; label corrected
                                "gemini_override": True,
                            }
                            log.info(
                                "vaidya.diagnose.vision_gemini_override",
                                original=top_pred.get("label"), corrected=alt_label,
                                cnn_conf=round(cnn_conf, 3),
                                reasoning=vision_validation.get("reasoning", ""),
                            )

                # Enrichment: plain-language description (always runs when Gemini available)
                gemini_vision_desc = await enrich_vision_with_gemini(
                    image_path=image_tmp,
                    cnn_result=vision_result,
                    symptoms=extracted.symptoms,
                    language=language or "en",
                )
                if gemini_vision_desc:
                    vision_result = dict(vision_result)
                    vision_result["gemini_description"] = gemini_vision_desc
                    log.info("vaidya.diagnose.gemini_vision_ok", desc_len=len(gemini_vision_desc))
            except Exception as exc:
                log.warning("vaidya.diagnose.gemini_vision_failed", error=str(exc))

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
        pid = None
        if patient_id:
            try:
                pid = uuid.UUID(patient_id)
            except ValueError:
                raise HTTPException(400, "patient_id must be a valid UUID")
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
        try:
            db.add(session)
            await db.flush()
        except Exception as exc:
            log.error("vaidya.diagnose.session_persist_failed", error=str(exc))
            await db.rollback()

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

    extracted, unmatched, symptom_vector = await extract_symptoms(
        text=payload.text,
        language=payload.language,
        redis=redis,
    )

    from app.services.diagnosis.classifier import run_classifier
    nlp_result = await run_classifier(symptom_vector)

    diagnosis, fusion_weights = await fuse_signals(
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
    try:
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
    except Exception as exc:
        logger.error("vaidya.diagnose.session_persist_failed", error=str(exc))
        await db.rollback()

    return FullTriageResponse(
        session_id=session_id,
        input_language=payload.language or "en",
        extracted=extracted,
        diagnosis=diagnosis,
        triage=triage,
        audio_result=None,
        vision_result=None,
        fusion_weights=fusion_weights,
        created_at=now,
    )


# ── POST /audio — cough detection only ───────────────────────────────────────

@router.post("/audio", summary="Cough detection — audio file only, no full triage")
async def predict_audio_only(
    audio_file: UploadFile = File(..., description="Respiratory audio (wav/ogg/mp3)"),
):
    """
    Lightweight endpoint: accepts an audio file, runs the cough classification
    model, and returns the result immediately. No symptom extraction, no DB write.
    Used by the frontend to show a real-time 'Cough Detected' popup after recording.
    """
    from app.services.diagnosis.audio_model import run_audio_model

    content = await audio_file.read()
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio file too large (max 15MB)")

    audio_tmp = _write_tmp(content, ".wav")
    try:
        result = await run_audio_model(audio_tmp)
    finally:
        _cleanup(audio_tmp)

    if "error" in result:
        raise HTTPException(503, result["error"])

    top    = result.get("top_prediction", {})
    label  = top.get("label", "other")
    conf   = top.get("confidence", 0.0)

    severity: str | None = None
    if label == "cough_severe":
        severity = "severe"
    elif label == "cough_healthy":
        severity = "mild"

    return {
        "detected":   label != "other",
        "label":      label,
        "confidence": round(conf, 4),
        "severity":   severity,
    }

