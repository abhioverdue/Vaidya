"""
Vaidya — Whisper STT transcription service

Model: faster-whisper tiny (CTranslate2 int8) — ~1-3s on single CPU core
       Replaces HuggingFace transformers pipeline (~8-15s on same hardware).
       4-5x faster because CTranslate2 uses fused GEMM ops + int8 quantisation
       without requiring PyTorch for inference.
"""

import asyncio
import os
from functools import lru_cache
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

LANG_TO_WHISPER = {"en": "en", "hi": "hi", "ta": "ta"}
WHISPER_TO_VAIDYA = {
    "en": "en", "hi": "hi", "ta": "ta",
    "kn": "ta",   # Kannada misdetected as Tamil
    "ml": "ta",   # Malayalam edge case
    "ur": "hi",   # Urdu/Hindi edge case
}
HALLUCINATIONS = frozenset({
    "thank you", "thanks for watching", "subscribe",
    "you", "[music]", "[applause]", "...",
})


@lru_cache(maxsize=1)
def _load_whisper():
    """Load faster-whisper model once per process. int8 keeps RAM ~80MB."""
    try:
        from faster_whisper import WhisperModel
        from app.core.config import settings
        model_id = settings.WHISPER_MODEL
        logger.info("vaidya.whisper.loading", model=model_id, backend="faster-whisper/ctranslate2")
        model = WhisperModel(model_id, device="cpu", compute_type="int8")
        logger.info("vaidya.whisper.ready", model=model_id)
        return model
    except Exception as exc:
        logger.error("vaidya.whisper.load_failed", error=str(exc))
        return None


def _normalise_audio(input_path: str) -> str:
    """Convert any audio format to 16kHz mono WAV. Returns same path if already WAV."""
    suffix = Path(input_path).suffix.lower()
    if suffix == ".wav":
        return input_path
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        out_path = str(Path(input_path).with_suffix("")) + "_norm.wav"
        audio.export(out_path, format="wav")
        logger.debug("vaidya.whisper.normalised", from_fmt=suffix)
        return out_path
    except ImportError:
        logger.warning("vaidya.whisper.pydub_missing — skipping normalisation")
        return input_path
    except Exception as exc:
        logger.warning("vaidya.whisper.normalise_failed", error=str(exc))
        return input_path


def _run_whisper_sync(audio_path: str, language_hint: str | None) -> dict:
    """
    Blocking faster-whisper inference — called from run_in_executor.
    beam_size=1 (greedy) is fastest and sufficient for short medical phrases.
    vad_filter skips silent segments, reducing hallucinations on noisy uploads.
    """
    model = _load_whisper()
    if model is None:
        return {"text": "", "language": language_hint or "en", "confidence": 0.0,
                "error": "Whisper model not loaded"}

    norm_path = _normalise_audio(audio_path)

    try:
        lang = LANG_TO_WHISPER.get(language_hint or "", None)
        segments_gen, info = model.transcribe(
            norm_path,
            language=lang,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )

        chunks = []
        text_parts = []
        total_logprob = 0.0
        for seg in segments_gen:
            text_parts.append(seg.text)
            chunks.append({"text": seg.text, "timestamp": (seg.start, seg.end)})
            total_logprob += seg.avg_logprob

        text = " ".join(text_parts).strip()
        detected = language_hint if language_hint else WHISPER_TO_VAIDYA.get(info.language, "en")
        avg_logprob = total_logprob / len(chunks) if chunks else -1.0

        if text.lower().strip() in HALLUCINATIONS:
            logger.info("vaidya.whisper.hallucination_filtered", text=text)
            return {"text": "", "language": detected, "confidence": 0.0, "chunks": [],
                    "error": "hallucination_filtered"}

        confidence = _estimate_confidence(text, chunks, avg_logprob)

        logger.info(
            "vaidya.whisper.transcribed",
            language=detected,
            text_len=len(text),
            confidence=round(confidence, 3),
            chunks=len(chunks),
        )
        return {"text": text, "language": detected, "confidence": confidence, "chunks": chunks}

    except Exception as exc:
        logger.error("vaidya.whisper.inference_error", error=str(exc))
        return {"text": "", "language": language_hint or "en", "confidence": 0.0, "error": str(exc)}

    finally:
        if norm_path != audio_path and os.path.exists(norm_path):
            os.unlink(norm_path)


def _estimate_confidence(text: str, chunks: list, avg_logprob: float = -1.0) -> float:
    if not text:
        return 0.0
    if text.lower().strip() in HALLUCINATIONS:
        return 0.1
    if len(text) < 10:
        return 0.4
    # avg_logprob from faster-whisper: 0.0 = perfect, -1.0 = decent, -2.0+ = poor
    # Map to [0, 1]: clamp logprob to [-2, 0] then normalise
    logprob_conf = max(0.0, min(1.0, 1.0 + avg_logprob / 2.0))
    return round(logprob_conf, 3)


async def transcribe_audio(file_path: str, language_hint: str | None = None) -> dict:
    """
    Async wrapper — runs blocking Whisper inference in thread pool.

    Returns:
        {"text": str, "language": "en"|"hi"|"ta", "confidence": float, "chunks": list}
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_whisper_sync, file_path, language_hint)
