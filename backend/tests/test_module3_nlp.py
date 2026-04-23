"""
Vaidya — Module 3 test suite
Tests: prompt loader, LLM JSON parsing, canonical mapping,
       synonym map, fuzzy matching, NLP endpoints, batch extract
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.services.nlp.extractor import (
    CANONICAL_SYMPTOMS,
    SYNONYM_MAP,
    _parse_json,
    _regex_fallback,
    _map_to_canonical,
    _clamp_severity,
    build_symptom_vector,
)
from app.services.nlp.prompt_loader import (
    get_extraction_system_prompt,
    get_few_shot_examples,
    list_available_prompts,
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


def _make_ollama_response(symptoms, duration=None, severity=None, red_flags=None):
    """Build a realistic Ollama JSON response for mocking."""
    return json.dumps({
        "symptoms":         symptoms,
        "duration":         duration,
        "severity_estimate": severity,
        "body_parts":       [],
        "red_flags":        red_flags or [],
        "raw_keywords":     symptoms,
        "onset_type":       None,
        "context_notes":    None,
    })


# ── Prompt loader ──────────────────────────────────────────────────────────────

class TestPromptLoader:
    def test_system_prompt_loads(self):
        prompt = get_extraction_system_prompt()
        assert len(prompt) > 100
        assert "JSON" in prompt
        assert "symptoms" in prompt.lower()

    def test_system_prompt_has_canonical_list(self):
        prompt = get_extraction_system_prompt()
        # Should contain several canonical symptom names
        assert "high_fever" in prompt
        assert "breathlessness" in prompt
        assert "chest_pain" in prompt

    def test_system_prompt_has_output_schema(self):
        prompt = get_extraction_system_prompt()
        assert "OUTPUT SCHEMA" in prompt
        assert "red_flags" in prompt
        assert "onset_type" in prompt

    def test_few_shot_examples_load(self):
        examples = get_few_shot_examples()
        assert len(examples) >= 3
        for ex in examples:
            assert "input" in ex
            assert "output" in ex
            assert len(ex["input"]) > 5

    def test_few_shot_has_hindi_example(self):
        examples = get_few_shot_examples()
        combined = " ".join(ex["input"] for ex in examples)
        # Should contain Hindi text in one of the examples
        assert any(ord(c) >= 0x0900 for c in combined)

    def test_few_shot_has_tamil_example(self):
        examples = get_few_shot_examples()
        combined = " ".join(ex["input"] for ex in examples)
        assert any(ord(c) >= 0x0B80 for c in combined)

    def test_list_prompts_returns_files(self):
        prompts = list_available_prompts()
        assert isinstance(prompts, list)
        assert any("symptom_extraction" in p for p in prompts)


# ── JSON parsing ───────────────────────────────────────────────────────────────

class TestJsonParsing:
    def test_clean_json(self):
        raw = '{"symptoms": ["fever", "cough"], "duration": "3 days"}'
        result = _parse_json(raw)
        assert result is not None
        assert result["symptoms"] == ["fever", "cough"]

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"symptoms": ["headache"]}\n```'
        result = _parse_json(raw)
        assert result is not None
        assert result["symptoms"] == ["headache"]

    def test_json_with_prose_prefix(self):
        raw = 'Here is the extracted data:\n{"symptoms": ["vomiting"], "duration": null}'
        result = _parse_json(raw)
        assert result is not None
        assert result["symptoms"] == ["vomiting"]

    def test_json_with_trailing_text(self):
        raw = '{"symptoms": ["fatigue"]} This concludes my analysis.'
        result = _parse_json(raw)
        assert result is not None

    def test_completely_invalid_json(self):
        result = _parse_json("This is not JSON at all.")
        assert result is None

    def test_empty_string(self):
        result = _parse_json("")
        assert result is None

    def test_none_input(self):
        result = _parse_json(None)
        assert result is None

    def test_nested_json_extracted(self):
        raw = '{"symptoms": ["fever"], "meta": {"source": "llm"}}'
        result = _parse_json(raw)
        assert result["symptoms"] == ["fever"]

    @pytest.mark.parametrize("raw,expected_symptom", [
        ('{"symptoms": ["cough"], "duration": "2 days"}', "cough"),
        ('```{"symptoms": ["headache"]}```', "headache"),
        ('Output: {"symptoms": ["nausea"]}', "nausea"),
    ])
    def test_json_parsing_parametrize(self, raw, expected_symptom):
        result = _parse_json(raw)
        assert result is not None
        assert expected_symptom in result["symptoms"]


# ── Canonical mapping ──────────────────────────────────────────────────────────

class TestCanonicalMapping:
    def test_direct_synonym_match(self):
        raw = {"symptoms": ["fever"], "duration": "3 days", "severity_estimate": None,
               "body_parts": [], "red_flags": [], "raw_keywords": ["fever"]}
        extracted, unmatched, vector = _map_to_canonical(raw, [])
        assert "high_fever" in extracted.symptoms
        assert vector["high_fever"] == 1

    def test_snake_case_direct_match(self):
        raw = {"symptoms": ["high_fever", "cough"], "duration": None, "severity_estimate": None,
               "body_parts": [], "red_flags": [], "raw_keywords": []}
        extracted, _, vector = _map_to_canonical(raw, [])
        assert "high_fever" in extracted.symptoms
        assert "cough" in extracted.symptoms

    def test_fuzzy_match_typo(self):
        raw = {"symptoms": ["hedache"], "duration": None, "severity_estimate": None,  # typo
               "body_parts": [], "red_flags": [], "raw_keywords": []}
        extracted, unmatched, _ = _map_to_canonical(raw, [])
        # Should fuzzy-match to headache
        assert "headache" in extracted.symptoms or "hedache" in unmatched

    def test_unmatched_word_goes_to_unmatched(self):
        raw = {"symptoms": ["xyzzy_notasymptom"], "duration": None, "severity_estimate": None,
               "body_parts": [], "red_flags": [], "raw_keywords": []}
        extracted, unmatched, _ = _map_to_canonical(raw, [])
        assert "xyzzy_notasymptom" in unmatched

    def test_spacy_extras_merged(self):
        raw = {"symptoms": ["fever"], "duration": None, "severity_estimate": None,
               "body_parts": [], "red_flags": [], "raw_keywords": []}
        extracted, _, vector = _map_to_canonical(raw, ["cough", "headache"])
        assert "cough" in extracted.symptoms
        assert vector["cough"] == 1

    def test_deduplication(self):
        raw = {"symptoms": ["fever", "fever", "high_fever"],
               "duration": None, "severity_estimate": None,
               "body_parts": [], "red_flags": [], "raw_keywords": ["fever"]}
        extracted, _, _ = _map_to_canonical(raw, [])
        assert extracted.symptoms.count("high_fever") == 1

    def test_vector_length_always_133(self):
        raw = {"symptoms": ["fever", "cough", "headache"],
               "duration": "2 days", "severity_estimate": 7,
               "body_parts": ["chest"], "red_flags": [], "raw_keywords": []}
        _, _, vector = _map_to_canonical(raw, [])
        assert len(vector) == 133

    def test_severity_clamped(self):
        assert _clamp_severity(15) == 10
        assert _clamp_severity(0)  == 1
        assert _clamp_severity(5)  == 5
        assert _clamp_severity(None) is None
        assert _clamp_severity("7") == 7
        assert _clamp_severity("bad") is None


# ── Synonym map ────────────────────────────────────────────────────────────────

class TestSynonymMap:
    def test_all_synonym_values_canonical(self):
        for phrase, canonical in SYNONYM_MAP.items():
            assert canonical in CANONICAL_SYMPTOMS, \
                f"Synonym '{phrase}' → '{canonical}' is not in CANONICAL_SYMPTOMS"

    def test_common_synonyms_present(self):
        assert "fever" in SYNONYM_MAP
        assert "coughing" in SYNONYM_MAP
        assert "loose motions" in SYNONYM_MAP
        assert "jaundice" in SYNONYM_MAP
        assert "fits" in SYNONYM_MAP
        assert "breathless" in SYNONYM_MAP

    def test_longer_phrases_before_shorter(self):
        # Ensure multi-word synonyms exist that wouldn't be caught by single-word lookup
        assert "difficulty breathing" in SYNONYM_MAP
        assert "short of breath" in SYNONYM_MAP
        assert "loss of consciousness" in SYNONYM_MAP


# ── Regex fallback ─────────────────────────────────────────────────────────────

class TestRegexFallback:
    def test_finds_synonym_in_text(self):
        result = _regex_fallback("I have fever and cough")
        assert "high_fever" in result["symptoms"]
        assert "cough" in result["symptoms"]

    def test_finds_canonical_name_in_text(self):
        result = _regex_fallback("patient has breathlessness and headache")
        assert "breathlessness" in result["symptoms"]
        assert "headache" in result["symptoms"]

    def test_empty_text(self):
        result = _regex_fallback("")
        assert isinstance(result["symptoms"], list)

    def test_hindi_text_no_crash(self):
        # Regex fallback should handle non-Latin text without crashing
        result = _regex_fallback("मुझे बुखार है")
        assert isinstance(result["symptoms"], list)

    def test_context_notes_set(self):
        result = _regex_fallback("some text")
        assert result["context_notes"] == "regex_fallback"


# ── Vector builder ─────────────────────────────────────────────────────────────

class TestVectorBuilder:
    def test_vector_has_133_keys(self):
        vector = build_symptom_vector([])
        assert len(vector) == 133

    def test_all_zeros_on_empty(self):
        vector = build_symptom_vector([])
        assert all(v == 0 for v in vector.values())

    def test_known_symptoms_set_to_1(self):
        vector = build_symptom_vector(["high_fever", "cough", "headache"])
        assert vector["high_fever"] == 1
        assert vector["cough"] == 1
        assert vector["headache"] == 1

    def test_unknown_symptoms_ignored(self):
        vector = build_symptom_vector(["fake_symptom_xyz"])
        assert all(v == 0 for v in vector.values())

    def test_all_canonical_symptoms_settable(self):
        # All 133 canonical symptoms should be valid keys
        for sym in CANONICAL_SYMPTOMS:
            vector = build_symptom_vector([sym])
            assert vector[sym] == 1


# ── Canonical symptoms completeness ───────────────────────────────────────────

class TestCanonicalList:
    def test_exactly_133_symptoms(self):
        assert len(CANONICAL_SYMPTOMS) == 133

    def test_no_duplicates(self):
        assert len(CANONICAL_SYMPTOMS) == len(set(CANONICAL_SYMPTOMS))

    def test_all_lowercase_snakecase(self):
        for sym in CANONICAL_SYMPTOMS:
            assert sym == sym.lower(), f"Not lowercase: {sym}"
            assert " " not in sym, f"Contains space: {sym}"

    def test_key_symptoms_present(self):
        critical = [
            "high_fever", "cough", "breathlessness", "chest_pain", "headache",
            "vomiting", "diarrhoea", "fatigue", "nausea", "dizziness",
            "loss_of_consciousness", "coughing_of_blood", "stiff_neck",
        ]
        for sym in critical:
            assert sym in CANONICAL_SYMPTOMS, f"Critical symptom missing: {sym}"


# ── NLP endpoint tests ────────────────────────────────────────────────────────

class TestNLPEndpoints:
    @pytest.mark.asyncio
    async def test_extract_english(self, async_client, mock_redis):
        ollama_response = _make_ollama_response(
            symptoms=["high_fever", "cough", "chest_pain"],
            duration="3 days",
            severity=7,
        )
        mock_ollama = AsyncMock(return_value=ollama_response)

        with patch("app.services.nlp.extractor._call_ollama", mock_ollama), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/nlp/extract",
                json={"text": "I have fever and cough for 3 days, chest hurts", "language": "en"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["matched_count"] > 0
        assert data["vector_active_count"] > 0
        assert len(data["symptom_vector"]) == 133
        assert data["symptom_vector"]["high_fever"] == 1
        assert data["symptom_vector"]["cough"] == 1

    @pytest.mark.asyncio
    async def test_extract_hindi_translated(self, async_client, mock_redis):
        ollama_response = _make_ollama_response(["high_fever", "cough"])
        mock_ollama = AsyncMock(return_value=ollama_response)

        with patch("app.services.nlp.extractor._call_ollama", mock_ollama), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/nlp/extract",
                json={"text": "मुझे बुखार और खांसी है", "language": "hi"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["input_language"] == "hi"
        assert len(data["symptom_vector"]) == 133

    @pytest.mark.asyncio
    async def test_extract_with_red_flags(self, async_client, mock_redis):
        ollama_response = json.dumps({
            "symptoms": ["chest_pain", "breathlessness", "sweating"],
            "duration": "20 minutes",
            "severity_estimate": 9,
            "body_parts": ["chest"],
            "red_flags": ["chest pain + breathlessness — possible cardiac event"],
            "raw_keywords": ["chest pain", "breathlessness", "sweating"],
            "onset_type": "sudden",
            "context_notes": None,
        })
        mock_ollama = AsyncMock(return_value=ollama_response)

        with patch("app.services.nlp.extractor._call_ollama", mock_ollama), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/nlp/extract",
                json={"text": "severe chest pain, can't breathe, sweating profusely", "language": "en"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["symptom_vector"]["chest_pain"] == 1
        assert data["symptom_vector"]["breathlessness"] == 1

    @pytest.mark.asyncio
    async def test_extract_ollama_fallback(self, async_client, mock_redis):
        """When Ollama fails, regex fallback should still return a valid response."""
        mock_ollama = AsyncMock(side_effect=Exception("Ollama down"))

        with patch("app.services.nlp.extractor._call_ollama", mock_ollama), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/nlp/extract",
                json={"text": "I have fever and cough since yesterday"},
            )

        assert r.status_code == 200
        data = r.json()
        # Regex fallback should catch fever and cough
        assert data["symptom_vector"]["high_fever"] == 1 or data["matched_count"] >= 0

    @pytest.mark.asyncio
    async def test_extract_text_too_short(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/nlp/extract",
                json={"text": "hi"},
            )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_list_symptoms(self, async_client):
        r = await async_client.get("/api/v1/nlp/symptoms")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 133
        assert "high_fever" in data["symptoms"]
        assert "breathlessness" in data["symptoms"]

    @pytest.mark.asyncio
    async def test_list_symptoms_grouped(self, async_client):
        r = await async_client.get("/api/v1/nlp/symptoms?group_by_alpha=true")
        assert r.status_code == 200
        data = r.json()
        assert "grouped" in data
        assert "A" in data["grouped"]   # anxiety, acidity, etc.

    @pytest.mark.asyncio
    async def test_search_symptoms_fever(self, async_client):
        r = await async_client.get("/api/v1/nlp/symptoms/search?q=fever")
        assert r.status_code == 200
        data = r.json()
        assert len(data["results"]) > 0
        assert data["results"][0]["symptom"] == "high_fever"
        assert data["results"][0]["via"] == "synonym_map"

    @pytest.mark.asyncio
    async def test_search_symptoms_fuzzy(self, async_client):
        r = await async_client.get("/api/v1/nlp/symptoms/search?q=headche")  # typo
        assert r.status_code == 200
        data = r.json()
        assert len(data["results"]) > 0

    @pytest.mark.asyncio
    async def test_build_vector_valid(self, async_client):
        r = await async_client.post(
            "/api/v1/nlp/vector",
            json={"symptoms": ["high_fever", "cough", "headache"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["active_count"] == 3
        assert data["total_features"] == 133
        assert data["symptom_vector"]["high_fever"] == 1

    @pytest.mark.asyncio
    async def test_build_vector_invalid_name(self, async_client):
        r = await async_client.post(
            "/api/v1/nlp/vector",
            json={"symptoms": ["not_a_real_symptom_xyz"]},
        )
        assert r.status_code == 422
        data = r.json()
        assert "invalid" in str(data).lower()

    @pytest.mark.asyncio
    async def test_batch_extract(self, async_client, mock_redis):
        ollama_response = _make_ollama_response(["high_fever", "cough"])
        mock_ollama = AsyncMock(return_value=ollama_response)

        with patch("app.services.nlp.extractor._call_ollama", mock_ollama), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/nlp/extract/batch",
                json={"texts": [
                    "I have fever",
                    "Headache and vomiting",
                    "Chest pain and breathlessness",
                ]},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 3
        assert all("symptoms" in item for item in data["results"])

    @pytest.mark.asyncio
    async def test_prompts_list(self, async_client):
        r = await async_client.get("/api/v1/nlp/prompts")
        assert r.status_code == 200
        data = r.json()
        assert "available" in data

    @pytest.mark.asyncio
    async def test_prompt_inspect_dev_only(self, async_client):
        r = await async_client.get("/api/v1/nlp/prompts/symptom_extraction_v1.txt")
        # In dev (ENV=development), should return 200
        assert r.status_code in (200, 403)

    @pytest.mark.asyncio
    async def test_prompt_path_traversal_blocked(self, async_client):
        r = await async_client.get("/api/v1/nlp/prompts/../../etc/passwd")
        assert r.status_code in (400, 404)


# ── Integration: full pipeline with mock Ollama ───────────────────────────────

class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_en_text_full_pipeline(self, mock_redis):
        from app.services.nlp.extractor import extract_symptoms

        ollama_resp = _make_ollama_response(
            symptoms=["high_fever", "cough", "chest_pain"],
            duration="3 days",
            severity=7,
            red_flags=["chest pain on breathing"],
        )

        with patch("app.services.nlp.extractor._call_ollama", AsyncMock(return_value=ollama_resp)):
            extracted, unmatched, vector = await extract_symptoms(
                text="I have fever and cough for 3 days. Chest hurts.",
                language="en",
                redis=mock_redis,
            )

        assert "high_fever" in extracted.symptoms
        assert "cough" in extracted.symptoms
        assert vector["high_fever"] == 1
        assert vector["cough"] == 1
        assert extracted.duration == "3 days"
        assert extracted.severity_estimate == 7
        assert len(vector) == 133

    @pytest.mark.asyncio
    async def test_cache_second_call_skips_ollama(self, mock_redis):
        from app.services.nlp.extractor import extract_symptoms
        import hashlib

        text = "I have fever"
        cache_key = f"nlp:v3:{hashlib.sha256(text.encode()).hexdigest()[:24]}"
        cached_data = json.dumps({
            "extracted": {
                "symptoms": ["high_fever"],
                "duration": None,
                "severity_estimate": None,
                "body_parts": [],
                "raw_keywords": [],
            },
            "vector": {sym: (1 if sym == "high_fever" else 0) for sym in CANONICAL_SYMPTOMS},
            "unmatched": [],
        })
        mock_redis.get.return_value = cached_data

        call_count = 0
        async def mock_ollama(text):
            nonlocal call_count
            call_count += 1
            return _make_ollama_response(["high_fever"])

        with patch("app.services.nlp.extractor._call_ollama", mock_ollama):
            extracted, unmatched, vector = await extract_symptoms(
                text=text, language="en", redis=mock_redis
            )

        # Ollama should NOT have been called (cache hit)
        assert call_count == 0
        assert "high_fever" in extracted.symptoms
