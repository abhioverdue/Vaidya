"""
Vaidya — language detection service
Supports: English (en), Hindi (hi), Tamil (ta)

Strategy (fastest to most accurate):
  1. Script detection  — Devanagari script = Hindi,  Tamil script = Tamil (instant, 100% accurate)
  2. langdetect        — probabilistic, trained on Wikipedia (fast, good for mixed scripts)
  3. Fallback to "en"  — when detection fails or language unsupported

Why script detection first:
  Hindi is written in Devanagari (Unicode range U+0900–U+097F).
  Tamil is written in Tamil script (Unicode range U+0B80–U+0BFF).
  Any sentence with even one character from these ranges is unambiguously that language.
  This catches the common rural case: a mix of native script + some English words.
"""

import unicodedata

import structlog

logger = structlog.get_logger(__name__)

# Unicode ranges for script detection
DEVANAGARI_RANGE = (0x0900, 0x097F)   # Hindi, Marathi, Sanskrit
TAMIL_RANGE      = (0x0B80, 0x0BFF)   # Tamil


def _has_script(text: str, start: int, end: int) -> bool:
    """Return True if text contains at least one character in the given Unicode range."""
    return any(start <= ord(c) <= end for c in text)


def _script_detect(text: str) -> str | None:
    """
    Instant script-based language detection.
    Returns language code or None if script detection is inconclusive.
    """
    if _has_script(text, *DEVANAGARI_RANGE):
        return "hi"
    if _has_script(text, *TAMIL_RANGE):
        return "ta"
    return None


def _langdetect_detect(text: str) -> str | None:
    """
    Probabilistic language detection via langdetect.
    Returns our language code or None if unsupported language detected.
    """
    try:
        from langdetect import detect, DetectorFactory
        # Seed for reproducibility — langdetect is non-deterministic by default
        DetectorFactory.seed = 42
        lang = detect(text)
        # Map to our supported set
        mapping = {
            "en": "en",
            "hi": "hi",
            "ta": "ta",
            "mr": "hi",   # Marathi → Hindi (same script, similar grammar)
            "ur": "hi",   # Urdu → Hindi (overlapping vocabulary)
            "kn": "ta",   # Kannada → Tamil (user might have mixed)
            "ml": "ta",   # Malayalam → Tamil (same region)
        }
        return mapping.get(lang)
    except Exception as exc:
        logger.debug("vaidya.lang_detect.langdetect_failed", error=str(exc))
        return None


async def detect_language(text: str) -> str:
    """
    Detect language of symptom text. Returns "en" | "hi" | "ta".

    Pipeline:
      1. Script detection (instant, Unicode ranges)
      2. langdetect probabilistic model
      3. Fallback to "en"

    Args:
        text: raw input text from patient

    Returns:
        ISO 639-1 language code: "en", "hi", or "ta"
    """
    if not text or not text.strip():
        return "en"

    # Step 1: Script detection — fastest path
    script_result = _script_detect(text)
    if script_result:
        logger.debug("vaidya.lang_detect.script", lang=script_result)
        return script_result

    # Step 2: Statistical detection
    stat_result = _langdetect_detect(text)
    if stat_result:
        logger.debug("vaidya.lang_detect.statistical", lang=stat_result)
        return stat_result

    # Step 3: Default to English (most symptom databases are in English)
    logger.debug("vaidya.lang_detect.fallback_en")
    return "en"


def is_supported_language(lang: str) -> bool:
    return lang in ("en", "hi", "ta")
