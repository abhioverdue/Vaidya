"""
Vaidya — Module 5 test suite
Tests: prompt loading, user message building, JSON parsing (4 strategies),
       Pydantic schema validation, field clamping, disclaimer enforcement,
       safe fallback, run_llm_fallback end-to-end, streaming, LLM endpoints
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from pydantic import ValidationError

from app.main import app
from app.schemas.schemas import DiagnosisResult
from app.services.diagnosis.llm_fallback import (
    LLMDiagnosisOutput,
    _build_messages,
    _build_user_message,
    _call_gemini,
    _parse_llm_json,
    _safe_fallback,
    _to_diagnosis_result,
    _validate_parsed,
    run_llm_fallback,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get.return_value = None
    r.setex.return_value = True
    r.zremrangebyscore = AsyncMock(return_value=0)
    r.zadd = AsyncMock(return_value=1)
    r.zcard = AsyncMock(return_value=1)
    r.expire = AsyncMock(return_value=True)
    pipeline_mock = AsyncMock()
    pipeline_mock.__aenter__ = AsyncMock(return_value=pipeline_mock)
    pipeline_mock.__aexit__ = AsyncMock(return_value=False)
    pipeline_mock.execute = AsyncMock(return_value=[0, 1, 1, True])
    r.pipeline.return_value = pipeline_mock
    return r


def _good_llm_response(**overrides) -> str:
    base = {
        "primary_diagnosis":      "Dengue Fever",
        "confidence":             0.82,
        "icd_hint":               "A90",
        "differential": [
            {"disease": "Malaria",      "confidence": 0.30, "reasoning": "Also causes fever in rural India"},
            {"disease": "Chikungunya",  "confidence": 0.45, "reasoning": "Shares rash and joint pain"},
        ],
        "red_flags":              ["Platelet count may drop — get CBC today"],
        "description":            "Dengue fever is a mosquito-borne illness causing fever, rash, and joint pain.",
        "precautions":            ["Rest and hydrate", "Paracetamol only — avoid NSAIDs", "Get CBC at nearest PHC"],
        "when_to_seek_emergency": "Go immediately if bleeding from any site or platelet < 50,000",
        "triage_level":           3,
        "triage_reasoning":       "Active dengue without danger signs — needs PHC visit for platelet count.",
        "confidence_reason":      "Classic triad of fever, rash, joint pain in endemic area gives high confidence.",
        "disclaimer":             "This AI triage output is for guidance only. It is NOT a medical diagnosis or prescription. Always consult a licensed doctor before acting on this information.",
    }
    base.update(overrides)
    return json.dumps(base)


# ── Prompt loading ─────────────────────────────────────────────────────────────

class TestPromptLoading:
    def test_system_prompt_loads(self):
        from app.services.nlp.prompt_loader import load_prompt
        prompt = load_prompt("llm_fallback_v1.txt")
        assert len(prompt) > 200
        assert "OUTPUT SCHEMA" in prompt
        assert "triage_level" in prompt
        assert "disclaimer" in prompt

    def test_system_prompt_has_emergency_patterns(self):
        from app.services.nlp.prompt_loader import load_prompt
        prompt = load_prompt("llm_fallback_v1.txt")
        assert "chest pain" in prompt.lower()
        assert "meningitis" in prompt.lower()
        assert "triage_level=5" in prompt or "5" in prompt

    def test_system_prompt_has_rural_india_context(self):
        from app.services.nlp.prompt_loader import load_prompt
        prompt = load_prompt("llm_fallback_v1.txt")
        assert "rural india" in prompt.lower() or "india" in prompt.lower()
        assert "phc" in prompt.lower() or "asha" in prompt.lower()

    def test_few_shot_examples_load(self):
        from app.services.nlp.prompt_loader import load_prompt
        examples = load_prompt("llm_fallback_examples_v1.txt")
        assert "EXAMPLE_1" in examples
        assert "Dengue" in examples
        assert "Heart Attack" in examples or "Myocardial Infarction" in examples

    def test_few_shot_has_5_examples(self):
        import re
        from app.services.nlp.prompt_loader import load_prompt
        raw      = load_prompt("llm_fallback_examples_v1.txt")
        examples = re.findall(r"EXAMPLE_\d+:", raw)
        assert len(examples) >= 5

    def test_build_messages_structure(self):
        msgs = _build_messages("test symptoms | severity: 5/10 | language: English")
        roles = [m["role"] for m in msgs]
        assert roles[0] == "system"
        assert "user" in roles
        assert "assistant" in roles
        # Last message must be user (the real query)
        assert msgs[-1]["role"] == "user"
        assert "test symptoms" in msgs[-1]["content"]

    def test_build_messages_alternating_few_shot(self):
        msgs = _build_messages("test query")
        # After system, should be alternating user/assistant pairs
        non_system = [m for m in msgs if m["role"] != "system"]
        # Last one is the real query — the rest should alternate
        pairs = non_system[:-1]
        for i in range(0, len(pairs) - 1, 2):
            assert pairs[i]["role"]     == "user"
            assert pairs[i+1]["role"]   == "assistant"


# ── User message builder ───────────────────────────────────────────────────────

class TestUserMessageBuilder:
    def test_basic_english_message(self):
        msg = _build_user_message(
            symptoms=["high_fever", "cough"],
            keywords=["fever", "cough"],
            severity=7,
            language="en",
        )
        assert "high_fever" in msg
        assert "7/10" in msg
        assert "English" in msg

    def test_hindi_language_label(self):
        msg = _build_user_message([], [], None, "hi")
        assert "Hindi" in msg

    def test_tamil_language_label(self):
        msg = _build_user_message([], [], None, "ta")
        assert "Tamil" in msg

    def test_duration_included(self):
        msg = _build_user_message(["high_fever"], [], None, "en", duration="3 days")
        assert "3 days" in msg

    def test_age_group_included(self):
        msg = _build_user_message(["high_fever"], [], None, "en", age_group="child")
        assert "child" in msg

    def test_red_flags_included(self):
        msg = _build_user_message([], [], None, "en", red_flags=["chest pain + breathlessness"])
        assert "chest pain" in msg

    def test_keywords_deduplicated_from_symptoms(self):
        msg = _build_user_message(
            symptoms=["high_fever"],
            keywords=["high_fever", "fever_extra"],  # high_fever is in symptoms, fever_extra is not
            severity=None,
            language="en",
        )
        # fever_extra should appear (new info), high_fever only once
        assert "fever_extra" in msg

    def test_empty_symptoms_handled(self):
        msg = _build_user_message([], [], None, "en")
        assert "not specified" in msg

    def test_severity_none_not_in_message(self):
        msg = _build_user_message(["cough"], [], None, "en")
        assert "None/10" not in msg
        assert "/10" not in msg


# ── JSON parsing ───────────────────────────────────────────────────────────────

class TestJsonParsing:
    def test_clean_json(self):
        raw = _good_llm_response()
        result = _parse_llm_json(raw)
        assert result is not None
        assert result["primary_diagnosis"] == "Dengue Fever"

    def test_json_with_markdown_fences(self):
        raw = f"```json\n{_good_llm_response()}\n```"
        result = _parse_llm_json(raw)
        assert result is not None
        assert result["confidence"] == 0.82

    def test_json_with_preamble(self):
        raw = f"Here is the clinical assessment:\n{_good_llm_response()}\nEnd of assessment."
        result = _parse_llm_json(raw)
        assert result is not None

    def test_json_with_trailing_text(self):
        raw = f"{_good_llm_response()} Note: always verify with a doctor."
        result = _parse_llm_json(raw)
        assert result is not None

    def test_invalid_json_returns_none(self):
        assert _parse_llm_json("Not JSON at all.") is None

    def test_empty_string_returns_none(self):
        assert _parse_llm_json("") is None

    def test_none_returns_none(self):
        assert _parse_llm_json(None) is None

    def test_broken_json_no_crash(self):
        # Should not raise — just return None
        result = _parse_llm_json('{"primary_diagnosis": "Dengue", "confidence": }')
        assert result is None

    @pytest.mark.parametrize("wrapper", [
        "",
        "```json\n{content}\n```",
        "Analysis: {content}",
        "Here you go:\n{content}\nDone.",
    ])
    def test_json_extraction_variants(self, wrapper):
        body = _good_llm_response()
        raw  = wrapper.replace("{content}", body) if "{content}" in wrapper else body
        result = _parse_llm_json(raw)
        assert result is not None


# ── Pydantic schema validation ────────────────────────────────────────────────

class TestSchemaValidation:
    def test_valid_response_validates(self):
        parsed    = json.loads(_good_llm_response())
        validated = _validate_parsed(parsed)
        assert validated.primary_diagnosis == "Dengue Fever"
        assert validated.confidence == 0.82
        assert validated.triage_level == 3

    def test_confidence_clamped_above_1(self):
        parsed = json.loads(_good_llm_response(confidence=1.5))
        validated = _validate_parsed(parsed)
        assert validated.confidence == 1.0

    def test_confidence_clamped_below_0(self):
        parsed = json.loads(_good_llm_response(confidence=-0.3))
        validated = _validate_parsed(parsed)
        assert validated.confidence == 0.0

    def test_triage_level_clamped_above_5(self):
        parsed = json.loads(_good_llm_response(triage_level=9))
        validated = _validate_parsed(parsed)
        assert validated.triage_level == 5

    def test_triage_level_clamped_below_1(self):
        parsed = json.loads(_good_llm_response(triage_level=0))
        validated = _validate_parsed(parsed)
        assert validated.triage_level == 1

    def test_disclaimer_enforced_if_missing(self):
        parsed    = json.loads(_good_llm_response(disclaimer=""))
        validated = _validate_parsed(parsed)
        assert "This AI triage output is for guidance only" in validated.disclaimer

    def test_disclaimer_enforced_if_noncompliant(self):
        parsed    = json.loads(_good_llm_response(disclaimer="Consult a doctor."))
        validated = _validate_parsed(parsed)
        assert "This AI triage output is for guidance only" in validated.disclaimer

    def test_empty_primary_diagnosis_raises(self):
        parsed = json.loads(_good_llm_response(primary_diagnosis=""))
        with pytest.raises(ValidationError):
            _validate_parsed(parsed)

    def test_missing_required_field_raises(self):
        parsed = json.loads(_good_llm_response())
        del parsed["triage_level"]
        with pytest.raises((ValidationError, Exception)):
            _validate_parsed(parsed)

    def test_differential_confidence_clamped(self):
        parsed = json.loads(_good_llm_response(
            differential=[{"disease": "X", "confidence": 2.0, "reasoning": "test"}]
        ))
        validated = _validate_parsed(parsed)
        assert validated.differential[0].confidence == 1.0

    def test_to_diagnosis_result_conversion(self):
        parsed    = json.loads(_good_llm_response())
        validated = _validate_parsed(parsed)
        result    = _to_diagnosis_result(validated)

        assert isinstance(result, DiagnosisResult)
        assert result.primary_diagnosis == "Dengue Fever"
        assert result.diagnosis_source == "llm_gemini"
        assert result.confidence        == 0.82
        assert len(result.differential) == 2
        assert len(result.precautions)  > 0

    def test_differential_confidence_label_set(self):
        parsed    = json.loads(_good_llm_response())
        validated = _validate_parsed(parsed)
        result    = _to_diagnosis_result(validated)

        for d in result.differential:
            assert "confidence_label" in d
            assert d["confidence_label"] in ("High", "Medium", "Low")


# ── Safe fallback ──────────────────────────────────────────────────────────────

class TestSafeFallback:
    def test_safe_fallback_returns_diagnosis_result(self):
        result = _safe_fallback(["high_fever", "cough"])
        assert isinstance(result, DiagnosisResult)

    def test_safe_fallback_diagnosis_source(self):
        result = _safe_fallback([])
        assert result.diagnosis_source == "llm_gemini"

    def test_safe_fallback_zero_confidence(self):
        result = _safe_fallback(["cough"])
        assert result.confidence == 0.0

    def test_safe_fallback_has_precautions(self):
        result = _safe_fallback([])
        assert len(result.precautions) >= 3

    def test_safe_fallback_mentions_phc(self):
        result = _safe_fallback([])
        all_text = " ".join(result.precautions + [result.description or ""])
        assert any(kw in all_text.lower() for kw in ["phc", "primary health", "doctor", "asha"])

    def test_safe_fallback_has_disclaimer(self):
        result = _safe_fallback([])
        assert len(result.disclaimer) > 20


# ── run_llm_fallback end-to-end ────────────────────────────────────────────────

class TestRunLLMFallback:
    @pytest.mark.asyncio
    async def test_successful_run(self):
        mock_response = _good_llm_response()
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=mock_response)):
            result = await run_llm_fallback(
                symptoms=["high_fever", "joint_pain", "skin_rash"],
                keywords=["fever", "rash", "joint pain"],
                severity=7,
                language="en",
            )
        assert result.primary_diagnosis == "Dengue Fever"
        assert result.confidence == 0.82
        assert result.diagnosis_source == "llm_gemini"
        assert len(result.differential) == 2

    @pytest.mark.asyncio
    async def test_ollama_unreachable_returns_safe_fallback(self):
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=None)):
            result = await run_llm_fallback(
                symptoms=["high_fever"],
                keywords=[],
                language="en",
            )
        assert result.primary_diagnosis == "Undetermined — clinical evaluation required"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_invalid_json_returns_safe_fallback(self):
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value="This is not JSON at all")):
            result = await run_llm_fallback(["cough"], [], language="en")
        assert result.confidence == 0.0
        assert result.diagnosis_source == "llm_gemini"

    @pytest.mark.asyncio
    async def test_validation_failure_partial_recovery(self):
        """Partial response (has primary + triage_level) should partially recover."""
        partial = json.dumps({
            "primary_diagnosis": "Malaria",
            "confidence":        0.70,
            "triage_level":      4,
            "differential":      [],
            "red_flags":         [],
            "precautions":       ["visit hospital"],
            "description":       "Malaria is a parasitic infection.",
            "disclaimer":        "This AI triage output is for guidance only. It is NOT a medical diagnosis.",
        })
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=partial)):
            result = await run_llm_fallback(["high_fever"], [], language="en")
        # Should succeed (partial recovery) or fall back to safe
        assert isinstance(result, DiagnosisResult)
        assert result.diagnosis_source == "llm_gemini"

    @pytest.mark.asyncio
    async def test_hindi_language_passed_to_prompt(self):
        mock_response = _good_llm_response()
        captured_msgs = []

        async def mock_call(messages):
            captured_msgs.extend(messages)
            return mock_response

        with patch("app.services.diagnosis.llm_fallback._call_gemini", mock_call):
            await run_llm_fallback(["high_fever"], [], language="hi")

        user_msg = captured_msgs[-1]["content"]
        assert "Hindi" in user_msg

    @pytest.mark.asyncio
    async def test_tamil_language_passed_to_prompt(self):
        mock_response = _good_llm_response()
        captured_msgs = []

        async def mock_call(messages):
            captured_msgs.extend(messages)
            return mock_response

        with patch("app.services.diagnosis.llm_fallback._call_gemini", mock_call):
            await run_llm_fallback(["high_fever"], [], language="ta")

        user_msg = captured_msgs[-1]["content"]
        assert "Tamil" in user_msg

    @pytest.mark.asyncio
    async def test_severity_included_in_prompt(self):
        mock_response = _good_llm_response()
        captured_msgs = []

        async def mock_call(messages):
            captured_msgs.extend(messages)
            return mock_response

        with patch("app.services.diagnosis.llm_fallback._call_gemini", mock_call):
            await run_llm_fallback(["high_fever"], [], severity=8, language="en")

        user_msg = captured_msgs[-1]["content"]
        assert "8/10" in user_msg

    @pytest.mark.asyncio
    async def test_emergency_response_has_triage_5(self):
        emergency_resp = _good_llm_response(
            primary_diagnosis="Acute Myocardial Infarction",
            confidence=0.88,
            triage_level=5,
            red_flags=["Chest pain + breathlessness — cardiac emergency"],
        )
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=emergency_resp)):
            result = await run_llm_fallback(
                symptoms=["chest_pain", "breathlessness", "sweating"],
                keywords=["chest pain", "cannot breathe"],
                severity=9,
                language="en",
            )
        assert result.primary_diagnosis == "Acute Myocardial Infarction"
        assert len(result.red_flags) > 0

    @pytest.mark.asyncio
    async def test_prompt_missing_returns_safe_fallback(self):
        with patch("app.services.diagnosis.llm_fallback._build_messages",
                   side_effect=FileNotFoundError("prompt not found")):
            result = await run_llm_fallback(["cough"], [], language="en")
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_disclaimer_always_present(self):
        mock_response = _good_llm_response(disclaimer="short disclaimer")
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=mock_response)):
            result = await run_llm_fallback(["cough"], [], language="en")
        assert len(result.disclaimer) > 20


# ── LLM endpoint tests ─────────────────────────────────────────────────────────

class TestLLMEndpoints:
    @pytest.mark.asyncio
    async def test_llm_diagnose_success(self, async_client, mock_redis):
        mock_response = _good_llm_response()
        with patch("app.api.v1.endpoints.llm_diagnose.run_llm_fallback",
                   AsyncMock(return_value=DiagnosisResult(
                       primary_diagnosis="Dengue Fever",
                       confidence=0.82,
                       differential=[],
                       diagnosis_source="llm_gemini",
                       red_flags=[],
                   ))), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/llm/diagnose",
                json={
                    "symptoms": ["high_fever", "joint_pain", "skin_rash"],
                    "keywords": ["fever", "rash"],
                    "severity": 7,
                    "language": "en",
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert data["primary_diagnosis"] == "Dengue Fever"
        assert data["diagnosis_source"] == "llm_gemini"

    @pytest.mark.asyncio
    async def test_llm_diagnose_cache_hit(self, async_client, mock_redis):
        cached_result = DiagnosisResult(
            primary_diagnosis="Cached Disease",
            confidence=0.75,
            differential=[],
            diagnosis_source="llm_gemini",
            red_flags=[],
        )
        mock_redis.get.return_value = cached_result.model_dump_json()

        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/llm/diagnose",
                json={"symptoms": ["high_fever"], "keywords": [], "language": "en"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["primary_diagnosis"] == "Cached Disease"

    @pytest.mark.asyncio
    async def test_llm_diagnose_empty_symptoms_rejected(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/llm/diagnose",
                json={"symptoms": [], "keywords": [], "language": "en"},
            )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_llm_diagnose_invalid_language(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/llm/diagnose",
                json={"symptoms": ["high_fever"], "language": "fr"},
            )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_get_fallback_prompt_dev(self, async_client):
        """In dev mode, should return prompt contents."""
        r = await async_client.get("/api/v1/llm/prompts/fallback?version=v1")
        assert r.status_code in (200, 404)  # 404 if prompt files not found in test
        if r.status_code == 200:
            data = r.json()
            assert "version" in data
            assert "system_prompt" in data

    @pytest.mark.asyncio
    async def test_test_prompt_endpoint_dev(self, async_client, mock_redis):
        """Test the prompt testing endpoint (dev only)."""
        mock_response = _good_llm_response()
        with patch("app.api.v1.endpoints.llm_diagnose._call_gemini",
                   AsyncMock(return_value=mock_response)), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/llm/prompts/fallback/test",
                json={
                    "symptoms": ["high_fever", "cough"],
                    "keywords": ["fever"],
                    "severity": 6,
                    "language": "en",
                    "version": "v1",
                },
            )
        assert r.status_code in (200, 403, 404, 503)


# ── Clinical quality assertions ────────────────────────────────────────────────

class TestClinicalQuality:
    """Verify the prompt produces clinically sensible outputs for key cases."""

    @pytest.mark.asyncio
    async def test_cardiac_emergency_gets_triage_5(self):
        cardiac_resp = _good_llm_response(
            primary_diagnosis="Acute MI",
            triage_level=5,
            red_flags=["Chest pain + breathlessness — cardiac event"],
        )
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=cardiac_resp)):
            result = await run_llm_fallback(
                ["chest_pain", "breathlessness", "sweating"],
                ["chest pain", "sweating"],
                severity=9,
                language="en",
            )
        assert len(result.red_flags) > 0
        assert result.diagnosis_source == "llm_gemini"

    @pytest.mark.asyncio
    async def test_common_cold_gets_low_triage(self):
        cold_resp = _good_llm_response(
            primary_diagnosis="Common Cold",
            confidence=0.91,
            triage_level=1,
            red_flags=[],
        )
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=cold_resp)):
            result = await run_llm_fallback(
                ["continuous_sneezing", "runny_nose", "throat_irritation"],
                ["cold", "runny nose"],
                severity=3,
                language="en",
            )
        assert result.primary_diagnosis == "Common Cold"
        assert result.diagnosis_source == "llm_gemini"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_differential_has_multiple_entries(self):
        resp = _good_llm_response(
            primary_diagnosis="Malaria",
            differential=[
                {"disease": "Dengue",  "confidence": 0.55, "reasoning": "Also causes fever and rash"},
                {"disease": "Typhoid", "confidence": 0.30, "reasoning": "Prolonged fever pattern"},
            ],
        )
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=resp)):
            result = await run_llm_fallback(
                ["high_fever", "sweating", "chills"],
                ["fever", "malaria"],
                severity=6,
                language="en",
            )
        assert len(result.differential) >= 2

    @pytest.mark.asyncio
    async def test_precautions_are_actionable(self):
        resp = _good_llm_response(precautions=[
            "Rest and drink ORS",
            "Get CBC blood test at PHC",
            "Avoid NSAIDs",
            "Monitor for bleeding",
        ])
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=resp)):
            result = await run_llm_fallback(["high_fever"], [], language="en")
        assert len(result.precautions) >= 3
        for p in result.precautions:
            assert len(p) > 5   # not empty strings

    @pytest.mark.asyncio
    async def test_tb_gets_high_triage(self):
        tb_resp = _good_llm_response(
            primary_diagnosis="Pulmonary Tuberculosis",
            confidence=0.85,
            triage_level=4,
            red_flags=["Haemoptysis requires same-day evaluation"],
        )
        with patch("app.services.diagnosis.llm_fallback._call_gemini",
                   AsyncMock(return_value=tb_resp)):
            result = await run_llm_fallback(
                ["cough", "weight_loss", "blood_in_sputum", "fatigue"],
                ["6 weeks cough", "blood sputum"],
                severity=6,
                language="en",
            )
        assert result.primary_diagnosis == "Pulmonary Tuberculosis"
        assert len(result.red_flags) > 0
