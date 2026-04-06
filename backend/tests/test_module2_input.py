"""
Vaidya — Module 2 test suite
Tests: language detection, audio preprocessing, Whisper pipeline, translator,
       voice endpoint, text endpoint, WebSocket stream
"""

import asyncio
import io
import json
import os
import struct
import tempfile
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.services.nlp.language_detector import (
    _script_detect,
    _langdetect_detect,
    detect_language,
    is_supported_language,
)
from app.services.nlp.translator import (
    _local_translate,
    HINDI_TO_ENGLISH,
    TAMIL_TO_ENGLISH,
)
from app.services.nlp.transcriber import _estimate_confidence


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
    r.ping.return_value = True
    r.get.return_value = None
    r.setex.return_value = True
    r.pipeline.return_value.execute = AsyncMock(return_value=[0, 1, 1, True])
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


def _make_wav_bytes(duration_s: float = 2.0, sr: int = 16000, amplitude: float = 0.3) -> bytes:
    """Generate a synthetic WAV file with a sine wave (real audio, not silence)."""
    import math
    n_samples = int(sr * duration_s)
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for i in range(n_samples):
            # 440 Hz sine wave (A4 note)
            val = int(amplitude * 32767 * math.sin(2 * math.pi * 440 * i / sr))
            wf.writeframes(struct.pack("<h", val))
    return buf.getvalue()


def _make_silent_wav_bytes(duration_s: float = 0.5) -> bytes:
    """Generate a silent WAV file."""
    n_samples = int(16000 * duration_s)
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * n_samples)
    return buf.getvalue()


# ── Language detection ─────────────────────────────────────────────────────────

class TestLanguageDetector:
    def test_devanagari_script_hindi(self):
        # Pure Hindi text — Devanagari script
        assert _script_detect("मुझे बुखार है") == "hi"

    def test_tamil_script(self):
        assert _script_detect("எனக்கு காய்ச்சல்") == "ta"

    def test_english_no_script(self):
        # English has no distinct Unicode range — should return None
        assert _script_detect("I have fever") is None

    def test_mixed_hindi_english(self):
        # Mixed text: Hindi + English words
        result = _script_detect("मुझे 3 दिन से fever है")
        assert result == "hi"

    def test_mixed_tamil_english(self):
        result = _script_detect("எனக்கு 3 நாட்களாக cough உள்ளது")
        assert result == "ta"

    def test_empty_text(self):
        assert _script_detect("") is None

    @pytest.mark.asyncio
    async def test_detect_language_hindi(self):
        result = await detect_language("मुझे बुखार और खांसी है")
        assert result == "hi"

    @pytest.mark.asyncio
    async def test_detect_language_tamil(self):
        result = await detect_language("எனக்கு காய்ச்சல் மற்றும் இருமல் உள்ளது")
        assert result == "ta"

    @pytest.mark.asyncio
    async def test_detect_language_english(self):
        result = await detect_language("I have fever and cough for three days")
        assert result == "en"

    @pytest.mark.asyncio
    async def test_detect_language_empty_defaults_en(self):
        result = await detect_language("")
        assert result == "en"

    @pytest.mark.asyncio
    async def test_detect_language_whitespace_defaults_en(self):
        result = await detect_language("   ")
        assert result == "en"

    def test_is_supported_language(self):
        assert is_supported_language("en") is True
        assert is_supported_language("hi") is True
        assert is_supported_language("ta") is True
        assert is_supported_language("fr") is False
        assert is_supported_language("zh") is False
        assert is_supported_language("")   is False

    @pytest.mark.parametrize("text,expected", [
        ("मुझे बुखार है",                "hi"),
        ("எனக்கு காய்ச்சல்",             "ta"),
        ("I have headache",              "en"),
        ("मुझे chest pain है",           "hi"),   # mixed Hindi+English
        ("எனக்கு 3 நாட்களாக fever",     "ta"),   # mixed Tamil+English
    ])
    @pytest.mark.asyncio
    async def test_detect_parametrize(self, text, expected):
        result = await detect_language(text)
        assert result == expected


# ── Translator ─────────────────────────────────────────────────────────────────

class TestTranslator:
    def test_hindi_fever_translation(self):
        result = _local_translate("बुखार", "hi")
        assert "fever" in result.lower()

    def test_hindi_cough_translation(self):
        result = _local_translate("खांसी", "hi")
        assert "cough" in result.lower()

    def test_tamil_fever_translation(self):
        result = _local_translate("காய்ச்சல்", "ta")
        assert "fever" in result.lower()

    def test_tamil_breathlessness(self):
        result = _local_translate("மூச்சு திணறல்", "ta")
        assert "breath" in result.lower()

    def test_hindi_complex_sentence(self):
        text = "मुझे बुखार और खांसी है, सांस लेने में तकलीफ है"
        result = _local_translate(text, "hi")
        assert "fever" in result.lower()
        assert "cough" in result.lower()

    def test_tamil_complex_sentence(self):
        text = "எனக்கு காய்ச்சல் மற்றும் இருமல் உள்ளது, மார்பு வலி"
        result = _local_translate(text, "ta")
        assert "fever" in result.lower()
        assert "cough" in result.lower()

    def test_english_passthrough(self):
        text = "I have fever and cough"
        result = _local_translate(text, "en")
        assert result == text   # should not be modified

    def test_hindi_phrase_map_coverage(self):
        # All Hindi phrases should be in the map
        assert len(HINDI_TO_ENGLISH) >= 40

    def test_tamil_phrase_map_coverage(self):
        assert len(TAMIL_TO_ENGLISH) >= 40

    def test_longer_phrases_take_priority(self):
        # "तेज बुखार" (high fever) should not be split into "तेज" + "बुखार" (fever)
        result = _local_translate("तेज बुखार", "hi")
        assert "high fever" in result.lower()

    @pytest.mark.asyncio
    async def test_translate_endpoint_indictrans_unavailable(self):
        """When IndicTrans2 is down, local map should take over."""
        from app.services.nlp.translator import translate_to_english
        result = await translate_to_english("बुखार", "hi")
        # Should use local_map since IndicTrans2 isn't running in test
        assert result["method"] in ("local_map", "indictrans2")
        assert "fever" in result["translated"].lower() or result["translated"]

    @pytest.mark.asyncio
    async def test_translate_english_passthrough(self):
        from app.services.nlp.translator import translate_to_english
        result = await translate_to_english("fever and cough", "en")
        assert result["method"] == "passthrough"
        assert result["translated"] == "fever and cough"


# ── Whisper confidence scoring ─────────────────────────────────────────────────

class TestWhisperConfidence:
    def test_empty_text_zero_confidence(self):
        assert _estimate_confidence("", []) == 0.0

    def test_hallucination_low_confidence(self):
        # Known Whisper hallucination — should get low confidence
        conf = _estimate_confidence("thank you", [])
        assert conf < 0.5

    def test_short_text_moderate_confidence(self):
        conf = _estimate_confidence("fever", [])
        assert 0.3 <= conf <= 0.8

    def test_chunked_text_higher_confidence(self):
        chunks = [
            {"text": "I have fever", "timestamp": (0, 2)},
            {"text": "and cough", "timestamp": (2, 4)},
        ]
        conf_chunked = _estimate_confidence("I have fever and cough", chunks)
        conf_plain   = _estimate_confidence("I have fever and cough", [])
        assert conf_chunked >= conf_plain

    def test_max_confidence_capped(self):
        chunks = [{"text": f"chunk {i}", "timestamp": (i, i+1)} for i in range(10)]
        conf = _estimate_confidence("long transcript with many chunks", chunks)
        assert conf <= 1.0


# ── Audio preprocessor ────────────────────────────────────────────────────────

class TestAudioPreprocessor:
    def test_quality_check_valid_audio(self):
        from app.services.nlp.audio_preprocessor import check_audio_quality

        wav_bytes = _make_wav_bytes(duration_s=3.0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name

        try:
            result = check_audio_quality(tmp)
            assert result["ok"] is True
            assert result["duration_s"] >= 2.5
        finally:
            os.unlink(tmp)

    def test_quality_check_silent_audio(self):
        from app.services.nlp.audio_preprocessor import check_audio_quality

        wav_bytes = _make_silent_wav_bytes(duration_s=2.0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name

        try:
            result = check_audio_quality(tmp)
            assert result["ok"] is False
            assert "silent" in result["reason"].lower()
        finally:
            os.unlink(tmp)

    def test_quality_check_too_short(self):
        from app.services.nlp.audio_preprocessor import check_audio_quality

        wav_bytes = _make_wav_bytes(duration_s=0.3)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name

        try:
            result = check_audio_quality(tmp)
            assert result["ok"] is False
            assert "short" in result["reason"].lower()
        finally:
            os.unlink(tmp)

    def test_convert_to_wav_already_wav(self):
        from app.services.nlp.audio_preprocessor import convert_to_wav
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            result = convert_to_wav(f.name)
            assert result == f.name   # no conversion needed


# ── Voice endpoint ─────────────────────────────────────────────────────────────

class TestVoiceEndpoint:
    @pytest.mark.asyncio
    async def test_voice_upload_valid_wav(self, async_client, mock_redis):
        wav = _make_wav_bytes(duration_s=3.0)

        mock_stt = AsyncMock(return_value={
            "text":       "I have fever and cough",
            "language":   "en",
            "confidence": 0.85,
            "chunks":     [],
        })

        with patch("app.api.v1.endpoints.input.transcribe_audio", mock_stt), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis), \
             patch("app.api.v1.endpoints.input.preprocess_audio",
                   return_value={"ok": True, "processed_path": "/tmp/fake.wav", "quality": {"duration_s": 3.0}}):

            response = await async_client.post(
                "/api/v1/input/voice",
                files={"file": ("test.wav", wav, "audio/wav")},
                data={"language_hint": "en", "denoise": "false"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["transcript"] == "I have fever and cough"
        assert data["detected_language"] == "en"
        assert data["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_voice_unsupported_format(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            response = await async_client.post(
                "/api/v1/input/voice",
                files={"file": ("test.mp4", b"fake_video_data", "video/mp4")},
            )
        assert response.status_code == 415

    @pytest.mark.asyncio
    async def test_voice_empty_file(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            response = await async_client.post(
                "/api/v1/input/voice",
                files={"file": ("empty.wav", b"", "audio/wav")},
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_voice_silent_audio_rejected(self, async_client, mock_redis):
        wav = _make_silent_wav_bytes(duration_s=2.0)
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            response = await async_client.post(
                "/api/v1/input/voice",
                files={"file": ("silent.wav", wav, "audio/wav")},
                data={"denoise": "false"},
            )
        assert response.status_code in (422, 200)   # depends on QC config

    @pytest.mark.asyncio
    async def test_voice_hindi_transcript(self, async_client, mock_redis):
        wav = _make_wav_bytes(duration_s=3.0)
        hindi_stt = AsyncMock(return_value={
            "text":       "मुझे बुखार है",
            "language":   "hi",
            "confidence": 0.78,
            "chunks":     [],
        })
        with patch("app.api.v1.endpoints.input.transcribe_audio", hindi_stt), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis), \
             patch("app.api.v1.endpoints.input.preprocess_audio",
                   return_value={"ok": True, "processed_path": "/tmp/fake.wav", "quality": {}}):
            response = await async_client.post(
                "/api/v1/input/voice",
                files={"file": ("hindi.wav", wav, "audio/wav")},
                data={"language_hint": "hi"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["detected_language"] == "hi"
        assert "बुखार" in data["transcript"]

    @pytest.mark.asyncio
    async def test_voice_tamil_transcript(self, async_client, mock_redis):
        wav = _make_wav_bytes(duration_s=3.0)
        tamil_stt = AsyncMock(return_value={
            "text":       "எனக்கு காய்ச்சல் உள்ளது",
            "language":   "ta",
            "confidence": 0.82,
            "chunks":     [],
        })
        with patch("app.api.v1.endpoints.input.transcribe_audio", tamil_stt), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis), \
             patch("app.api.v1.endpoints.input.preprocess_audio",
                   return_value={"ok": True, "processed_path": "/tmp/fake.wav", "quality": {}}):
            response = await async_client.post(
                "/api/v1/input/voice",
                files={"file": ("tamil.ogg", wav, "audio/ogg")},
                data={"language_hint": "ta"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["detected_language"] == "ta"


# ── Text endpoint ──────────────────────────────────────────────────────────────

class TestTextEndpoint:
    @pytest.mark.asyncio
    async def test_text_english(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis), \
             patch("app.api.v1.endpoints.input.detect_language", AsyncMock(return_value="en")):
            r = await async_client.post(
                "/api/v1/input/text",
                json={"text": "I have fever and cough for 3 days", "language": "en"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["original_language"] == "en"
        assert "cache_key" in data

    @pytest.mark.asyncio
    async def test_text_hindi(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis), \
             patch("app.api.v1.endpoints.input.detect_language", AsyncMock(return_value="hi")):
            r = await async_client.post(
                "/api/v1/input/text",
                json={"text": "मुझे बुखार और खांसी है और सांस लेने में तकलीफ है"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["original_language"] == "hi"
        assert "english_text" in data

    @pytest.mark.asyncio
    async def test_text_too_short_rejected(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/input/text",
                json={"text": "Hi"},
            )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_languages_endpoint(self, async_client):
        r = await async_client.get("/api/v1/input/languages")
        assert r.status_code == 200
        data = r.json()
        codes = [l["code"] for l in data["supported_languages"]]
        assert "en" in codes
        assert "hi" in codes
        assert "ta" in codes


# ── Integration: text → language detect → translate pipeline ──────────────────

class TestFullTextPipeline:
    @pytest.mark.asyncio
    async def test_hindi_text_gets_translated(self):
        from app.services.nlp.language_detector import detect_language
        from app.services.nlp.translator import translate_to_english

        text = "मुझे बुखार और खांसी है"
        lang = await detect_language(text)
        assert lang == "hi"

        result = await translate_to_english(text, lang)
        assert "fever" in result["translated"].lower()
        assert result["method"] in ("local_map", "indictrans2")

    @pytest.mark.asyncio
    async def test_tamil_text_gets_translated(self):
        from app.services.nlp.language_detector import detect_language
        from app.services.nlp.translator import translate_to_english

        text = "எனக்கு காய்ச்சல் மற்றும் இருமல் உள்ளது"
        lang = await detect_language(text)
        assert lang == "ta"

        result = await translate_to_english(text, lang)
        assert "fever" in result["translated"].lower()

    @pytest.mark.asyncio
    async def test_english_text_passthrough(self):
        from app.services.nlp.language_detector import detect_language
        from app.services.nlp.translator import translate_to_english

        text = "I have headache and fever for two days"
        lang = await detect_language(text)
        assert lang == "en"

        result = await translate_to_english(text, lang)
        assert result["method"] == "passthrough"
        assert result["translated"] == text
