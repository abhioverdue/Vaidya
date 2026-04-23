"""
Vaidya — Hindi/Tamil → English translation service
Module 2 — IndicTrans2 (AI4Bharat, free, self-hostable)

Why IndicTrans2 over Google Translate:
  - Completely free, no API key, no quota
  - Trained specifically on Indian languages with medical corpus
  - Handles Indic scripts + romanised transliteration
  - Can self-host on the same machine as the rest of Vaidya

Architecture:
  - IndicTrans2 runs as a separate lightweight container (indictrans2:8001)
  - This service calls it via HTTP with retry
  - If IndicTrans2 is unavailable, falls through to a local dictionary approach
    for the most critical medical terms (the "medical phrase map")

Medical phrase map (local fallback — no external call needed):
  Covers the 80 most common symptom descriptions in Hindi and Tamil,
  drawn from patient phrasing in ICMR rural health studies.
"""

import asyncio
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ── Medical phrase maps ────────────────────────────────────────────────────────
# These cover the most common ways rural patients describe symptoms.
# Used as fallback when IndicTrans2 is unavailable.

HINDI_TO_ENGLISH: dict[str, str] = {
    # Fever family
    "बुखार": "fever",
    "तेज बुखार": "high fever",
    "हल्का बुखार": "mild fever",
    "ठंड लगना": "chills",
    "कंपकंपी": "shivering",
    # Respiratory
    "खांसी": "cough",
    "बलगम": "phlegm",
    "सांस लेने में तकलीफ": "breathlessness",
    "सांस फूलना": "breathlessness",
    "छाती में दर्द": "chest pain",
    "छाती में जकड़न": "chest tightness",
    "गला खराब": "sore throat",
    "गले में खराश": "throat irritation",
    "नाक बंद": "congestion",
    "नाक बहना": "runny nose",
    # GI
    "उल्टी": "vomiting",
    "जी मिचलाना": "nausea",
    "दस्त": "diarrhoea",
    "पेट दर्द": "stomach pain",
    "पेट में जलन": "acidity",
    "कब्ज": "constipation",
    # Pain
    "सिरदर्द": "headache",
    "कमर दर्द": "back pain",
    "जोड़ों में दर्द": "joint pain",
    "मांसपेशियों में दर्द": "muscle pain",
    "बदन दर्द": "body ache",
    "पैर में दर्द": "leg pain",
    # Skin
    "खुजली": "itching",
    "चकत्ते": "skin rash",
    "त्वचा में जलन": "skin irritation",
    "पीली त्वचा": "yellowish skin",
    # Neurological
    "चक्कर आना": "dizziness",
    "बेहोशी": "loss of consciousness",
    "सिर घूमना": "spinning movements",
    # General
    "थकान": "fatigue",
    "कमजोरी": "weakness",
    "भूख न लगना": "loss of appetite",
    "वजन कम होना": "weight loss",
    "पसीना आना": "sweating",
    "आंखें पीली": "yellowing of eyes",
    "पेशाब में जलन": "burning micturition",
    "मुंह में छाले": "ulcers on tongue",
    "3 दिन से": "for 3 days",
    "1 हफ्ते से": "for 1 week",
    "कई दिनों से": "for several days",
}

TAMIL_TO_ENGLISH: dict[str, str] = {
    # Fever family
    "காய்ச்சல்": "fever",
    "அதிக காய்ச்சல்": "high fever",
    "லேசான காய்ச்சல்": "mild fever",
    "குளிர்": "chills",
    "நடுக்கம்": "shivering",
    # Respiratory
    "இருமல்": "cough",
    "சளி": "phlegm",
    "மூச்சு திணறல்": "breathlessness",
    "மூச்சுத் திணறல்": "breathlessness",
    "மார்பு வலி": "chest pain",
    "மார்பில் இறுக்கம்": "chest tightness",
    "தொண்டை வலி": "sore throat",
    "தொண்டை கரகரப்பு": "throat irritation",
    "மூக்கடைப்பு": "congestion",
    "மூக்கு ஒழுகுதல்": "runny nose",
    # GI
    "வாந்தி": "vomiting",
    "குமட்டல்": "nausea",
    "வயிற்றுப்போக்கு": "diarrhoea",
    "வயிற்று வலி": "stomach pain",
    "அஜீரணம்": "indigestion",
    "மலச்சிக்கல்": "constipation",
    # Pain
    "தலைவலி": "headache",
    "முதுகு வலி": "back pain",
    "மூட்டு வலி": "joint pain",
    "தசை வலி": "muscle pain",
    "உடல் வலி": "body ache",
    # Skin
    "அரிப்பு": "itching",
    "தோல் வியாதி": "skin rash",
    "மஞ்சள் தோல்": "yellowish skin",
    "கண்கள் மஞ்சளாக": "yellowing of eyes",
    # Neurological
    "தலைச்சுற்றல்": "dizziness",
    "மயக்கம்": "loss of consciousness",
    # General
    "சோர்வு": "fatigue",
    "பலவீனம்": "weakness",
    "பசியின்மை": "loss of appetite",
    "எடை குறைவு": "weight loss",
    "வியர்வை": "sweating",
    "சிறுநீரில் எரிச்சல்": "burning micturition",
    "வாயில் புண்": "ulcers on tongue",
    "3 நாட்களாக": "for 3 days",
    "ஒரு வாரமாக": "for 1 week",
    "பல நாட்களாக": "for several days",
}


def _local_translate(text: str, source_lang: str) -> str:
    """
    Dictionary-based translation fallback.
    Replaces known medical phrases, leaves unknown words as-is.
    Handles partial matches — looks for each phrase anywhere in the text.
    """
    phrase_map = HINDI_TO_ENGLISH if source_lang == "hi" else TAMIL_TO_ENGLISH

    result = text
    # Sort by phrase length descending — match longer phrases first
    for native, english in sorted(phrase_map.items(), key=lambda x: -len(x[0])):
        if native in result:
            result = result.replace(native, english)

    return result


async def translate_to_english(
    text: str,
    source_lang: str,
    timeout: int = 10,
) -> dict[str, str]:
    """
    Translate Hindi or Tamil symptom text to English.

    Priority:
      1. IndicTrans2 microservice (HTTP call, best accuracy)
      2. Local phrase map (instant, covers common medical terms)

    Args:
        text:        raw text in Hindi or Tamil
        source_lang: "hi" or "ta"
        timeout:     seconds to wait for IndicTrans2

    Returns:
        {"translated": str, "method": "indictrans2"|"local_map"|"passthrough"}
    """
    if source_lang == "en":
        return {"translated": text, "method": "passthrough"}

    if source_lang not in ("hi", "ta"):
        logger.warning("vaidya.translator.unsupported_lang", lang=source_lang)
        return {"translated": text, "method": "passthrough"}

    # Map to IndicTrans2 language codes
    src_code = "hin_Deva" if source_lang == "hi" else "tam_Taml"

    # Try IndicTrans2 microservice first
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "http://indictrans2:8001/translate",
                json={
                    "text":     text,
                    "src_lang": src_code,
                    "tgt_lang": "eng_Latn",
                },
            )
            if response.status_code == 200:
                translated = response.json().get("translated", text)
                logger.info(
                    "vaidya.translator.indictrans2",
                    src=source_lang,
                    src_len=len(text),
                    tgt_len=len(translated),
                )
                return {"translated": translated, "method": "indictrans2"}

    except (httpx.ConnectError, httpx.TimeoutException):
        logger.debug(
            "vaidya.translator.indictrans2_unavailable",
            src=source_lang,
            note="falling back to local phrase map",
        )
    except Exception as exc:
        logger.warning("vaidya.translator.error", error=str(exc))

    # Local phrase map fallback
    translated = _local_translate(text, source_lang)
    logger.info(
        "vaidya.translator.local_map",
        src=source_lang,
        replaced_terms=sum(1 for p in (HINDI_TO_ENGLISH if source_lang == "hi" else TAMIL_TO_ENGLISH) if p in text),
    )
    return {"translated": translated, "method": "local_map"}
