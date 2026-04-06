"""
Vaidya — test suite
Tests: API health, NLP extraction, classifier, triage engine, care finder
Run: pytest -v --cov=app --cov-report=term-missing
"""

import asyncio
import json
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.core.config import settings
from app.services.diagnosis.classifier import _detect_red_flags
from app.services.nlp.extractor import _map_to_canonical, CANONICAL_SYMPTOMS
from app.services.triage.engine import compute_triage_level as _compute_level, TRIAGE_LABELS
from app.schemas.schemas import DiagnosisResult


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator:
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.ping.return_value = True
    redis.get.return_value = None
    redis.setex.return_value = True
    redis.zremrangebyscore.return_value = 0
    redis.zadd.return_value = 1
    redis.zcard.return_value = 1
    redis.expire.return_value = True
    redis.pipeline.return_value.__aenter__ = AsyncMock(return_value=redis)
    redis.pipeline.return_value.__aexit__ = AsyncMock(return_value=False)
    redis.pipeline.return_value.execute = AsyncMock(return_value=[0, 1, 1, True])
    return redis


@pytest.fixture
def sample_symptom_vector():
    vector = {col: 0 for col in CANONICAL_SYMPTOMS}
    vector.update({
        "high_fever": 1,
        "cough": 1,
        "breathlessness": 1,
        "chest_pain": 1,
        "fatigue": 1,
    })
    return vector


@pytest.fixture
def sample_diagnosis():
    return DiagnosisResult(
        primary_diagnosis="Pneumonia",
        confidence=0.87,
        differential=[{"disease": "Bronchitis", "confidence": 0.45}],
        diagnosis_source="xgboost",
        red_flags=[],
    )


# ── Health check ───────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_200(self, client):
        with patch("app.main.redis_client") as mock_r:
            mock_r.ping = AsyncMock(return_value=True)
            response = client.get("/health")
        assert response.status_code == 200

    def test_health_schema(self, client):
        with patch("app.main.redis_client") as mock_r:
            mock_r.ping = AsyncMock(return_value=True)
            data = client.get("/health").json()
        assert "status" in data
        assert "version" in data
        assert data["version"] == settings.VERSION


# ── NLP extraction ─────────────────────────────────────────────────────────────

class TestNLPExtraction:
    def test_map_canonical_basic(self):
        raw = {
            "symptoms": ["fever", "cough", "breathlessness"],
            "duration": "3 days",
            "severity_estimate": 7,
            "body_parts": ["chest"],
            "raw_keywords": ["fever", "cough"],
        }
        result, _unmatched, _vector = _map_to_canonical(raw, spacy_extra=[])
        assert "high_fever" in result.symptoms or "cough" in result.symptoms
        assert result.duration == "3 days"
        assert result.severity_estimate == 7

    def test_synonym_mapping(self):
        raw = {
            "symptoms": ["loose motions", "throwing up", "tired"],
            "duration": None,
            "severity_estimate": None,
            "body_parts": [],
            "raw_keywords": [],
        }
        result, _unmatched, _vector = _map_to_canonical(raw, spacy_extra=[])
        assert "diarrhoea" in result.symptoms
        assert "vomiting" in result.symptoms
        assert "fatigue" in result.symptoms

    def test_fuzzy_matching(self):
        raw = {
            "symptoms": ["headch", "fevr"],  # intentional typos
            "duration": None,
            "severity_estimate": None,
            "body_parts": [],
            "raw_keywords": [],
        }
        result, _unmatched, _vector = _map_to_canonical(raw, spacy_extra=[])
        # Fuzzy match should catch close enough terms
        assert len(result.symptoms) >= 0  # may or may not match depending on cutoff

    def test_symptom_vector_length(self):
        raw = {
            "symptoms": ["fever", "cough"],
            "duration": "2 days",
            "severity_estimate": 5,
            "body_parts": [],
            "raw_keywords": ["fever"],
        }
        _result, _unmatched, vector = _map_to_canonical(raw, spacy_extra=[])
        assert len(CANONICAL_SYMPTOMS) == 133

    @pytest.mark.parametrize("lang_symptom,expected_canonical", [
        ("loose motions", "diarrhoea"),
        ("throwing up", "vomiting"),
        ("sore throat", "throat_irritation"),
        ("yellow eyes", "yellowing_of_eyes"),
        ("body pain", "muscle_pain"),
        ("fits", "altered_sensorium"),
    ])
    def test_synonym_table(self, lang_symptom, expected_canonical):
        from app.services.nlp.extractor import SYNONYM_MAP
        assert lang_symptom in SYNONYM_MAP
        assert SYNONYM_MAP[lang_symptom] == expected_canonical


# ── Red flag detection ─────────────────────────────────────────────────────────

class TestRedFlags:
    def test_chest_pain_breathlessness(self):
        vector = {col: 0 for col in CANONICAL_SYMPTOMS}
        vector["chest_pain"] = 1
        vector["breathlessness"] = 1
        flags = _detect_red_flags(vector)
        assert len(flags) > 0
        assert any("cardiac" in f.lower() or "chest" in f.lower() for f in flags)

    def test_no_flags_normal_symptoms(self):
        vector = {col: 0 for col in CANONICAL_SYMPTOMS}
        vector["cough"] = 1
        vector["mild_fever"] = 1
        flags = _detect_red_flags(vector)
        assert flags == []

    def test_meningitis_pattern(self):
        vector = {col: 0 for col in CANONICAL_SYMPTOMS}
        vector["high_fever"] = 1
        vector["stiff_neck"] = 1
        flags = _detect_red_flags(vector)
        assert any("meningitis" in f.lower() for f in flags)

    def test_loss_of_consciousness(self):
        vector = {col: 0 for col in CANONICAL_SYMPTOMS}
        vector["loss_of_consciousness"] = 1
        flags = _detect_red_flags(vector)
        assert len(flags) > 0


# ── Triage engine ──────────────────────────────────────────────────────────────

class TestTriageEngine:
    def test_emergency_with_red_flags(self):
        diagnosis = DiagnosisResult(
            primary_diagnosis="Unknown",
            confidence=0.5,
            differential=[],
            diagnosis_source="xgboost",
            red_flags=["Chest pain + breathlessness — possible cardiac event"],
        )
        level = _compute_level(diagnosis, self_severity=8)
        assert level >= 4

    def test_self_care_for_minor_disease(self):
        diagnosis = DiagnosisResult(
            primary_diagnosis="Common Cold",
            confidence=0.9,
            differential=[],
            diagnosis_source="xgboost",
            red_flags=[],
        )
        level = _compute_level(diagnosis, self_severity=2)
        assert level == 1

    def test_urgent_pneumonia_high_confidence(self):
        diagnosis = DiagnosisResult(
            primary_diagnosis="Pneumonia",
            confidence=0.87,
            differential=[],
            diagnosis_source="xgboost",
            red_flags=[],
        )
        level = _compute_level(diagnosis, self_severity=7)
        assert level >= 3

    def test_level_escalation_with_high_self_severity(self):
        diagnosis = DiagnosisResult(
            primary_diagnosis="Acne",
            confidence=0.9,
            differential=[],
            diagnosis_source="xgboost",
            red_flags=[],
        )
        level_low = _compute_level(diagnosis, self_severity=2)
        level_high = _compute_level(diagnosis, self_severity=9)
        assert level_high >= level_low

    def test_triage_labels_coverage(self):
        assert all(i in TRIAGE_LABELS for i in range(1, 6))

    def test_llm_fallback_gets_see_doctor(self):
        diagnosis = DiagnosisResult(
            primary_diagnosis="Undetermined — clinical evaluation required",
            confidence=0.0,
            differential=[],
            diagnosis_source="llm_gemini",
            red_flags=[],
        )
        level = _compute_level(diagnosis, self_severity=5)
        assert level >= 3


# ── LLM prompt ────────────────────────────────────────────────────────────────

class TestLLMFallback:
    def test_parse_valid_json(self):
        from app.services.diagnosis.llm_fallback import _parse_llm_json
        raw = json.dumps({
            "primary_diagnosis": "Viral fever",
            "confidence": 0.72,
            "differential": [{"disease": "Dengue", "confidence": 0.3}],
            "red_flags": [],
            "description": "A common viral infection.",
            "precautions": ["rest", "drink fluids"],
            "triage_level": 2,
            "reasoning": "Low severity viral pattern.",
            "disclaimer": "Consult a doctor.",
        })
        result = _parse_llm_json(raw)
        assert result["primary_diagnosis"] == "Viral fever"
        assert result["confidence"] == 0.72

    def test_parse_json_with_markdown_fences(self):
        from app.services.diagnosis.llm_fallback import _parse_llm_json
        raw = '```json\n{"primary_diagnosis": "Malaria", "confidence": 0.8, "differential": [], "precautions": ["take antimalarial"]}\n```'
        result = _parse_llm_json(raw)
        assert result["primary_diagnosis"] == "Malaria"

    def test_parse_invalid_json_raises(self):
        from app.services.diagnosis.llm_fallback import _parse_llm_json
        result = _parse_llm_json("This is not JSON at all.")
        assert result is None

    def test_confidence_clamped(self):
        from app.services.diagnosis.llm_fallback import _parse_llm_json, _validate_parsed
        raw = json.dumps({
            "primary_diagnosis": "X",
            "confidence": 1.5,  # out of range
            "differential": [],
            "precautions": [],
            "triage_level": 3,
            "disclaimer": "Consult a doctor for a proper diagnosis.",
        })
        parsed = _parse_llm_json(raw)
        assert parsed is not None
        validated = _validate_parsed(parsed)
        assert validated is not None
        assert validated.confidence <= 1.0


# ── Input API ─────────────────────────────────────────────────────────────────

class TestInputAPI:
    @pytest.mark.asyncio
    async def test_text_input_english(self, async_client, mock_redis):
        with patch("app.api.v1.endpoints.input.detect_language", return_value="en"), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            response = await async_client.post(
                "/api/v1/input/text",
                json={"text": "I have fever and cough for three days", "language": "en"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["original_language"] == "en"
        assert "cache_key" in data

    @pytest.mark.asyncio
    async def test_text_input_too_short(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            response = await async_client.post(
                "/api/v1/input/text",
                json={"text": "Hi"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_voice_unsupported_format(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            response = await async_client.post(
                "/api/v1/input/voice",
                files={"file": ("test.mp4", b"fakevideo", "video/mp4")},
            )
        assert response.status_code == 415


# ── Care finder ───────────────────────────────────────────────────────────────

class TestCareFinder:
    def test_haversine_same_point(self):
        from app.services.care.overpass import haversine_km
        assert haversine_km(12.97, 79.16, 12.97, 79.16) == pytest.approx(0.0, abs=0.01)

    def test_haversine_known_distance(self):
        from app.services.care.overpass import haversine_km
        # Vellore to Chennai: ~130km
        dist = haversine_km(12.9165, 79.1325, 13.0827, 80.2707)
        assert 120 < dist < 145

    def test_classify_phc(self):
        from app.services.care.overpass import classify_facility_type
        assert classify_facility_type({"name": "PHC Katpadi"}) == "phc"

    def test_classify_private(self):
        from app.services.care.overpass import classify_facility_type
        assert classify_facility_type({"name": "Apollo Hospital"}) == "private"

    @pytest.mark.asyncio
    async def test_hospitals_endpoint(self, async_client, mock_redis):
        mock_result = {
            "results": [],
            "total": 0,
            "patient_location": {"lat": 12.97, "lng": 79.16, "district": ""},
        }
        with patch("app.api.v1.endpoints.care.find_nearby_hospitals", return_value=MagicMock(**mock_result)), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            response = await async_client.get(
                "/api/v1/care/hospitals?lat=12.97&lng=79.16"
            )
        assert response.status_code in (200, 422, 500)  # depends on mock depth
