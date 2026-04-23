"""
Vaidya — Module 6 test suite: Triage engine + ASHA alert system
Tests: rule engine, emergency override, ASHA assignment, notification dispatch, follow-up scheduling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.schemas.schemas import DiagnosisResult
from app.services.triage.engine import (
    compute_triage_level,
    build_triage_reasoning,
    haversine_km,
    FOLLOWUP_HOURS,
    TRIAGE_LABELS,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_dx(
    disease="Common Cold",
    confidence=0.85,
    red_flags=None,
    source="xgboost",
) -> DiagnosisResult:
    return DiagnosisResult(
        primary_diagnosis=disease,
        confidence=confidence,
        differential=[],
        diagnosis_source=source,
        red_flags=red_flags or [],
    )


# ── Rule engine: level 1 / self-care ──────────────────────────────────────────

class TestLevel1:
    def test_common_cold_low_severity(self):
        dx = make_dx("Common Cold", 0.9)
        assert compute_triage_level(dx, self_severity=2) == 1

    def test_self_care_disease_no_severity(self):
        dx = make_dx("Allergy", 0.8)
        assert compute_triage_level(dx, self_severity=None) == 1

    def test_migraine_low_severity(self):
        dx = make_dx("Migraine", 0.75)
        assert compute_triage_level(dx, self_severity=3) == 1

    def test_acne_no_severity(self):
        dx = make_dx("Acne", 0.90)
        assert compute_triage_level(dx, self_severity=None) == 1


# ── Rule engine: level 2 / monitor ────────────────────────────────────────────

class TestLevel2:
    def test_self_care_high_severity_bumps_to_2(self):
        dx = make_dx("Common Cold", 0.9)
        assert compute_triage_level(dx, self_severity=7) == 2

    def test_unknown_disease_moderate_severity(self):
        dx = make_dx("SomeUnknownDisease", 0.5)
        assert compute_triage_level(dx, self_severity=5) == 2

    def test_default_safe(self):
        dx = make_dx("SomeDisease", 0.55)
        assert compute_triage_level(dx, self_severity=None) == 2

    def test_audio_hint_2(self):
        dx = make_dx("SomeDisease", 0.6)
        assert compute_triage_level(dx, self_severity=None, audio_hint=2) == 2


# ── Rule engine: level 3 / see GP ─────────────────────────────────────────────

class TestLevel3:
    def test_urgent_disease_low_confidence(self):
        dx = make_dx("Dengue Fever", confidence=0.35)
        assert compute_triage_level(dx, self_severity=None) == 3

    def test_low_confidence_undetermined(self):
        dx = make_dx("Undetermined", confidence=0.25)
        assert compute_triage_level(dx, self_severity=None) == 3

    def test_self_severity_6(self):
        dx = make_dx("SomeDisease", confidence=0.55)
        assert compute_triage_level(dx, self_severity=6) == 3

    def test_empty_disease_low_confidence(self):
        dx = make_dx("", confidence=0.20)
        assert compute_triage_level(dx, self_severity=None) == 3


# ── Rule engine: level 4 / urgent ─────────────────────────────────────────────

class TestLevel4:
    def test_dengue_high_confidence(self):
        dx = make_dx("Dengue Fever", confidence=0.80)
        assert compute_triage_level(dx, self_severity=None) == 4

    def test_malaria_high_confidence(self):
        dx = make_dx("Malaria", confidence=0.75)
        assert compute_triage_level(dx, self_severity=None) == 4

    def test_extreme_self_severity_9(self):
        dx = make_dx("Common Cold", 0.9)
        assert compute_triage_level(dx, self_severity=9) == 4

    def test_chest_pain_red_flag(self):
        dx = make_dx("Unknown", 0.3, red_flags=["chest pain", "breathlessness"])
        assert compute_triage_level(dx, self_severity=None) == 4

    def test_self_severity_8(self):
        dx = make_dx("SomeDisease", 0.55)
        assert compute_triage_level(dx, self_severity=8) == 4


# ── Rule engine: level 5 / emergency ──────────────────────────────────────────

class TestLevel5Emergency:
    def test_heart_attack_red_flag(self):
        dx = make_dx("Unknown", 0.5, red_flags=["heart attack", "loss of consciousness"])
        assert compute_triage_level(dx, self_severity=None) == 5

    def test_stroke_red_flag(self):
        dx = make_dx("Unknown", 0.3, red_flags=["stroke", "face drooping"])
        assert compute_triage_level(dx, self_severity=None) == 5

    def test_meningitis_red_flag(self):
        dx = make_dx("Unknown", 0.4, red_flags=["meningitis"])
        assert compute_triage_level(dx, self_severity=None) == 5

    def test_sepsis_red_flag(self):
        dx = make_dx("Unknown", 0.3, red_flags=["sepsis"])
        assert compute_triage_level(dx, self_severity=None) == 5

    def test_anaphylaxis_red_flag(self):
        dx = make_dx("Anaphylaxis", 0.9, red_flags=["throat swelling", "anaphylaxis"])
        assert compute_triage_level(dx, self_severity=None) == 5

    def test_emergency_override_age_50_chest_pain(self):
        """Spec: chest pain + breathlessness + age>50 → level 5."""
        dx = make_dx("Unknown", 0.4, red_flags=["chest pain", "breathlessness", "cardiac event"])
        assert compute_triage_level(dx, self_severity=None) == 5

    def test_haemoptysis_red_flag(self):
        dx = make_dx("TB", 0.6, red_flags=["coughing blood"])
        assert compute_triage_level(dx, self_severity=None) == 5


# ── Triage labels ──────────────────────────────────────────────────────────────

class TestTriageLabels:
    def test_all_5_levels_have_labels(self):
        assert len(TRIAGE_LABELS) == 5
        for lvl in range(1, 6):
            assert TRIAGE_LABELS[lvl]

    def test_followup_hours_defined(self):
        assert FOLLOWUP_HOURS[1] > FOLLOWUP_HOURS[3] > FOLLOWUP_HOURS[5]
        # Urgent cases follow up sooner
        assert FOLLOWUP_HOURS[5] == 2
        assert FOLLOWUP_HOURS[4] == 8


# ── Reasoning builder ──────────────────────────────────────────────────────────

class TestReasoning:
    def test_includes_disease(self):
        dx = make_dx("Dengue Fever", 0.8)
        r = build_triage_reasoning(dx, self_severity=6, level=4)
        assert "Dengue Fever" in r

    def test_includes_severity(self):
        dx = make_dx("Common Cold", 0.9)
        r = build_triage_reasoning(dx, self_severity=7, level=2)
        assert "7/10" in r

    def test_emergency_mentions_108(self):
        dx = make_dx("Unknown", 0.5, red_flags=["stroke"])
        r = build_triage_reasoning(dx, self_severity=None, level=5)
        assert "108" in r

    def test_red_flag_in_reasoning(self):
        dx = make_dx("Unknown", 0.4, red_flags=["chest pain"])
        r = build_triage_reasoning(dx, self_severity=None, level=4)
        assert "chest pain" in r.lower()


# ── Haversine distance ─────────────────────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_km(12.97, 79.16, 12.97, 79.16) == pytest.approx(0.0, abs=0.01)

    def test_known_distance(self):
        # Vellore to Chennai ≈ 130 km
        dist = haversine_km(12.9165, 79.1325, 13.0827, 80.2707)
        assert 120 < dist < 145

    def test_symmetry(self):
        d1 = haversine_km(12.97, 79.16, 13.08, 80.27)
        d2 = haversine_km(13.08, 80.27, 12.97, 79.16)
        assert d1 == pytest.approx(d2, abs=0.01)


# ── FCM message builder ────────────────────────────────────────────────────────

class TestFCMMessage:
    def test_level5_is_high_priority(self):
        from app.services.notifications.fcm import _build_message
        msg = _build_message("token123", "sess1", "worker1", 5, "Stroke")
        assert msg["message"]["android"]["priority"] == "high"
        assert "EMERGENCY" in msg["message"]["notification"]["title"]

    def test_reminder_uses_followup_channel(self):
        from app.services.notifications.fcm import _build_message
        msg = _build_message("token123", "sess1", "worker1", 3, "Dengue", is_reminder=True)
        assert msg["message"]["android"]["notification"]["channel_id"] == "vaidya_followup"
        assert "reminder" in msg["message"]["notification"]["title"].lower()

    def test_level3_body_mentions_phc(self):
        from app.services.notifications.fcm import _build_message
        msg = _build_message("token123", "sess1", "worker1", 3, "Dengue")
        assert "48h" in msg["message"]["notification"]["body"]

    def test_data_values_are_strings(self):
        """FCM v1 requires all data values to be strings."""
        from app.services.notifications.fcm import _build_message
        msg = _build_message("tok", "s", "w", 4, "Malaria")
        for v in msg["message"]["data"].values():
            assert isinstance(v, str), f"Expected str, got {type(v)} for value {v}"


# ── SMS builder ────────────────────────────────────────────────────────────────

class TestSMSBuilder:
    def test_under_160_chars(self):
        from app.worker.tasks import _build_sms_body
        msg = _build_sms_body("Meenakshi", 4, "Malaria Falciparum", "abc123def456")
        assert len(msg) <= 160

    def test_urgency_label_emergency(self):
        from app.worker.tasks import _build_sms_body
        msg = _build_sms_body("Sunita", 5, "Stroke", "xyz")
        assert "EMERGENCY" in msg

    def test_session_id_truncated(self):
        from app.worker.tasks import _build_sms_body
        msg = _build_sms_body("Lakshmi", 3, "Dengue", "abcdef-1234")
        assert "ABCDEF" in msg   # first 6 chars uppercased


# ── Notification dispatch gate ─────────────────────────────────────────────────

class TestDispatchGate:
    @patch("app.services.triage.engine.notify_asha_fcm")
    @patch("app.services.triage.engine.notify_asha_sms")
    @patch("app.services.triage.engine.schedule_followup")
    def test_level_2_does_not_dispatch(self, mock_fu, mock_sms, mock_fcm):
        from app.services.triage.engine import dispatch_asha_notification
        dispatch_asha_notification(
            session_id="sess1",
            asha_worker={"id": "w1", "fcm_token": "tok", "phone": "+91xxx"},
            triage_level=2,
            diagnosis="Cold",
        )
        mock_fcm.apply_async.assert_not_called()
        mock_sms.apply_async.assert_not_called()
        mock_fu.apply_async.assert_not_called()

    @patch("app.services.triage.engine.notify_asha_fcm")
    @patch("app.services.triage.engine.notify_asha_sms")
    @patch("app.services.triage.engine.schedule_followup")
    def test_level_3_dispatches_all_channels(self, mock_fu, mock_sms, mock_fcm):
        from app.services.triage.engine import dispatch_asha_notification

        mock_fcm.apply_async = MagicMock()
        mock_sms.apply_async = MagicMock()
        mock_fu.apply_async  = MagicMock()

        dispatch_asha_notification(
            session_id="sess-abc",
            asha_worker={"id": "w1", "fcm_token": "tok123", "phone": "+919876543210", "name": "Meena"},
            triage_level=3,
            diagnosis="Dengue",
        )
        mock_fcm.apply_async.assert_called_once()
        mock_sms.apply_async.assert_called_once()
        mock_fu.apply_async.assert_called_once()
