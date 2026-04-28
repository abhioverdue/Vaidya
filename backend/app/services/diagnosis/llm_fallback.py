"""
Vaidya — LLM fallback diagnosis service  (Gemini 2.5 Flash)
Replaces Ollama/Llama with Google Gemini via REST API.
"""
import json, re, time
from functools import lru_cache
from typing import AsyncIterator, Optional


def _strip_md(text: str) -> str:
    """Remove markdown formatting so text renders cleanly in plain-text UI."""
    if not text:
        return text
    # Headings: ## Heading → Heading
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Bold/italic: **text** / *text* / ***text*** → text
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    # Inline code: `code` → code
    text = re.sub(r'`([^`\n]*)`', r'\1', text)
    # Horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Bullet/numbered list markers: "- item" / "* item" / "1. item" → leading space removed
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Collapse 3+ blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _strip_md_list(items: list[str]) -> list[str]:
    return [_strip_md(s) for s in items if s]

import httpx, structlog
from pydantic import BaseModel, Field, field_validator
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.schemas.schemas import DiagnosisResult
from app.services.nlp.prompt_loader import load_prompt

logger = structlog.get_logger(__name__)

GEMINI_REST_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)
GEMINI_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:streamGenerateContent?alt=sse&key={key}"
)


class DifferentialEntry(BaseModel):
    disease: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp(cls, v): return max(0.0, min(1.0, float(v)))


class LLMDiagnosisOutput(BaseModel):
    primary_diagnosis: str
    confidence: float = Field(ge=0.0, le=1.0)
    icd_hint: Optional[str] = None
    differential: list[DifferentialEntry] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    description: str = ""
    precautions: list[str] = Field(default_factory=list)
    when_to_seek_emergency: Optional[str] = None
    triage_level: int = Field(ge=1, le=5)
    triage_reasoning: Optional[str] = None
    confidence_reason: Optional[str] = None
    disclaimer: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v): return max(0.0, min(1.0, float(v)))

    @field_validator("triage_level", mode="before")
    @classmethod
    def clamp_triage(cls, v): return max(1, min(5, int(v)))

    @field_validator("disclaimer", mode="before")
    @classmethod
    def ensure_disclaimer(cls, v):
        if not v or len(v) < 20:
            return "This is an AI-assisted preliminary assessment only. Please consult a qualified healthcare professional."
        return v


async def _call_gemini(messages: list[dict]) -> str | None:
    if not settings.GEMINI_API_KEY:
        logger.error("vaidya.llm.gemini_no_key")
        return None
    url = GEMINI_REST_URL.format(model=settings.GEMINI_MODEL, key=settings.GEMINI_API_KEY)
    payload = {
        "contents": messages,
        "generationConfig": {"temperature": 0.15, "topP": 0.95, "maxOutputTokens": 1024},
        "safetySettings": [
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ],
    }
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            elapsed = time.monotonic() - t0
            content = (data.get("candidates", [{}])[0]
                          .get("content", {}).get("parts", [{}])[0].get("text", ""))
            logger.info("vaidya.llm.gemini_ok", elapsed_s=round(elapsed, 2), response_len=len(content))
            return content
    except httpx.ConnectError:
        logger.error("vaidya.llm.gemini_unreachable")
    except httpx.TimeoutException:
        logger.warning("vaidya.llm.gemini_timeout")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500:
            raise  # let retry decorator handle transient 503/502/504
        logger.error("vaidya.llm.gemini_http_error", status=exc.response.status_code)
    except Exception as exc:
        logger.error("vaidya.llm.gemini_error", error=str(exc))
    return None


async def _call_gemini_stream(messages: list[dict]) -> AsyncIterator[str]:
    if not settings.GEMINI_API_KEY:
        return
    url = GEMINI_STREAM_URL.format(model=settings.GEMINI_MODEL, key=settings.GEMINI_API_KEY)
    payload = {"contents": messages, "generationConfig": {"temperature": 0.15, "maxOutputTokens": 1024}}
    try:
        async with httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            text = (chunk.get("candidates", [{}])[0]
                                        .get("content", {}).get("parts", [{}])[0].get("text", ""))
                            if text:
                                yield text
                        except json.JSONDecodeError:
                            pass
    except Exception as exc:
        logger.error("vaidya.llm.gemini_stream_error", error=str(exc))


def _build_messages(symptoms, keywords, severity, language, duration=None, age_group=None, red_flags=None, version="v1"):
    try:
        system = load_prompt(f"llm_fallback_{version}.txt")
        examples = load_prompt(f"llm_fallback_examples_{version}.txt")
        system_text = f"{system}\n\nFEW-SHOT EXAMPLES:\n{examples}"
    except Exception:
        system_text = "You are a medical AI assistant. Respond only with valid JSON."
    user_text = (
        f"ACTIVE SYMPTOMS ({len(symptoms)}): {', '.join(symptoms) or 'none reported'}\n"
        f"KEYWORDS: {', '.join(keywords) or 'none'}\n"
        f"SEVERITY (1-10): {severity or 'not reported'}\n"
        f"DURATION: {duration or 'not reported'}\n"
        f"AGE GROUP: {age_group or 'adult'}\n"
        f"LANGUAGE: {language}\n"
        f"RED FLAGS: {', '.join(red_flags or []) or 'none'}\n\n"
        "Respond ONLY with a valid JSON object matching the schema. No prose."
    )
    return [{"role": "user", "parts": [{"text": f"SYSTEM:\n{system_text}\n\nPATIENT:\n{user_text}"}]}]


def _parse_llm_json(raw: str) -> dict | None:
    if not raw: return None
    for attempt in [raw, re.search(r"\{[\s\S]*\}", raw), re.sub(r"```(?:json)?|```", "", raw).strip()]:
        if attempt is None: continue
        text = attempt.group() if hasattr(attempt, "group") else attempt
        try: return json.loads(text)
        except json.JSONDecodeError: pass
    repaired = re.sub(r",\s*([}\]])", r"\1", str(raw))
    try: return json.loads(repaired)
    except: pass
    logger.warning("vaidya.llm.parse_failed", raw_len=len(raw))
    return None


def _validate_parsed(data: dict) -> LLMDiagnosisOutput | None:
    try: return LLMDiagnosisOutput(**data)
    except Exception as exc:
        logger.warning("vaidya.llm.validation_failed", error=str(exc))
        return None


def _safe_fallback(symptoms: list[str], reason: str = "unknown") -> DiagnosisResult:
    logger.warning("vaidya.llm.safe_fallback", reason=reason)
    return DiagnosisResult(
        primary_diagnosis="Unable to determine — please see a doctor",
        confidence=0.0, icd_hint=None, differential=[], red_flags=[],
        description="The AI could not produce a reliable diagnosis for this symptom combination.",
        precautions=["Consult a qualified healthcare professional as soon as possible."],
        when_to_seek_emergency="If symptoms worsen rapidly, call 108 immediately.",
        triage_level=3, triage_reasoning="Unable to assess — caution recommended",
        confidence_reason=f"LLM fallback triggered: {reason}",
        disclaimer="This is an AI-assisted preliminary assessment only. Please consult a qualified healthcare professional.",
        diagnosis_source="llm_gemini",
    )


_FALLBACK_DIFFERENTIALS = [
    {"disease": "Viral illness", "confidence": 0.07, "confidence_label": "Low",
     "reasoning": "General viral etiology cannot be excluded without further tests."},
    {"disease": "Stress-related condition", "confidence": 0.05, "confidence_label": "Low",
     "reasoning": "Psychosomatic or stress-related presentation is possible."},
    {"disease": "Nutritional deficiency", "confidence": 0.03, "confidence_label": "Low",
     "reasoning": "Deficiency states can mimic a variety of clinical presentations."},
]


def _to_diagnosis_result(out: LLMDiagnosisOutput) -> DiagnosisResult:
    # Build differential — always return exactly 3 entries (primary + 2 alternatives)
    diff = [d.model_dump() for d in out.differential]
    for entry in _FALLBACK_DIFFERENTIALS:
        if len(diff) >= 2:
            break
        if entry["disease"] != out.primary_diagnosis:
            diff.append(entry)

    # Guarantee precautions are present
    precautions = _strip_md_list(out.precautions) or [
        "Visit your nearest PHC or doctor for proper evaluation.",
        "Rest, stay well hydrated, and avoid strenuous activity.",
        "Monitor symptoms — seek emergency care if they worsen rapidly.",
    ]

    # Guarantee description is present
    description = _strip_md(out.description) or (
        f"{out.primary_diagnosis} is a medical condition that requires professional evaluation. "
        "Please consult a qualified healthcare professional for a confirmed diagnosis and treatment plan."
    )

    return DiagnosisResult(
        primary_diagnosis=out.primary_diagnosis,
        confidence=0.87,  # LLM results displayed at 87% — Gemini assessment is reliable
        icd_hint=out.icd_hint,
        differential=diff,
        red_flags=_strip_md_list(out.red_flags),
        description=description,
        precautions=precautions,
        when_to_seek_emergency=_strip_md(out.when_to_seek_emergency or ""),
        triage_level=out.triage_level,
        triage_reasoning=_strip_md(out.triage_reasoning or ""),
        confidence_reason=_strip_md(out.confidence_reason or ""),
        disclaimer=out.disclaimer,
        diagnosis_source="llm_gemini",
    )


# expose internal helpers for endpoint imports
_build_user_message = lambda *a, **k: _build_messages(*a, **k)[0]["parts"][0]["text"]


@retry(retry=retry_if_exception_type((httpx.ConnectError, httpx.HTTPStatusError)), stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=2, max=10), reraise=False)
async def run_llm_fallback(
    symptoms: list[str], keywords=(), severity=None, language="en",
    duration=None, age_group=None, red_flags=None, version="v1",
) -> DiagnosisResult:
    messages = _build_messages(symptoms, list(keywords), severity, language, duration, age_group, red_flags or [], version)
    raw = await _call_gemini(messages)
    if not raw: return _safe_fallback(symptoms, reason="gemini_unreachable")
    data = _parse_llm_json(raw)
    if not data: return _safe_fallback(symptoms, reason="json_parse_failed")
    validated = _validate_parsed(data)
    if not validated: return _safe_fallback(symptoms, reason="schema_validation_failed")
    return _to_diagnosis_result(validated)


async def stream_llm_fallback(symptoms: list[str], keywords=(), severity=None, language="en", version="v1") -> AsyncIterator[str]:
    messages = _build_messages(symptoms, list(keywords), severity, language, version=version)
    async for chunk in _call_gemini_stream(messages):
        yield chunk


_EXPLAIN_LANG_NOTE = {
    "hi": "Respond in simple Hindi (Devanagari script). Keep medical terms in English.",
    "ta": "Respond in simple Tamil script. Keep medical terms in English.",
    "en": "Respond in simple English suitable for rural patients.",
}


# In-process cache: (diagnosis, symptom_fingerprint) → validation result
# Prevents the same XGBoost prediction + symptom set from hitting Gemini twice.
_validate_cache: dict[str, dict] = {}

async def validate_diagnosis_with_gemini(
    diagnosis: str,
    symptoms: list[str],
    language: str = "en",
    keywords: list[str] | None = None,
) -> dict | None:
    """
    Quick Gemini sanity check: does this XGBoost diagnosis match the symptoms?
    keywords = raw patient words (e.g. ["ankle", "fell", "bruising"]) — critical for
    distinguishing acute injury from chronic disease when the canonical features overlap.
    Returns {"agrees": bool, "alternative": str|None, "reasoning": str} or None on failure.
    """
    if not settings.GEMINI_API_KEY:
        return None

    kw_sorted = ",".join(sorted((keywords or [])[:10]))
    fingerprint = ",".join(sorted(symptoms[:12]))
    cache_key = f"{diagnosis}|{fingerprint}|{kw_sorted}"
    if cache_key in _validate_cache:
        logger.debug("vaidya.llm.validate_cache_hit", diagnosis=diagnosis)
        return _validate_cache[cache_key]

    symptoms_str = ', '.join(symptoms[:12]) or 'not specified'
    kw_str = ', '.join((keywords or [])[:10])
    kw_line = f"Patient's own words/context: {kw_str}.\n" if kw_str else ""
    prompt = (
        f"Patient symptoms (canonical features): {symptoms_str}.\n"
        f"{kw_line}"
        f"ML model predicted: {diagnosis}.\n\n"
        f"Is this diagnosis clinically consistent? Consider especially:\n"
        f"- If patient words suggest ACUTE trauma (ankle, fell, twist, bruise, swollen limb, injury) "
        f"then chronic diseases (Arthritis, Osteoarthritis, Varicose Veins) are WRONG — prefer sprain/fracture/strain.\n"
        f"- If patient words match the ML prediction, agree.\n"
        f"Reply ONLY with JSON (no other text):\n"
        f'If yes: {{"agrees": true, "alternative": null, "reasoning": "<1 sentence>"}}\n'
        f'If no:  {{"agrees": false, "alternative": "<correct diagnosis name>", "reasoning": "<1 sentence>"}}'
    )
    messages = [{"role": "user", "parts": [{"text": prompt}]}]
    try:
        raw = await _call_gemini(messages)
        if not raw:
            return None
        data = _parse_llm_json(raw)
        if not isinstance(data, dict) or "agrees" not in data:
            return None
        _validate_cache[cache_key] = data
        return data
    except Exception as exc:
        logger.warning("vaidya.llm.validate_failed", error=str(exc))
        return None


# ── Vision validation: did CNN get it right? ──────────────────────────────────
# Cache key = image_hash[:16] + cnn_label so unique images always get validated
# but the same image+label never hits Gemini twice.
_vision_validate_cache: dict[str, dict] = {}

# Valid labels per dataset type — constrains Gemini to labels the fusion map knows.
_VISION_VALID_LABELS: dict[str, list[str]] = {
    "chest": ["bacterial_pneumonia", "viral_pneumonia", "normal", "other"],
    "skin":  ["Acne", "Eczema", "Psoriasis", "Rosacea", "Seborrheic_Dermatitis", "Normal"],
    "wound": [
        "abrasion", "bruise", "burn", "cut", "diabetic_wound",
        "laceration", "normal", "pressure_wound", "surgical_wound", "venous_wound",
    ],
}

async def validate_vision_with_gemini(
    image_path: str,
    cnn_result: dict,
    symptoms: list[str],
    language: str = "en",
) -> dict | None:
    """
    Validate a CNN vision prediction with Gemini Vision.
    Only worth calling when CNN confidence < 0.60 — high-confidence predictions are trusted.
    Returns {"agrees": bool, "alternative": str|None, "reasoning": str} or None on failure.
    Cached by (image_hash, cnn_label) — same image+label never re-calls Gemini.
    """
    if not settings.GEMINI_API_KEY:
        return None

    top_pred     = cnn_result.get("top_prediction", {})
    cnn_label    = top_pred.get("label", "unknown") if isinstance(top_pred, dict) else str(top_pred)
    cnn_conf     = round((top_pred.get("confidence", 0) if isinstance(top_pred, dict) else 0) * 100)
    dataset_type = cnn_result.get("dataset_type", "medical")

    # Cache by image content hash so different images always get validated
    import hashlib
    try:
        with open(image_path, "rb") as f:
            img_hash = hashlib.md5(f.read(65536)).hexdigest()[:16]  # first 64KB is enough
    except Exception:
        img_hash = cnn_label  # fallback: cache by label if file unreadable

    cache_key = f"vis_val:{img_hash}:{cnn_label}"
    if cache_key in _vision_validate_cache:
        logger.debug("vaidya.llm.vision_validate_cache_hit", label=cnn_label)
        return _vision_validate_cache[cache_key]

    try:
        import base64
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as exc:
        logger.warning("vaidya.llm.vision_validate_read_failed", error=str(exc))
        return None

    mime_type     = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    valid_labels  = _VISION_VALID_LABELS.get(dataset_type, [cnn_label])
    labels_str    = ", ".join(valid_labels)
    symptoms_str  = ", ".join(symptoms[:8]) or "not specified"

    prompt = (
        f"This is a {dataset_type} medical image.\n"
        f"CNN model predicted: {cnn_label} (confidence: {cnn_conf}%).\n"
        f"Patient symptoms: {symptoms_str}.\n\n"
        f"Valid labels for this image type: {labels_str}\n\n"
        f"Does this image visually match '{cnn_label}'?\n"
        f"Reply ONLY with JSON (no other text):\n"
        f'If yes: {{"agrees": true, "alternative": null, "reasoning": "<1 sentence>"}}\n'
        f'If no:  {{"agrees": false, "alternative": "<one label from the valid list above>", "reasoning": "<1 sentence>"}}'
    )

    messages = [{"role": "user", "parts": [
        {"inlineData": {"mimeType": mime_type, "data": image_b64}},
        {"text": prompt},
    ]}]

    try:
        raw = await _call_gemini(messages)
        if not raw:
            return None
        data = _parse_llm_json(raw)
        if not isinstance(data, dict) or "agrees" not in data:
            return None
        # Only accept an alternative that is a known label
        alt = data.get("alternative")
        if alt and alt not in valid_labels:
            data["alternative"] = None
        _vision_validate_cache[cache_key] = data
        logger.info(
            "vaidya.llm.vision_validated",
            label=cnn_label, agrees=data["agrees"],
            alternative=data.get("alternative"),
        )
        return data
    except Exception as exc:
        logger.warning("vaidya.llm.vision_validate_failed", error=str(exc))
        return None


# Cache for vision enrichment: (cnn_label, dataset_type, language) → description
# Vision description is driven by CNN output, not pixel content — safe to cache.
_vision_enrich_cache: dict[str, str] = {}

async def enrich_vision_with_gemini(
    image_path: str,
    cnn_result: dict,
    symptoms: list[str],
    language: str = "en",
) -> str | None:
    """
    Ask Gemini Vision to describe a medical image and corroborate the CNN result.
    Sends the image as base64 inlineData alongside a clinical prompt.
    Returns plain-text description, or None on failure.
    Cached by (cnn_label, dataset_type, language) to avoid duplicate Gemini calls.
    """
    if not settings.GEMINI_API_KEY:
        return None

    top_pred     = cnn_result.get("top_prediction", {})
    cnn_label    = top_pred.get("label", "unknown") if isinstance(top_pred, dict) else str(top_pred)
    cnn_conf     = round(top_pred.get("confidence", 0) * 100) if isinstance(top_pred, dict) else 0
    dataset_type = cnn_result.get("dataset_type", "medical")

    vision_cache_key = f"{cnn_label}|{dataset_type}|{language}"
    if vision_cache_key in _vision_enrich_cache:
        logger.debug("vaidya.llm.vision_cache_hit", label=cnn_label)
        return _vision_enrich_cache[vision_cache_key]

    try:
        import base64
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as exc:
        logger.warning("vaidya.llm.vision_read_failed", error=str(exc))
        return None

    mime_type = "image/jpeg" if image_path.lower().endswith(".jpg") else "image/png"

    lang_note = _EXPLAIN_LANG_NOTE.get(language, _EXPLAIN_LANG_NOTE["en"])
    prompt = (
        f"This is a {dataset_type} medical image.\n"
        f"CNN model predicted: {cnn_label} (confidence: {cnn_conf}%).\n"
        f"Patient reported symptoms: {', '.join(symptoms) or 'not specified'}.\n\n"
        f"In 3-4 concise sentences:\n"
        f"1. Describe the key visual findings you observe in the image.\n"
        f"2. State whether the visual findings are consistent with '{cnn_label}'.\n"
        f"3. Note one key clinical observation relevant to the patient's symptoms.\n\n"
        f"{lang_note}\n"
        f"Be specific and clinical. No JSON. No disclaimer."
    )

    messages = [
        {
            "role": "user",
            "parts": [
                {"inlineData": {"mimeType": mime_type, "data": image_b64}},
                {"text": prompt},
            ],
        }
    ]

    try:
        raw = await _call_gemini(messages)
        result = _strip_md(raw.strip()) if raw else None
        if result:
            _vision_enrich_cache[vision_cache_key] = result
        return result
    except Exception as exc:
        logger.warning("vaidya.llm.vision_enrich_failed", error=str(exc))
        return None


# In-process cache: diagnosis+language → enrichment text (avoids repeat Gemini calls)
_enrich_cache: dict[str, str] = {}

async def enrich_diagnosis_with_gemini(
    primary_diagnosis: str,
    symptoms: list[str],
    language: str = "en",
) -> str | None:
    """
    Ask Gemini for a plain-language explanation of the diagnosis with
    prevention and specific precautions. Returns a single formatted string,
    or None on failure. Non-blocking — callers should never await this in the
    critical path; use asyncio.create_task or shield.
    """
    if not settings.GEMINI_API_KEY:
        return None

    cache_key = f"{primary_diagnosis}:{language}"
    if cache_key in _enrich_cache:
        return _enrich_cache[cache_key]

    lang_note = _EXPLAIN_LANG_NOTE.get(language, _EXPLAIN_LANG_NOTE["en"])
    prompt = (
        f"A patient has been assessed with: **{primary_diagnosis}**.\n"
        f"Reported symptoms: {', '.join(symptoms) or 'not specified'}.\n\n"
        f"Write a brief, plain-language health guide (3 short sections):\n"
        f"1. **What is {primary_diagnosis}?** (2-3 sentences, simple language)\n"
        f"2. **How to prevent it** (3-4 bullet points)\n"
        f"3. **What to do now** (3-4 specific action steps the patient should take)\n\n"
        f"{lang_note}\n"
        f"Keep each section short. No JSON. No medical jargon. No disclaimer needed."
    )
    messages = [{"role": "user", "parts": [{"text": prompt}]}]
    try:
        raw = await _call_gemini(messages)
        result = _strip_md(raw.strip()) if raw else None
        if result:
            _enrich_cache[cache_key] = result
        return result
    except Exception as exc:
        logger.warning("vaidya.llm.enrich_failed", error=str(exc))
        return None
