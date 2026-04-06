"""
Vaidya — /api/v1/llm  (Module 5 — LLM fallback endpoints)

POST /diagnose              — explicit LLM diagnosis (bypass XGBoost)
POST /diagnose/stream       — streaming SSE version for real-time UI
GET  /diagnose/explain      — explain why fallback was triggered for a session
GET  /prompts/fallback      — inspect the LLM system prompt (dev only)
POST /prompts/fallback/test — test a new prompt version before deploying
"""

import asyncio
import json
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.redis import get_redis
from app.schemas.schemas import DiagnosisResult
from app.services.diagnosis.llm_fallback import (
    LLMDiagnosisOutput,
    _build_user_message,
    _build_messages,
    _call_gemini,
    _parse_llm_json,
    _safe_fallback,
    _to_diagnosis_result,
    _validate_parsed,
    run_llm_fallback,
    stream_llm_fallback,
)
from app.services.nlp.prompt_loader import load_prompt, list_available_prompts

router = APIRouter()
logger = structlog.get_logger(__name__)


# ── Request schemas ────────────────────────────────────────────────────────────

class LLMDiagnoseRequest(BaseModel):
    symptoms:   list[str] = Field(..., min_length=1, description="Canonical symptom names or natural language symptom list")
    keywords:   list[str] = Field(default_factory=list, description="Raw extracted keywords for additional context")
    severity:   Optional[int] = Field(None, ge=1, le=10)
    language:   str = Field("en", pattern="^(en|hi|ta)$")
    duration:   Optional[str] = Field(None, max_length=100)
    age_group:  Optional[str] = Field(None, pattern="^(child|adult|senior)$")
    red_flags:  Optional[list[str]] = Field(default_factory=list)
    prompt_version: str = Field("v1", description="Prompt template version to use")


class PromptTestRequest(BaseModel):
    symptoms:  list[str] = Field(..., min_length=1)
    keywords:  list[str] = Field(default_factory=list)
    severity:  Optional[int] = Field(None, ge=1, le=10)
    language:  str = Field("en", pattern="^(en|hi|ta)$")
    version:   str = Field("v1")


# ── POST /diagnose ─────────────────────────────────────────────────────────────

@router.post(
    "/diagnose",
    response_model=DiagnosisResult,
    summary="Explicit LLM diagnosis — bypasses XGBoost entirely",
)
async def llm_diagnose(
    payload: LLMDiagnoseRequest,
    redis=Depends(get_redis),
):
    """
    Runs Llama 3.1 8B directly for diagnosis without consulting the XGBoost model first.

    Use this endpoint when:
    - XGBoost explicitly returned low confidence (< 0.60)
    - Symptom presentation doesn't fit standard disease classes
    - Patient describes unusual or complex symptom combinations
    - You want a second opinion on an XGBoost diagnosis

    Unlike the /diagnose/predict pipeline, this endpoint:
    - Skips the XGBoost classifier entirely
    - Accepts natural language symptoms (not just canonical names)
    - Returns additional fields: triage_level hint, ICD hint, emergency guidance
    - Is slower (~5–15s on CPU) than XGBoost (~0.05s)

    The response is a standard DiagnosisResult compatible with /triage and /care.
    """
    import hashlib

    # Cache key — same clinical input within 5 min gets same LLM response
    cache_input = f"{sorted(payload.symptoms)}|{payload.severity}|{payload.language}|{payload.prompt_version}"
    cache_key   = f"llm:v1:{hashlib.sha256(cache_input.encode()).hexdigest()[:20]}"

    cached = await redis.get(cache_key)
    if cached:
        logger.debug("vaidya.llm_ep.cache_hit")
        data = json.loads(cached)
        return DiagnosisResult(**data)

    logger.info(
        "vaidya.llm_ep.start",
        symptoms=len(payload.symptoms),
        language=payload.language,
        version=payload.prompt_version,
    )

    result = await run_llm_fallback(
        symptoms=payload.symptoms,
        keywords=payload.keywords,
        severity=payload.severity,
        language=payload.language,
        duration=payload.duration,
        age_group=payload.age_group,
        red_flags=payload.red_flags,
        version=payload.prompt_version,
    )

    # Cache for 5 min — LLM responses are expensive
    await redis.setex(cache_key, 300, result.model_dump_json())

    return result


# ── POST /diagnose/stream ──────────────────────────────────────────────────────

@router.post(
    "/diagnose/stream",
    summary="Streaming LLM diagnosis — real-time token output via SSE",
    response_class=StreamingResponse,
)
async def llm_diagnose_stream(payload: LLMDiagnoseRequest):
    """
    Streaming version of /diagnose using Server-Sent Events.
    The frontend receives JSON tokens as they are generated — useful for
    showing a real-time "thinking" animation while Llama is running.

    Event format:
        data: {"chunk": "partial json text", "done": false}
        data: {"chunk": "", "done": true, "full_json": {...}}

    The final event includes the fully assembled and validated JSON.
    If validation fails, the final event includes an error field instead.

    Client usage (JavaScript):
        const es = new EventSource('/api/v1/llm/diagnose/stream', {method: 'POST', ...});
        es.onmessage = e => {
            const {chunk, done, full_json} = JSON.parse(e.data);
            if (done) setResult(full_json);
            else appendToDisplay(chunk);
        };
    """
    async def event_generator():
        full_text = ""
        try:
            async for chunk in stream_llm_fallback(
                symptoms=payload.symptoms,
                keywords=payload.keywords,
                severity=payload.severity,
                language=payload.language,
                duration=payload.duration,
                version=payload.prompt_version,
            ):
                full_text += chunk
                yield f"data: {json.dumps({'chunk': chunk, 'done': False})}\n\n"

            # Assemble, parse, and validate the complete output
            parsed = _parse_llm_json(full_text)
            if parsed:
                try:
                    validated  = _validate_parsed(parsed)
                    result     = _to_diagnosis_result(validated)
                    final_data = result.model_dump()
                    # Add extra fields from validated output not in DiagnosisResult
                    final_data["triage_level"]           = validated.triage_level
                    final_data["triage_reasoning"]       = validated.triage_reasoning
                    final_data["when_to_seek_emergency"] = validated.when_to_seek_emergency
                    final_data["icd_hint"]               = validated.icd_hint
                    final_data["confidence_reason"]      = validated.confidence_reason
                    yield f"data: {json.dumps({'chunk': '', 'done': True, 'full_json': final_data})}\n\n"
                except Exception as exc:
                    yield f"data: {json.dumps({'chunk': '', 'done': True, 'error': str(exc)})}\n\n"
            else:
                yield f"data: {json.dumps({'chunk': '', 'done': True, 'error': 'JSON parse failed'})}\n\n"

        except Exception as exc:
            logger.error("vaidya.llm_ep.stream_error", error=str(exc))
            fallback = _safe_fallback(payload.symptoms, reason=str(exc))
            yield f"data: {json.dumps({'chunk': '', 'done': True, 'full_json': fallback.model_dump()})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # required for nginx SSE pass-through
        },
    )


# ── GET /prompts/fallback ─────────────────────────────────────────────────────

@router.get(
    "/prompts/fallback",
    summary="Inspect LLM fallback prompt templates (dev only)",
)
async def get_fallback_prompts(version: str = Query("v1")):
    """
    Returns the current system prompt and few-shot examples used for LLM diagnosis.
    Useful for prompt engineering and debugging LLM output quality.
    Only available in development environments.
    """
    if settings.ENV == "production":
        raise HTTPException(403, "Prompt inspection disabled in production")

    try:
        system   = load_prompt(f"llm_fallback_{version}.txt")
        examples = load_prompt(f"llm_fallback_examples_{version}.txt")
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))

    return {
        "version":        version,
        "system_chars":   len(system),
        "examples_chars": len(examples),
        "system_prompt":  system,
        "examples":       examples,
        "available":      [p for p in list_available_prompts() if "fallback" in p],
    }


# ── POST /prompts/fallback/test ────────────────────────────────────────────────

@router.post(
    "/prompts/fallback/test",
    summary="Test a prompt version against a sample query (dev only)",
)
async def test_prompt_version(payload: PromptTestRequest):
    """
    Runs a full LLM diagnosis with the specified prompt version.
    Use this to A/B test new prompt templates before promoting them to default.
    Only available in development environments.
    """
    if settings.ENV == "production":
        raise HTTPException(403, "Prompt testing disabled in production")

    user_msg = _build_user_message(
        symptoms=payload.symptoms,
        keywords=payload.keywords,
        severity=payload.severity,
        language=payload.language,
    )

    try:
        messages = _build_messages(
            symptoms=payload.symptoms,
            keywords=payload.keywords,
            severity=payload.severity,
            language=payload.language,
            version=payload.version,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, f"Prompt version '{payload.version}' not found: {exc}")

    raw = await _call_gemini(messages)
    if not raw:
        raise HTTPException(503, "Gemini unreachable")

    parsed = _parse_llm_json(raw)
    parse_success = parsed is not None

    validation_error = None
    validated = None
    if parsed:
        try:
            validated = _validate_parsed(parsed)
        except Exception as exc:
            validation_error = str(exc)

    return {
        "version":          payload.version,
        "user_message":     user_msg,
        "raw_response":     raw,
        "parse_success":    parse_success,
        "validation_error": validation_error,
        "result":           validated.model_dump() if validated else None,
    }
