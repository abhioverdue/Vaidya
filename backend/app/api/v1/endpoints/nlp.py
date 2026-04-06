"""
Vaidya — /api/v1/nlp  (Module 3 — complete)

POST /extract               — full pipeline: text → LLM → 133-feature vector
POST /extract/batch         — parallel batch extraction (up to 10 texts)
GET  /symptoms              — list all 133 canonical symptom names
GET  /symptoms/search       — fuzzy-search canonical list
POST /vector                — build vector directly from canonical names
GET  /prompts               — list prompt template versions
GET  /prompts/{filename}    — inspect prompt (dev only)
"""

import difflib
import hashlib
import json
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.redis import get_redis
from app.schemas.schemas import ExtractedSymptoms, TextInputRequest
from app.services.nlp.extractor import (
    CANONICAL_SYMPTOMS,
    SYNONYM_MAP,
    extract_symptoms,
    build_symptom_vector,
)
from app.services.nlp.prompt_loader import list_available_prompts, load_prompt

router = APIRouter()
logger = structlog.get_logger(__name__)


# ── Local response schemas (not in global schemas.py — endpoint-specific) ──────

class ExtractResponse(BaseModel):
    session_cache_key:   str
    input_language:      str
    extracted:           ExtractedSymptoms
    symptom_vector:      dict[str, int]
    matched_count:       int
    unmatched_terms:     list[str]
    vector_active_count: int
    red_flags:           list[str] = Field(default_factory=list)
    onset_type:          Optional[str] = None


class BatchRequest(BaseModel):
    texts:    list[str] = Field(..., min_length=1, max_length=10)
    language: Optional[str] = Field(None, pattern="^(en|hi|ta)$")


class VectorRequest(BaseModel):
    symptoms: list[str] = Field(..., description="Canonical symptom name list")


# ── POST /extract ──────────────────────────────────────────────────────────────

@router.post("/extract", response_model=ExtractResponse,
             summary="Extract symptoms → 133-feature binary vector")
async def extract(payload: TextInputRequest, redis=Depends(get_redis)):
    """
    Full NLP extraction pipeline for a single patient symptom description.

    Pipeline: cache → translate → Ollama LLM → spaCy NER → canonical map → vector

    The returned symptom_vector is the direct XGBoost classifier input.
    Pass it straight to POST /diagnose/predict.

    Examples:
      EN: {"text": "fever and cough for 3 days, chest pain on breathing"}
      HI: {"text": "मुझे बुखार और खांसी है", "language": "hi"}
      TA: {"text": "எனக்கு காய்ச்சல் உள்ளது", "language": "ta"}
    """
    logger.info("vaidya.nlp.extract", text_len=len(payload.text), lang=payload.language)

    extracted, unmatched, vector = await extract_symptoms(
        text=payload.text,
        language=payload.language,
        redis=redis,
    )

    cache_key = f"nlp:v3:{hashlib.sha256(payload.text.encode()).hexdigest()[:24]}"

    # Pull red_flags + onset_type from cached LLM output
    red_flags, onset_type = [], None
    try:
        raw = await redis.get(cache_key)
        if raw:
            d          = json.loads(raw)
            red_flags  = d.get("red_flags", [])
            onset_type = d.get("onset_type")
    except Exception:
        pass

    return ExtractResponse(
        session_cache_key=cache_key,
        input_language=payload.language or "auto",
        extracted=extracted,
        symptom_vector=vector,
        matched_count=len(extracted.symptoms),
        unmatched_terms=unmatched,
        vector_active_count=sum(vector.values()),
        red_flags=red_flags,
        onset_type=onset_type,
    )


# ── POST /extract/batch ────────────────────────────────────────────────────────

@router.post("/extract/batch", summary="Parallel batch extraction (max 10 texts)")
async def extract_batch(payload: BatchRequest, redis=Depends(get_redis)):
    """Run concurrent extraction across multiple texts. Total time ≈ single extraction."""
    import asyncio

    async def _one(text: str):
        try:
            ext, unmatched, vec = await extract_symptoms(
                text=text, language=payload.language, redis=redis
            )
            return {
                "preview":       text[:80] + ("..." if len(text) > 80 else ""),
                "symptoms":      ext.symptoms,
                "matched_count": len(ext.symptoms),
                "vector_active": sum(vec.values()),
                "unmatched":     unmatched,
                "error":         None,
            }
        except Exception as exc:
            return {"preview": text[:80], "symptoms": [], "error": str(exc)}

    results = await asyncio.gather(*[_one(t) for t in payload.texts])
    return {"count": len(results), "results": results}


# ── GET /symptoms ──────────────────────────────────────────────────────────────

@router.get("/symptoms", summary="List all 133 canonical symptom names")
async def list_symptoms(
    group_by_alpha: bool = Query(False),
):
    if group_by_alpha:
        from collections import defaultdict
        grouped: dict[str, list] = defaultdict(list)
        for s in sorted(CANONICAL_SYMPTOMS):
            grouped[s[0].upper()].append(s)
        return {"total": len(CANONICAL_SYMPTOMS), "grouped": dict(sorted(grouped.items()))}
    return {"total": len(CANONICAL_SYMPTOMS), "symptoms": CANONICAL_SYMPTOMS}


# ── GET /symptoms/search ───────────────────────────────────────────────────────

@router.get("/symptoms/search", summary="Fuzzy-search canonical symptom list")
async def search_symptoms(
    q:     str = Query(..., min_length=2),
    limit: int = Query(5, ge=1, le=20),
):
    """Find the closest canonical symptom names for any phrasing (autocomplete / test)."""
    q_lower = q.lower().strip()
    q_snake = q_lower.replace(" ", "_")

    # Direct synonym lookup
    if q_lower in SYNONYM_MAP:
        return {"query": q, "results": [{"symptom": SYNONYM_MAP[q_lower], "score": 1.0, "via": "synonym_map"}]}

    # Fuzzy on snake_case
    matches = difflib.get_close_matches(q_snake, CANONICAL_SYMPTOMS, n=limit, cutoff=0.4)

    # Also try spaced form
    can_spaced = [s.replace("_", " ") for s in CANONICAL_SYMPTOMS]
    for m in difflib.get_close_matches(q_lower, can_spaced, n=limit, cutoff=0.4):
        can = CANONICAL_SYMPTOMS[can_spaced.index(m)]
        if can not in matches:
            matches.append(can)

    results = sorted(
        [{"symptom": m, "score": round(difflib.SequenceMatcher(None, q_snake, m).ratio(), 3), "via": "fuzzy"} for m in matches[:limit]],
        key=lambda x: -x["score"],
    )
    return {"query": q, "results": results}


# ── POST /vector ───────────────────────────────────────────────────────────────

@router.post("/vector", summary="Build binary vector from canonical symptom names")
async def build_vector(payload: VectorRequest):
    """Skip LLM extraction entirely — build the XGBoost input vector from known symptom names."""
    invalid = [s for s in payload.symptoms if s not in CANONICAL_SYMPTOMS]
    if invalid:
        raise HTTPException(422, {
            "error":   "invalid_symptom_names",
            "invalid": invalid,
            "hint":    "Use GET /nlp/symptoms/search to find the correct canonical name",
        })
    vector = build_symptom_vector(payload.symptoms)
    return {
        "input_symptoms": payload.symptoms,
        "symptom_vector": vector,
        "active_count":   sum(vector.values()),
        "total_features": len(vector),
    }


# ── GET /prompts ───────────────────────────────────────────────────────────────

@router.get("/prompts", summary="List available prompt templates")
async def list_prompts():
    return {"available": list_available_prompts(), "hot_reload": settings.ENV == "development"}


@router.get("/prompts/{filename}", summary="Inspect a prompt template (dev only)")
async def get_prompt(filename: str):
    if settings.ENV == "production":
        raise HTTPException(403, "Prompt inspection disabled in production")
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")
    try:
        content = load_prompt(filename)
        return {"filename": filename, "content": content, "chars": len(content)}
    except FileNotFoundError:
        raise HTTPException(404, f"Prompt '{filename}' not found")
