"""
Vaidya — /api/v1/input

POST /text   — symptom text in EN/HI/TA
POST /voice  — audio file → Whisper STT → transcript + language
"""

import hashlib
import os
import tempfile
from typing import Optional

import structlog
from fastapi import (
    APIRouter, Depends, File, Form, HTTPException,
    UploadFile,
)

from app.core.redis import get_redis
from app.schemas.schemas import TextInputRequest, VoiceInputResponse
from app.services.nlp.language_detector import detect_language, is_supported_language
from app.services.nlp.transcriber import transcribe_audio
from app.services.nlp.translator import translate_to_english
from app.services.nlp.audio_preprocessor import preprocess_audio

router = APIRouter()
logger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
ALLOWED_AUDIO_MIME = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/ogg",           # WhatsApp voice messages
    "audio/mpeg",          # mp3
    "audio/mp3",
    "audio/webm",          # browser MediaRecorder (Chrome/Firefox)
    "audio/mp4",           # m4a / iOS recordings
    "audio/x-m4a",
    "audio/flac",
    "application/octet-stream",   # some mobile apps don't set mime correctly
}
ALLOWED_EXTENSIONS = {".wav", ".ogg", ".mp3", ".webm", ".m4a", ".flac"}
MAX_AUDIO_BYTES    = 15 * 1024 * 1024   # 15 MB (rural recordings can be large)
MAX_TEXT_LENGTH    = 2000


# ── Helper ─────────────────────────────────────────────────────────────────────

def _get_extension(filename: str | None, content_type: str | None) -> str:
    """Determine file extension from filename or MIME type."""
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            return ext
    mime_to_ext = {
        "audio/ogg":  ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp3":  ".mp3",
        "audio/webm": ".webm",
        "audio/mp4":  ".m4a",
        "audio/x-m4a":".m4a",
        "audio/flac": ".flac",
        "audio/wav":  ".wav",
        "audio/wave": ".wav",
    }
    return mime_to_ext.get(content_type or "", ".wav")


# ── POST /text ─────────────────────────────────────────────────────────────────

@router.post(
    "/text",
    summary="Submit symptom text (EN / HI / TA)",
    response_description="Language detection + normalised text + cache key",
)
async def submit_text(
    payload: TextInputRequest,
    redis=Depends(get_redis),
):
    """
    Accepts raw symptom descriptions in English, Hindi, or Tamil.

    - Auto-detects language via Unicode script analysis + langdetect
    - Translates to English if Hindi or Tamil (for downstream NLP)
    - Caches normalised text for 10 minutes (same text = same extraction result)
    - Returns cache_key to pass to /nlp/extract to skip re-processing

    Example payloads:
      EN: {"text": "I have had fever and cough for 3 days"}
      HI: {"text": "मुझे 3 दिन से बुखार और खांसी है"}
      TA: {"text": "எனக்கு 3 நாட்களாக காய்ச்சல் மற்றும் இருமல் உள்ளது"}
    """
    text = payload.text

    # Language detection
    language = payload.language or await detect_language(text)
    if not is_supported_language(language):
        language = "en"   # graceful fallback

    # Translate if needed (for NLP extraction which is English-only)
    translation_result = await translate_to_english(text, language)
    english_text    = translation_result["translated"]
    translate_method = translation_result["method"]

    logger.info(
        "vaidya.input.text",
        language=language,
        length=len(text),
        translation_method=translate_method,
        patient_id=str(payload.patient_id) if payload.patient_id else None,
    )

    # Cache key: SHA-256 of normalised English text
    # Downstream /nlp/extract uses this to skip re-inference on same text
    cache_key = f"input:{hashlib.sha256(english_text.lower().strip().encode()).hexdigest()[:20]}"
    await redis.setex(cache_key, 600, english_text)   # 10 min TTL

    return {
        "status":           "accepted",
        "original_language": language,
        "original_text":    text,
        "english_text":     english_text,
        "translation_method": translate_method,
        "text_length":      len(text),
        "cache_key":        cache_key,
    }


# ── POST /voice ────────────────────────────────────────────────────────────────

@router.post(
    "/voice",
    response_model=VoiceInputResponse,
    summary="Submit voice recording — Whisper STT → transcript",
)
async def submit_voice(
    file: UploadFile = File(
        ...,
        description="Audio file: wav / ogg (WhatsApp) / webm (browser) / mp3 / m4a",
    ),
    language_hint: Optional[str] = Form(
        None,
        pattern="^(en|hi|ta)$",
        description="Optional: tell Whisper which language to expect (faster)",
    ),
    translate: bool = Form(
        True,
        description="Also return English translation of Hindi/Tamil transcript",
    ),
    denoise: bool = Form(
        True,
        description="Apply noise reduction (recommended for phone recordings)",
    ),
    redis=Depends(get_redis),
):
    """
    Full voice-to-text pipeline for rural patients:

    1. Validate audio format + size
    2. Preprocess: convert to 16kHz WAV + noise reduction
    3. Quality check: reject silence / too-short clips
    4. Whisper tiny STT: transcript + language detection
    5. If Hindi/Tamil: translate to English for NLP downstream
    6. Cache transcript for 10 minutes

    Supported formats: wav, ogg (WhatsApp voice), webm (browser),
                       mp3, m4a (iPhone), flac

    Language hint speeds up Whisper by skipping its internal language
    detection step — use it when the patient's language is already known
    from the language selector in the app.
    """
    # ── Validate MIME type ───────────────────────────────────────────────────
    if (
        file.content_type not in ALLOWED_AUDIO_MIME
        and _get_extension(file.filename, file.content_type) not in ALLOWED_EXTENSIONS
    ):
        raise HTTPException(
            status_code=415,
            detail={
                "error":     "unsupported_format",
                "message":   f"Unsupported audio format: {file.content_type}",
                "supported": ["wav", "ogg", "mp3", "webm", "m4a", "flac"],
            },
        )

    # ── Read + size check ────────────────────────────────────────────────────
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail={"error": "empty_file", "message": "Audio file is empty"})

    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "error":   "file_too_large",
                "message": f"Audio file too large ({len(content) // (1024*1024)}MB). Maximum: {MAX_AUDIO_BYTES // (1024*1024)}MB",
            },
        )

    logger.info(
        "vaidya.input.voice.received",
        filename=file.filename,
        content_type=file.content_type,
        size_kb=round(len(content) / 1024, 1),
        language_hint=language_hint,
    )

    # ── Write to temp file ───────────────────────────────────────────────────
    ext = _get_extension(file.filename, file.content_type)
    tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp_path = tmp_file.name
    tmp_file.write(content)
    tmp_file.close()

    cleanup_paths = [tmp_path]

    try:
        # ── Preprocess (format convert + noise reduction + QC) ───────────────
        pre = preprocess_audio(tmp_path, denoise=denoise)

        if pre["processed_path"] != tmp_path:
            cleanup_paths.append(pre["processed_path"])

        if not pre["ok"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "error":   "audio_quality",
                    "message": pre["reason"],
                },
            )

        processed_path = pre["processed_path"]
        quality_meta   = pre.get("quality", {})

        # ── Whisper STT ──────────────────────────────────────────────────────
        stt_result = await transcribe_audio(
            file_path=processed_path,
            language_hint=language_hint,
        )

        if stt_result.get("error") and not stt_result.get("text"):
            raise HTTPException(
                status_code=503,
                detail={
                    "error":   "stt_failed",
                    "message": "Speech recognition failed. Please try speaking more clearly.",
                },
            )

        transcript    = stt_result["text"]
        detected_lang = stt_result["language"]
        confidence    = stt_result["confidence"]

        # ── Translate if needed ──────────────────────────────────────────────
        english_transcript   = transcript
        translation_method   = "passthrough"

        if translate and detected_lang != "en" and transcript:
            tr = await translate_to_english(transcript, detected_lang)
            english_transcript = tr["translated"]
            translation_method = tr["method"]

        # ── Cache transcript ─────────────────────────────────────────────────
        if transcript:
            cache_key = f"voice:{hashlib.sha256(transcript.encode()).hexdigest()[:20]}"
            await redis.setex(cache_key, 600, english_transcript)
        else:
            cache_key = None

        logger.info(
            "vaidya.input.voice.done",
            language=detected_lang,
            transcript_len=len(transcript),
            confidence=round(confidence, 3),
            translation_method=translation_method,
            duration_s=quality_meta.get("duration_s"),
        )

        return VoiceInputResponse(
            transcript=transcript,
            detected_language=detected_lang,
            confidence=round(confidence, 3),
            english_transcript=english_transcript if detected_lang != "en" else None,
            translation_method=translation_method if detected_lang != "en" else None,
        )

    finally:
        # Always clean up temp files
        for path in cleanup_paths:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except Exception:
                pass

