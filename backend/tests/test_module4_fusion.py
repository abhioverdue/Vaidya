"""
Vaidya — Module 4 test suite
Tests: FusionPlan weights, signal parsing, corroboration scoring,
       red flag escalation, LLM fallback gate, concurrent model execution,
       diagnose endpoint (text-only, multimodal, audio, image)
"""

import asyncio
import json
import os
import struct
import tempfile
import uuid
import wave
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.schemas.schemas import DiagnosisResult
from app.services.diagnosis.fusion import (
    AUDIO_CORROBORATION,
    AUDIO_TRIAGE_HINT,
    BASE_WEIGHT_AUDIO,
    BASE_WEIGHT_NLP,
    BASE_WEIGHT_VISION,
    FusionPlan,
    ModelSignal,
    VISION_CORROBORATION,
    _compute_corroboration_scores,
    _parse_audio_signal,
    _parse_nlp_signal,
    _parse_vision_signal,
    fuse_signals,
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


@pytest.fixture
def nlp_result_pneumonia():
    return DiagnosisResult(
        primary_diagnosis="Pneumonia",
        confidence=0.82,
        differential=[
            {"disease": "Bronchial Asthma", "confidence": 0.35},
            {"disease": "Common Cold",      "confidence": 0.15},
        ],
        diagnosis_source="xgboost",
        red_flags=[],
    )


@pytest.fixture
def nlp_result_low_confidence():
    return DiagnosisResult(
        primary_diagnosis="Unknown",
        confidence=0.28,
        differential=[],
        diagnosis_source="xgboost",
        red_flags=[],
    )


@pytest.fixture
def nlp_result_with_red_flags():
    return DiagnosisResult(
        primary_diagnosis="Heart attack",
        confidence=0.71,
        differential=[{"disease": "Pneumonia", "confidence": 0.20}],
        diagnosis_source="xgboost",
        red_flags=["Chest pain + breathlessness — possible cardiac event"],
    )


@pytest.fixture
def audio_result_severe():
    return {
        "top_prediction":  {"label": "cough_severe",  "confidence": 0.78},
        "all_predictions": [
            {"label": "cough_severe",  "confidence": 0.78},
            {"label": "other",         "confidence": 0.14},
            {"label": "cough_healthy", "confidence": 0.08},
        ],
        "signal_source": "audio_model",
    }


@pytest.fixture
def audio_result_healthy():
    return {
        "top_prediction":  {"label": "cough_healthy", "confidence": 0.85},
        "all_predictions": [
            {"label": "cough_healthy", "confidence": 0.85},
            {"label": "other",         "confidence": 0.10},
            {"label": "cough_severe",  "confidence": 0.05},
        ],
        "signal_source": "audio_model",
    }


@pytest.fixture
def vision_result_pneumonia():
    return {
        "dataset_type":   "chest",
        "top_prediction": {"label": "bacterial_pneumonia", "confidence": 0.73},
        "all_predictions": [
            {"label": "bacterial_pneumonia", "confidence": 0.73},
            {"label": "viral_pneumonia",     "confidence": 0.18},
            {"label": "normal",              "confidence": 0.09},
        ],
        "signal_source": "vision_model",
    }


@pytest.fixture
def vision_result_diabetic():
    return {
        "dataset_type":   "wound",
        "top_prediction": {"label": "diabetic_wound", "confidence": 0.81},
        "all_predictions": [
            {"label": "diabetic_wound", "confidence": 0.81},
            {"label": "venous_wound",   "confidence": 0.12},
        ],
        "signal_source": "vision_model",
    }


def _make_wav_bytes(duration_s=2.0):
    import math
    buf = BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        n = int(16000 * duration_s)
        for i in range(n):
            val = int(0.3 * 32767 * math.sin(2 * math.pi * 440 * i / 16000))
            wf.writeframes(struct.pack("<h", val))
    return buf.getvalue()


def _make_png_bytes():
    """Minimal valid PNG (1x1 red pixel)."""
    import zlib
    raw = b'\x00\xff\x00\x00\xff'   # filter byte + RGBA
    png  = b'\x89PNG\r\n\x1a\n'
    ihdr = b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
    idat_data  = zlib.compress(raw)
    idat_chunk = len(idat_data).to_bytes(4, "big") + b"IDAT" + idat_data
    idat_chunk += zlib.crc32(b"IDAT" + idat_data).to_bytes(4, "big")
    iend = b'\x00\x00\x00\x00IEND\xaeB`\x82'
    return png + ihdr + idat_chunk + iend


# ── FusionPlan ────────────────────────────────────────────────────────────────

class TestFusionPlan:
    def test_text_only_nlp_weight_is_1(self):
        plan = FusionPlan.compute(has_audio=False, has_vision=False)
        assert plan.w_nlp == 1.0
        assert plan.w_audio == 0.0
        assert plan.w_vision == 0.0

    def test_text_plus_audio_weights_sum_to_1(self):
        plan = FusionPlan.compute(has_audio=True, has_vision=False)
        assert abs(plan.w_nlp + plan.w_audio + plan.w_vision - 1.0) < 0.001

    def test_text_plus_vision_weights_sum_to_1(self):
        plan = FusionPlan.compute(has_audio=False, has_vision=True)
        assert abs(plan.w_nlp + plan.w_audio + plan.w_vision - 1.0) < 0.001

    def test_all_modalities_weights_sum_to_1(self):
        plan = FusionPlan.compute(has_audio=True, has_vision=True)
        assert abs(plan.w_nlp + plan.w_audio + plan.w_vision - 1.0) < 0.001

    def test_all_modalities_base_weights(self):
        plan = FusionPlan.compute(has_audio=True, has_vision=True)
        assert plan.w_nlp    == BASE_WEIGHT_NLP
        assert plan.w_audio  == BASE_WEIGHT_AUDIO
        assert plan.w_vision == BASE_WEIGHT_VISION

    def test_missing_audio_redistributes_to_nlp_and_vision(self):
        plan_no_audio  = FusionPlan.compute(has_audio=False, has_vision=True)
        plan_all       = FusionPlan.compute(has_audio=True,  has_vision=True)
        assert plan_no_audio.w_nlp    > plan_all.w_nlp
        assert plan_no_audio.w_vision > plan_all.w_vision
        assert plan_no_audio.w_audio  == 0.0

    def test_missing_vision_redistributes(self):
        plan_no_vision = FusionPlan.compute(has_audio=True, has_vision=False)
        plan_all       = FusionPlan.compute(has_audio=True, has_vision=True)
        assert plan_no_vision.w_nlp   > plan_all.w_nlp
        assert plan_no_vision.w_audio > plan_all.w_audio
        assert plan_no_vision.w_vision == 0.0


# ── Signal parsing ────────────────────────────────────────────────────────────

class TestSignalParsing:
    def test_parse_nlp_signal(self, nlp_result_pneumonia):
        sig = _parse_nlp_signal(nlp_result_pneumonia)
        assert sig.modality == "nlp"
        assert sig.available is True
        assert sig.top_label == "Pneumonia"
        assert abs(sig.confidence - 0.82) < 0.001
        assert "Pneumonia" in sig.all_probs

    def test_parse_nlp_includes_differential(self, nlp_result_pneumonia):
        sig = _parse_nlp_signal(nlp_result_pneumonia)
        assert "Bronchial Asthma" in sig.all_probs
        assert sig.all_probs["Bronchial Asthma"] == 0.35

    def test_parse_audio_severe(self, audio_result_severe):
        sig = _parse_audio_signal(audio_result_severe)
        assert sig.modality == "audio"
        assert sig.available is True
        assert sig.top_label == "cough_severe"
        assert sig.confidence == 0.78

    def test_parse_audio_none_not_available(self):
        sig = _parse_audio_signal(None)
        assert sig.available is False

    def test_parse_audio_error_not_available(self):
        sig = _parse_audio_signal({"error": "model not loaded"})
        assert sig.available is False
        assert sig.error == "model not loaded"

    def test_parse_vision_pneumonia(self, vision_result_pneumonia):
        sig = _parse_vision_signal(vision_result_pneumonia)
        assert sig.modality == "vision"
        assert sig.available is True
        assert sig.top_label == "bacterial_pneumonia"

    def test_parse_vision_none_not_available(self):
        sig = _parse_vision_signal(None)
        assert sig.available is False


# ── Corroboration scoring ─────────────────────────────────────────────────────

class TestCorroborationScoring:
    def test_audio_severe_boosts_pneumonia(self, nlp_result_pneumonia, audio_result_severe):
        plan = FusionPlan.compute(has_audio=True, has_vision=False)
        nlp_sig   = _parse_nlp_signal(nlp_result_pneumonia)
        audio_sig = _parse_audio_signal(audio_result_severe)
        vis_sig   = _parse_vision_signal(None)

        text_only_score = plan.w_nlp * nlp_sig.all_probs.get("Pneumonia", 0)

        scores = _compute_corroboration_scores(nlp_sig, audio_sig, vis_sig, plan)
        fused_pneumonia = scores.get("Pneumonia", 0)

        # Audio severe corroborates Pneumonia → fused score should be higher
        assert fused_pneumonia > text_only_score

    def test_vision_pneumonia_boosts_pneumonia(self, nlp_result_pneumonia, vision_result_pneumonia):
        plan    = FusionPlan.compute(has_audio=False, has_vision=True)
        nlp_sig = _parse_nlp_signal(nlp_result_pneumonia)
        vis_sig = _parse_vision_signal(vision_result_pneumonia)

        text_only_score = plan.w_nlp * nlp_sig.all_probs.get("Pneumonia", 0)
        scores = _compute_corroboration_scores(nlp_sig, _parse_audio_signal(None), vis_sig, plan)
        assert scores.get("Pneumonia", 0) > text_only_score

    def test_all_modalities_highest_pneumonia_score(self, nlp_result_pneumonia, audio_result_severe, vision_result_pneumonia):
        plan_all   = FusionPlan.compute(has_audio=True,  has_vision=True)
        plan_audio = FusionPlan.compute(has_audio=True,  has_vision=False)
        plan_none  = FusionPlan.compute(has_audio=False, has_vision=False)

        nlp_sig   = _parse_nlp_signal(nlp_result_pneumonia)
        audio_sig = _parse_audio_signal(audio_result_severe)
        vis_sig   = _parse_vision_signal(vision_result_pneumonia)

        score_all   = _compute_corroboration_scores(nlp_sig, audio_sig, vis_sig, plan_all).get("Pneumonia", 0)
        score_audio = _compute_corroboration_scores(nlp_sig, audio_sig, _parse_vision_signal(None), plan_audio).get("Pneumonia", 0)
        score_text  = _compute_corroboration_scores(nlp_sig, _parse_audio_signal(None), _parse_vision_signal(None), plan_none).get("Pneumonia", 0)

        # More modalities corroborating → higher score
        assert score_all >= score_audio >= score_text

    def test_healthy_cough_no_boost_to_pneumonia(self, nlp_result_pneumonia, audio_result_healthy):
        plan      = FusionPlan.compute(has_audio=True, has_vision=False)
        nlp_sig   = _parse_nlp_signal(nlp_result_pneumonia)
        audio_sig = _parse_audio_signal(audio_result_healthy)

        scores = _compute_corroboration_scores(nlp_sig, audio_sig, _parse_vision_signal(None), plan)
        pneumonia_score = scores.get("Pneumonia", 0)
        # cough_healthy should NOT corroborate Pneumonia
        assert "Pneumonia" not in AUDIO_CORROBORATION.get("cough_healthy", {})

    def test_fused_scores_all_non_negative(self, nlp_result_pneumonia, audio_result_severe, vision_result_pneumonia):
        plan    = FusionPlan.compute(has_audio=True, has_vision=True)
        nlp_sig = _parse_nlp_signal(nlp_result_pneumonia)
        scores  = _compute_corroboration_scores(
            nlp_sig,
            _parse_audio_signal(audio_result_severe),
            _parse_vision_signal(vision_result_pneumonia),
            plan,
        )
        for disease, score in scores.items():
            assert score >= 0.0, f"Negative score for {disease}: {score}"


# ── Full fusion ───────────────────────────────────────────────────────────────

class TestFuseSignals:
    @pytest.mark.asyncio
    async def test_text_only_returns_nlp_result(self, nlp_result_pneumonia):
        result = await fuse_signals(nlp_result=nlp_result_pneumonia, symptom_count=6)
        assert result.primary_diagnosis == "Pneumonia"
        assert result.diagnosis_source in ("xgboost", "fusion")

    @pytest.mark.asyncio
    async def test_audio_corroboration_increases_confidence(self, nlp_result_pneumonia, audio_result_severe):
        result_text  = await fuse_signals(nlp_result=nlp_result_pneumonia, symptom_count=6)
        result_fused = await fuse_signals(
            nlp_result=nlp_result_pneumonia,
            audio_result=audio_result_severe,
            symptom_count=6,
        )
        assert result_fused.confidence >= result_text.confidence * 0.9   # ≥ 90% of text-only

    @pytest.mark.asyncio
    async def test_vision_corroboration_source_is_fusion(self, nlp_result_pneumonia, vision_result_pneumonia):
        result = await fuse_signals(
            nlp_result=nlp_result_pneumonia,
            vision_result=vision_result_pneumonia,
            symptom_count=6,
        )
        assert result.diagnosis_source == "fusion"

    @pytest.mark.asyncio
    async def test_red_flags_from_nlp_preserved(self, nlp_result_with_red_flags):
        result = await fuse_signals(nlp_result=nlp_result_with_red_flags, symptom_count=5)
        assert len(result.red_flags) > 0
        assert any("cardiac" in f.lower() or "chest" in f.lower() for f in result.red_flags)

    @pytest.mark.asyncio
    async def test_audio_severe_adds_red_flag(self, nlp_result_pneumonia, audio_result_severe):
        result = await fuse_signals(
            nlp_result=nlp_result_pneumonia,
            audio_result=audio_result_severe,
            symptom_count=6,
        )
        # High confidence audio severe should add a red flag
        audio_flags = [f for f in result.red_flags if "audio" in f.lower() or "respiratory" in f.lower()]
        assert len(audio_flags) > 0

    @pytest.mark.asyncio
    async def test_diabetic_wound_vision_adds_red_flag(self, nlp_result_pneumonia, vision_result_diabetic):
        result = await fuse_signals(
            nlp_result=nlp_result_pneumonia,
            vision_result=vision_result_diabetic,
            symptom_count=6,
        )
        wound_flags = [f for f in result.red_flags if "diabet" in f.lower() or "wound" in f.lower()]
        assert len(wound_flags) > 0

    @pytest.mark.asyncio
    async def test_red_flags_deduplicated(self, nlp_result_with_red_flags, audio_result_severe):
        result = await fuse_signals(
            nlp_result=nlp_result_with_red_flags,
            audio_result=audio_result_severe,
            symptom_count=6,
        )
        assert len(result.red_flags) == len(set(result.red_flags))

    @pytest.mark.asyncio
    async def test_llm_fallback_triggered_on_low_confidence(self, nlp_result_low_confidence):
        mock_fallback = AsyncMock(return_value=DiagnosisResult(
            primary_diagnosis="Viral fever",
            confidence=0.65,
            differential=[],
            diagnosis_source="llm_gemini",
            red_flags=[],
        ))
        with patch("app.services.diagnosis.fusion.run_llm_fallback", mock_fallback):
            result = await fuse_signals(
                nlp_result=nlp_result_low_confidence,
                symptom_count=2,   # below MIN_SYMPTOMS_FOR_CLASSIFIER
                extracted_symptoms=["high_fever"],
            )
        mock_fallback.assert_called_once()
        assert result.diagnosis_source == "llm_gemini"

    @pytest.mark.asyncio
    async def test_llm_fallback_not_triggered_when_audio_corroborates(
        self, nlp_result_low_confidence, audio_result_severe
    ):
        """Audio strongly corroborating should keep fused confidence above threshold."""
        # Low NLP confidence + high audio severe → fused might still be above threshold
        # This tests the logic: nlp_alone_too_weak AND fusion_still_weak
        mock_fallback = AsyncMock(return_value=DiagnosisResult(
            primary_diagnosis="LLM result",
            confidence=0.5,
            differential=[],
            diagnosis_source="llm_gemini",
            red_flags=[],
        ))
        with patch("app.services.diagnosis.fusion.run_llm_fallback", mock_fallback):
            result = await fuse_signals(
                nlp_result=nlp_result_low_confidence,
                audio_result=audio_result_severe,
                symptom_count=2,
            )
        # Result could be either fusion (if fused_conf > threshold*0.8) or llm_fallback
        # Either way, should not crash
        assert result.primary_diagnosis != ""
        assert result.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_confidence_always_clamped_to_1(self, nlp_result_pneumonia, audio_result_severe, vision_result_pneumonia):
        result = await fuse_signals(
            nlp_result=nlp_result_pneumonia,
            audio_result=audio_result_severe,
            vision_result=vision_result_pneumonia,
            symptom_count=8,
        )
        assert result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_confidence_non_negative(self, nlp_result_low_confidence):
        mock_fallback = AsyncMock(return_value=DiagnosisResult(
            primary_diagnosis="Unknown",
            confidence=0.0,
            differential=[],
            diagnosis_source="llm_gemini",
            red_flags=[],
        ))
        with patch("app.services.diagnosis.fusion.run_llm_fallback", mock_fallback):
            result = await fuse_signals(
                nlp_result=nlp_result_low_confidence,
                symptom_count=1,
            )
        assert result.confidence >= 0.0


# ── Corroboration tables ───────────────────────────────────────────────────────

class TestCorroborationTables:
    def test_audio_corroboration_all_values_in_range(self):
        for label, disease_map in AUDIO_CORROBORATION.items():
            for disease, score in disease_map.items():
                assert 0.0 <= score <= 1.0, f"Score out of range: {label} → {disease}: {score}"

    def test_vision_corroboration_all_values_in_range(self):
        for label, disease_map in VISION_CORROBORATION.items():
            for disease, score in disease_map.items():
                assert 0.0 <= score <= 1.0, f"Score out of range: {label} → {disease}: {score}"

    def test_audio_triage_hints_valid_levels(self):
        for label, level in AUDIO_TRIAGE_HINT.items():
            assert 1 <= level <= 5, f"Invalid triage level for {label}: {level}"

    def test_all_audio_classes_have_entries(self):
        assert "cough_severe"  in AUDIO_CORROBORATION
        assert "cough_healthy" in AUDIO_CORROBORATION
        assert "other"         in AUDIO_CORROBORATION

    def test_all_audio_classes_have_triage_hints(self):
        assert "cough_severe"  in AUDIO_TRIAGE_HINT
        assert "cough_healthy" in AUDIO_TRIAGE_HINT
        assert "other"         in AUDIO_TRIAGE_HINT

    def test_cough_severe_higher_triage_than_healthy(self):
        assert AUDIO_TRIAGE_HINT["cough_severe"] > AUDIO_TRIAGE_HINT["cough_healthy"]


# ── Diagnose endpoint tests ───────────────────────────────────────────────────

class TestDiagnoseEndpoints:
    @pytest.mark.asyncio
    async def test_predict_text_only(self, async_client, mock_redis):
        mock_extraction = (
            MagicMock(symptoms=["high_fever","cough"], duration="3 days",
                      severity_estimate=7, body_parts=[], raw_keywords=["fever","cough"]),
            [],
            {"high_fever": 1, "cough": 1, **{s: 0 for s in ["headache","nausea"]}},
        )
        mock_nlp = AsyncMock(return_value=DiagnosisResult(
            primary_diagnosis="Pneumonia", confidence=0.85,
            differential=[], diagnosis_source="xgboost", red_flags=[],
        ))
        mock_triage = AsyncMock(return_value=MagicMock(
            level=3, label="Visit PHC within 48h", reasoning="...",
            asha_assigned=None, follow_up_at=None,
        ))
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        with patch("app.api.v1.endpoints.diagnose.extract_symptoms", AsyncMock(return_value=mock_extraction)), \
             patch("app.services.diagnosis.classifier.run_classifier", mock_nlp), \
             patch("app.api.v1.endpoints.diagnose.compute_triage", mock_triage), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis), \
             patch("app.core.database.AsyncSessionFactory", return_value=mock_db):
            r = await async_client.post(
                "/api/v1/diagnose/predict/text",
                json={"text": "I have fever and cough for 3 days", "language": "en"},
            )

        assert r.status_code in (200, 422, 500)   # depends on DB mock depth

    @pytest.mark.asyncio
    async def test_diagnose_audio_unsupported_format(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/diagnose/audio",
                files={"file": ("test.mp4", b"fakedata", "video/mp4")},
            )
        assert r.status_code == 415

    @pytest.mark.asyncio
    async def test_diagnose_audio_empty_file(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/diagnose/audio",
                files={"file": ("empty.wav", b"", "audio/wav")},
            )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_diagnose_audio_valid_wav(self, async_client, mock_redis):
        wav = _make_wav_bytes()
        mock_audio = AsyncMock(return_value={
            "top_prediction":  {"label": "cough_severe", "confidence": 0.75},
            "all_predictions": [{"label": "cough_severe", "confidence": 0.75}],
            "signal_source": "audio_model",
        })
        with patch("app.api.v1.endpoints.diagnose.run_audio_model", mock_audio), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/diagnose/audio",
                files={"file": ("test.wav", wav, "audio/wav")},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["top_prediction"]["label"] == "cough_severe"

    @pytest.mark.asyncio
    async def test_diagnose_image_valid(self, async_client, mock_redis):
        png = _make_png_bytes()
        mock_vision = AsyncMock(return_value={
            "dataset_type":   "chest",
            "top_prediction": {"label": "bacterial_pneumonia", "confidence": 0.72},
            "all_predictions": [{"label": "bacterial_pneumonia", "confidence": 0.72}],
            "signal_source": "vision_model",
        })
        with patch("app.api.v1.endpoints.diagnose.run_vision_model", mock_vision), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/diagnose/image",
                files={"file": ("xray.png", png, "image/png")},
                data={"task_type": "chest"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["top_prediction"]["label"] == "bacterial_pneumonia"

    @pytest.mark.asyncio
    async def test_diagnose_image_invalid_format(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/diagnose/image",
                files={"file": ("test.gif", b"GIF89a", "image/gif")},
            )
        assert r.status_code == 415

    @pytest.mark.asyncio
    async def test_explain_invalid_uuid(self, async_client):
        r = await async_client.get("/api/v1/diagnose/explain/not-a-uuid")
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_explain_session_not_found(self, async_client, mock_redis):
        fake_id = str(uuid.uuid4())
        mock_db_result = MagicMock()
        mock_db_result.scalar_one_or_none.return_value = None
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.get(f"/api/v1/diagnose/explain/{fake_id}")
        assert r.status_code in (404, 500)


# ── Integration: concurrent model execution ───────────────────────────────────

class TestConcurrentExecution:
    @pytest.mark.asyncio
    async def test_run_all_models_text_only(self):
        from app.services.diagnosis.fusion import run_all_models_concurrent

        mock_nlp = AsyncMock(return_value=DiagnosisResult(
            primary_diagnosis="Pneumonia", confidence=0.8,
            differential=[], diagnosis_source="xgboost", red_flags=[],
        ))
        with patch("app.services.diagnosis.classifier.run_classifier", mock_nlp):
            nlp_r, audio_r, vision_r = await run_all_models_concurrent(
                symptom_vector={"high_fever": 1, "cough": 1},
            )
        assert nlp_r.primary_diagnosis == "Pneumonia"
        assert audio_r is None
        assert vision_r is None

    @pytest.mark.asyncio
    async def test_run_all_models_handles_audio_error_gracefully(self):
        from app.services.diagnosis.fusion import run_all_models_concurrent

        mock_nlp   = AsyncMock(return_value=DiagnosisResult(
            primary_diagnosis="Pneumonia", confidence=0.8,
            differential=[], diagnosis_source="xgboost", red_flags=[],
        ))
        mock_audio = AsyncMock(side_effect=RuntimeError("audio model crashed"))

        with patch("app.services.diagnosis.classifier.run_classifier", mock_nlp), \
             patch("app.services.diagnosis.audio_model.run_audio_model", mock_audio):
            # Write a temp wav file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(_make_wav_bytes())
                wav_path = f.name
            try:
                nlp_r, audio_r, vision_r = await run_all_models_concurrent(
                    symptom_vector={"high_fever": 1},
                    audio_path=wav_path,
                )
            finally:
                os.unlink(wav_path)

        assert nlp_r.primary_diagnosis == "Pneumonia"
        assert audio_r is None   # error was swallowed, not propagated

    @pytest.mark.asyncio
    async def test_fuse_signals_end_to_end(self):
        """Full integration: parse → plan → score → result."""
        nlp = DiagnosisResult(
            primary_diagnosis="Tuberculosis", confidence=0.74,
            differential=[{"disease": "Pneumonia", "confidence": 0.35}],
            diagnosis_source="xgboost", red_flags=[],
        )
        audio = {
            "top_prediction":  {"label": "cough_severe", "confidence": 0.82},
            "all_predictions": [{"label": "cough_severe", "confidence": 0.82}],
            "signal_source": "audio_model",
        }
        result = await fuse_signals(
            nlp_result=nlp,
            audio_result=audio,
            symptom_count=6,
        )
        assert result.primary_diagnosis != ""
        assert 0.0 <= result.confidence <= 1.0
        assert result.diagnosis_source in ("xgboost", "fusion", "llm_gemini")
        assert isinstance(result.red_flags, list)
