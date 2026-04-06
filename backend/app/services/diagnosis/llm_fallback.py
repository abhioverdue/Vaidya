"""
Vaidya — LLM fallback diagnosis service  (Gemini 1.5 Flash)
Replaces Ollama/Llama with Google Gemini 1.5 Flash via REST API.
"""
import json, re, time
from typing import AsyncIterator, Optional

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


def _to_diagnosis_result(out: LLMDiagnosisOutput) -> DiagnosisResult:
    return DiagnosisResult(
        primary_diagnosis=out.primary_diagnosis, confidence=out.confidence, icd_hint=out.icd_hint,
        differential=[d.model_dump() for d in out.differential], red_flags=out.red_flags,
        description=out.description, precautions=out.precautions,
        when_to_seek_emergency=out.when_to_seek_emergency, triage_level=out.triage_level,
        triage_reasoning=out.triage_reasoning, confidence_reason=out.confidence_reason,
        disclaimer=out.disclaimer, diagnosis_source="llm_gemini",
    )


# expose internal helpers for endpoint imports
_build_user_message = lambda *a, **k: _build_messages(*a, **k)[0]["parts"][0]["text"]


@retry(retry=retry_if_exception_type(httpx.ConnectError), stop=stop_after_attempt(3),
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
