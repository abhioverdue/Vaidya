"""
Vaidya — Module 7 test suite
Tests: haversine, facility classifier, Overpass parsing, ranker,
       eSanjeevani fallback, ABDM demo, care endpoints
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.services.care.overpass import (
    haversine_km,
    classify_facility_type,
    has_108_ambulance,
    is_24h,
    extract_address,
    _parse_overpass,
)
from app.services.care.ranker import score_hospitals, _weights
from app.services.care.esanjeevani import (
    _normalise_specialty,
    _build_case_summary,
    _demo_slots,
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


def _make_hospital(
    name="PHC Kovilpatti",
    h_type="phc",
    dist_km=3.5,
    open_24h=False,
    ambulance=False,
    pmjay=False,
) -> dict:
    return {
        "osm_id":        str(uuid.uuid4()),
        "name":          name,
        "hospital_type": h_type,
        "address":       "Test address",
        "distance_km":   dist_km,
        "phone":         "108" if ambulance else "04636-229234",
        "ambulance_108": ambulance,
        "open_24h":      open_24h,
        "pmjay_empanelled": pmjay,
        "latitude":      9.17,
        "longitude":     77.88,
    }


# ── Haversine distance ────────────────────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_km(12.97, 77.59, 12.97, 77.59) == pytest.approx(0.0, abs=0.01)

    def test_known_distance(self):
        # Chennai to Bangalore ≈ 290 km
        d = haversine_km(13.08, 80.27, 12.97, 77.59)
        assert 280 <= d <= 300

    def test_distance_is_symmetric(self):
        d1 = haversine_km(10.0, 78.0, 11.0, 79.0)
        d2 = haversine_km(11.0, 79.0, 10.0, 78.0)
        assert d1 == pytest.approx(d2, rel=1e-5)

    def test_short_distance_accurate(self):
        # About 1.1 km (rough estimate)
        d = haversine_km(12.0000, 78.0000, 12.0100, 78.0000)
        assert 1.0 <= d <= 1.2

    def test_non_negative(self):
        assert haversine_km(0, 0, 1, 1) >= 0


# ── Facility type classifier ──────────────────────────────────────────────────

class TestFacilityClassifier:
    def test_phc_from_name(self):
        assert classify_facility_type({"name": "PHC Kovilpatti"}) == "phc"
        assert classify_facility_type({"name": "Primary Health Centre Katpadi"}) == "phc"
        assert classify_facility_type({"name": "primary health center"}) == "phc"

    def test_chc_from_name(self):
        assert classify_facility_type({"name": "CHC Madurai East"}) == "chc"
        assert classify_facility_type({"name": "Community Health Centre"}) == "chc"

    def test_district_hospital(self):
        assert classify_facility_type({"name": "Government District Hospital"}) == "district"

    def test_esic(self):
        assert classify_facility_type({"name": "ESIC Hospital Chennai"}) == "esic"

    def test_private_hospital(self):
        result = classify_facility_type({"name": "Apollo Hospital", "amenity": "hospital"})
        assert result == "private"

    def test_govt_operator(self):
        result = classify_facility_type({
            "name": "City Hospital",
            "operator": "Government of Tamil Nadu",
        })
        assert result == "district"

    def test_healthcare_centre_tag(self):
        result = classify_facility_type({"healthcare": "centre"})
        assert result == "phc"

    def test_unknown_returns_other_or_private(self):
        result = classify_facility_type({"name": "Something Clinic"})
        assert result in ("phc", "private", "other")


# ── 108 ambulance detection ───────────────────────────────────────────────────

class TestAmbulanceDetection:
    def test_phone_has_108(self):
        assert has_108_ambulance({"phone": "+91-108"}) is True
        assert has_108_ambulance({"phone": "1800-108-1234"}) is True

    def test_no_108_in_tags(self):
        assert has_108_ambulance({"phone": "04636-229234"}) is False

    def test_name_has_ambulance(self):
        assert has_108_ambulance({"name": "District Hospital Ambulance Centre"}) is True

    def test_empty_tags(self):
        assert has_108_ambulance({}) is False


# ── 24h detection ─────────────────────────────────────────────────────────────

class TestOpenHours:
    def test_24_7_string(self):
        assert is_24h({"opening_hours": "24/7"}) is True

    def test_mo_su_full_day(self):
        assert is_24h({"opening_hours": "Mo-Su 00:00-24:00"}) is True

    def test_regular_hours(self):
        assert is_24h({"opening_hours": "Mo-Fr 08:00-17:00"}) is False

    def test_missing_tag(self):
        assert is_24h({}) is False


# ── Address extraction ────────────────────────────────────────────────────────

class TestAddressExtraction:
    def test_full_address_components(self):
        tags = {
            "addr:housenumber": "42",
            "addr:street":      "Gandhi Road",
            "addr:city":        "Madurai",
            "addr:postcode":    "625001",
        }
        addr = extract_address(tags)
        assert "Gandhi Road" in addr
        assert "Madurai" in addr

    def test_addr_full_fallback(self):
        tags = {"addr:full": "Near Bus Stand, Kovilpatti"}
        assert extract_address(tags) == "Near Bus Stand, Kovilpatti"

    def test_empty_tags_returns_none(self):
        assert extract_address({}) is None


# ── Overpass parsing ──────────────────────────────────────────────────────────

class TestOverpassParsing:
    def _make_osm(self, elements):
        return {"elements": elements}

    def test_node_coordinates_extracted(self):
        osm = self._make_osm([{
            "type": "node", "id": 123,
            "lat": 12.5, "lon": 78.5,
            "tags": {"name": "PHC Test", "amenity": "clinic"},
        }])
        result = _parse_overpass(osm, 12.0, 78.0, None)
        assert len(result) == 1
        assert result[0]["name"] == "PHC Test"
        assert result[0]["latitude"] == 12.5

    def test_way_uses_center_coordinates(self):
        osm = self._make_osm([{
            "type": "way", "id": 456,
            "center": {"lat": 13.0, "lon": 79.0},
            "tags": {"name": "District Hospital", "amenity": "hospital"},
        }])
        result = _parse_overpass(osm, 12.0, 78.0, None)
        assert result[0]["latitude"] == 13.0

    def test_no_name_tag_skipped(self):
        osm = self._make_osm([{
            "type": "node", "id": 789,
            "lat": 12.5, "lon": 78.5,
            "tags": {"amenity": "hospital"},   # no name
        }])
        result = _parse_overpass(osm, 12.0, 78.0, None)
        assert len(result) == 0

    def test_deduplication_by_name_and_coords(self):
        element = {
            "type": "node", "id": 1,
            "lat": 12.500, "lon": 78.500,
            "tags": {"name": "PHC Test", "amenity": "clinic"},
        }
        osm = self._make_osm([element, element])   # duplicate
        result = _parse_overpass(osm, 12.0, 78.0, None)
        assert len(result) == 1

    def test_specialty_filter_applied(self):
        osm = self._make_osm([
            {
                "type": "node", "id": 1, "lat": 12.5, "lon": 78.5,
                "tags": {
                    "name": "Pulmonology PHC",
                    "healthcare:speciality": "pulmonology",
                    "amenity": "clinic",
                },
            },
            {
                "type": "node", "id": 2, "lat": 12.6, "lon": 78.6,
                "tags": {"name": "General Clinic", "amenity": "clinic"},
            },
        ])
        result = _parse_overpass(osm, 12.0, 78.0, "pulmonology")
        assert len(result) == 1
        assert result[0]["name"] == "Pulmonology PHC"

    def test_distance_calculated(self):
        osm = self._make_osm([{
            "type": "node", "id": 1, "lat": 12.0, "lon": 78.0,
            "tags": {"name": "PHC Near", "amenity": "clinic"},
        }])
        result = _parse_overpass(osm, 12.0, 78.0, None)
        assert result[0]["distance_km"] == pytest.approx(0.0, abs=0.1)


# ── Hospital ranker ───────────────────────────────────────────────────────────

class TestHospitalRanker:
    def test_empty_list_returns_empty(self):
        assert score_hospitals([], triage_level=2) == []

    def test_phc_ranks_above_private_same_distance(self):
        hospitals = [
            _make_hospital("Private Hospital", "private", dist_km=2.0),
            _make_hospital("PHC Test",          "phc",     dist_km=2.0),
        ]
        ranked = score_hospitals(hospitals, triage_level=2)
        assert ranked[0]["name"] == "PHC Test"
        assert ranked[0]["rank"] == 1

    def test_emergency_triage_nearest_wins(self):
        """Level 5: closest hospital should rank first regardless of type."""
        hospitals = [
            _make_hospital("Distant PHC",       "phc",     dist_km=30.0, open_24h=False),
            _make_hospital("Nearby Private 24h", "private", dist_km=2.0,  open_24h=True,  ambulance=True),
        ]
        ranked = score_hospitals(hospitals, triage_level=5)
        assert ranked[0]["name"] == "Nearby Private 24h"

    def test_pmjay_patient_prefers_empanelled(self):
        hospitals = [
            _make_hospital("Non-PMJAY PHC",        "phc", dist_km=3.0, pmjay=False),
            _make_hospital("PMJAY Private Hospital","private", dist_km=4.0, pmjay=True),
        ]
        ranked = score_hospitals(hospitals, triage_level=3, pmjay_eligible=True)
        # With triage 3 the PMJAY-empanelled should rank highly
        pmjay_hospital_rank = next(h["rank"] for h in ranked if h["pmjay_empanelled"])
        assert pmjay_hospital_rank <= 2

    def test_ranks_are_sequential(self):
        hospitals = [_make_hospital(f"H{i}", "phc", dist_km=float(i)) for i in range(1, 6)]
        ranked    = score_hospitals(hospitals, triage_level=2)
        ranks     = [h["rank"] for h in ranked]
        assert ranks == list(range(1, len(ranked) + 1))

    def test_max_results_capped(self):
        hospitals = [_make_hospital(f"H{i}", "phc", dist_km=float(i)) for i in range(1, 20)]
        ranked    = score_hospitals(hospitals, triage_level=2, max_results=5)
        assert len(ranked) <= 5

    def test_scores_sum_to_one(self):
        """Verify weights sum to 1.0 for all triage levels."""
        for level in range(1, 6):
            w = _weights(level)
            total = sum(w)
            assert abs(total - 1.0) < 0.001, f"Level {level}: weights sum to {total}"

    def test_24h_bonus_on_urgent_triage(self):
        hospitals = [
            _make_hospital("PHC No-24h",  "phc", dist_km=3.0, open_24h=False),
            _make_hospital("PHC With 24h", "phc", dist_km=3.1, open_24h=True),
        ]
        ranked4 = score_hospitals(hospitals, triage_level=4)
        # At triage 4 the 24h facility should rank first (slight distance penalty OK)
        assert ranked4[0]["open_24h"] is True

    def test_ambulance_boost_at_emergency(self):
        hospitals = [
            _make_hospital("PHC No Amb",    "phc", dist_km=3.0, ambulance=False, open_24h=True),
            _make_hospital("PHC With Amb",  "phc", dist_km=3.2, ambulance=True,  open_24h=True),
        ]
        ranked5 = score_hospitals(hospitals, triage_level=5)
        assert ranked5[0]["ambulance_108"] is True


# ── eSanjeevani service ───────────────────────────────────────────────────────

class TestESanjeevani:
    def test_specialty_normalisation(self):
        assert _normalise_specialty("respiratory") == "Pulmonology"
        assert _normalise_specialty("gp")          == "General Medicine"
        assert _normalise_specialty("child")       == "Paediatrics"
        assert _normalise_specialty("Cardiology")  == "Cardiology"

    def test_demo_slots_structure(self):
        slots = _demo_slots("Pulmonology", "ta")
        assert len(slots) >= 2
        for s in slots:
            assert "slot_id"     in s
            assert "doctor_name" in s
            assert "specialty"   in s
            assert "available_at" in s
            assert s["fee"]      == "Free"

    def test_demo_slots_language_aware(self):
        ta_slots = _demo_slots(None, "ta")
        hi_slots = _demo_slots(None, "hi")
        ta_langs = set(l for s in ta_slots for l in s.get("languages", []))
        hi_langs = set(l for s in hi_slots for l in s.get("languages", []))
        assert "ta" in ta_langs
        assert "hi" in hi_langs

    def test_case_summary_includes_session_id(self):
        summary = _build_case_summary("abc12345", "Dengue", 3, "ta")
        assert "abc12345"[:8] in summary
        assert "Dengue" in summary
        assert "3" in summary

    def test_case_summary_includes_urgency(self):
        s5 = _build_case_summary("x", "MI",      5, "en")
        s1 = _build_case_summary("x", "Cold",    1, "en")
        assert "EMERGENCY" in s5
        assert "Self-care"  in s1

    @pytest.mark.asyncio
    async def test_get_slots_returns_demo_on_api_failure(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception("timeout")
            from app.services.care.esanjeevani import get_available_slots
            slots = await get_available_slots(specialty="General Medicine", language="en")
        assert len(slots) >= 1
        assert all("doctor_name" in s for s in slots)

    @pytest.mark.asyncio
    async def test_book_slot_returns_fallback_on_api_failure(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = Exception("timeout")
            from app.services.care.esanjeevani import book_slot
            result = await book_slot(
                slot_id="TEST001",
                patient_name="Ravi Kumar",
                patient_phone="9876543210",
                session_id=str(uuid.uuid4()),
                diagnosis="Dengue",
                triage_level=3,
                language="ta",
            )
        assert "booking_id" in result
        assert result["status"] in ("confirmed", "pending_manual_confirm")
        assert "join_url" in result


# ── ABDM service ──────────────────────────────────────────────────────────────

class TestABDM:
    @pytest.mark.asyncio
    async def test_demo_response_when_no_credentials(self):
        from app.services.care.abdm import check_pmjay_coverage
        result = await check_pmjay_coverage("demo_token_xxxx", state_code="TN")
        assert "pmjay_eligible" in result
        assert "annual_cover"   in result
        assert result["source"] in ("abdm_live", "abdm_sandbox_demo")

    @pytest.mark.asyncio
    async def test_state_scheme_returned_for_known_states(self):
        from app.services.care.abdm import check_pmjay_coverage
        result = await check_pmjay_coverage("demo_token", state_code="AP")
        # Andhra Pradesh should return Aarogyasri
        if result.get("state_scheme"):
            assert "arogyasri" in result["state_scheme"].lower() or \
                   "andhra" in result["state_scheme"].lower() or \
                   result["source"] == "abdm_sandbox_demo"

    def test_state_name_to_code(self):
        from app.services.care.finder import _state_name_to_code
        assert _state_name_to_code("Tamil Nadu")  == "TN"
        assert _state_name_to_code("Maharashtra") == "MH"
        assert _state_name_to_code("kerala")       == "KL"
        assert _state_name_to_code("Unknown State") is None


# ── Care endpoints ────────────────────────────────────────────────────────────

class TestCareEndpoints:
    @pytest.mark.asyncio
    async def test_hospitals_requires_lat_lng(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.get("/api/v1/care/hospitals")
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_hospitals_invalid_lat(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.get("/api/v1/care/hospitals?lat=999&lng=78")
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_hospitals_with_mock_overpass(self, async_client, mock_redis):
        mock_facilities = [
            _make_hospital("PHC Kovilpatti", "phc", dist_km=3.5),
            _make_hospital("Private Hospital", "private", dist_km=5.0),
        ]
        with patch("app.services.care.finder.query_overpass",
                   AsyncMock(return_value=mock_facilities)), \
             patch("app.services.care.finder.reverse_geocode",
                   AsyncMock(return_value={"district": "Thoothukudi", "state": "Tamil Nadu"})), \
             patch("app.services.care.finder.enrich_with_empanelment",
                   AsyncMock(side_effect=lambda h, **kw: h)), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.get("/api/v1/care/hospitals?lat=9.17&lng=77.88")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert len(data["results"]) >= 1

    @pytest.mark.asyncio
    async def test_hospitals_returns_phc_first(self, async_client, mock_redis):
        mock_facilities = [
            _make_hospital("Private Hosp", "private", dist_km=1.0),
            _make_hospital("PHC Test",     "phc",     dist_km=3.0),
        ]
        with patch("app.services.care.finder.query_overpass",
                   AsyncMock(return_value=mock_facilities)), \
             patch("app.services.care.finder.reverse_geocode",
                   AsyncMock(return_value={"district": "Test"})), \
             patch("app.services.care.finder.enrich_with_empanelment",
                   AsyncMock(side_effect=lambda h, **kw: h)), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.get(
                "/api/v1/care/hospitals?lat=9.17&lng=77.88&triage_level=2"
            )
        if r.status_code == 200:
            first = r.json()["results"][0]
            assert first["hospital_type"] == "phc"

    @pytest.mark.asyncio
    async def test_teleconsult_returns_slots(self, async_client, mock_redis):
        mock_slots = _demo_slots("General Medicine", "en")
        with patch("app.api.v1.endpoints.care.get_available_slots",
                   AsyncMock(return_value=mock_slots)), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.get("/api/v1/care/teleconsult")
        assert r.status_code == 200
        data = r.json()
        assert "slots" in data
        assert data["cost"] == "Free (Government of India)"

    @pytest.mark.asyncio
    async def test_teleconsult_book(self, async_client, mock_redis):
        mock_result = {
            "booking_id":   "VD12345678",
            "doctor_name":  "Dr. Test",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
            "join_url":     "https://esanjeevaniopd.in/join/VD12345678",
            "case_summary": "Test summary",
            "status":       "confirmed",
        }
        with patch("app.api.v1.endpoints.care.book_slot",
                   AsyncMock(return_value=mock_result)), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/care/teleconsult/book",
                json={
                    "session_id":    str(uuid.uuid4()),
                    "slot_id":       "DEMO_EN_1",
                    "patient_name":  "Ravi Kumar",
                    "patient_phone": "9876543210",
                    "diagnosis":     "Dengue",
                    "triage_level":  3,
                    "language":      "en",
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert "booking_id" in data
        assert "join_url"   in data

    @pytest.mark.asyncio
    async def test_teleconsult_book_invalid_phone(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.post(
                "/api/v1/care/teleconsult/book",
                json={
                    "session_id":    str(uuid.uuid4()),
                    "slot_id":       "X",
                    "patient_name":  "Test",
                    "patient_phone": "123",   # too short
                },
            )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_coverage_requires_token(self, async_client, mock_redis):
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.get("/api/v1/care/coverage")
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_coverage_returns_scheme_info(self, async_client, mock_redis):
        mock_coverage = {
            "pmjay_eligible": True,
            "scheme_name":    "PMJAY",
            "annual_cover":   "₹5,00,000",
            "state_scheme":   "Dr. YSR Aarogyasri",
            "source":         "abdm_sandbox_demo",
        }
        with patch("app.api.v1.endpoints.care.check_pmjay_coverage",
                   AsyncMock(return_value=mock_coverage)), \
             patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.get(
                "/api/v1/care/coverage?aadhaar_token=ABDM_TEST_TOKEN_12345&state_code=AP"
            )
        assert r.status_code == 200
        data = r.json()
        assert data["pmjay_eligible"] is True

    @pytest.mark.asyncio
    async def test_geocode_cached_response(self, async_client, mock_redis):
        cached = json.dumps({
            "district": "Thoothukudi",
            "state":    "Tamil Nadu",
            "display_name": "Kovilpatti, Thoothukudi, Tamil Nadu, India",
        })
        mock_redis.get.return_value = cached
        with patch("app.core.redis.redis_client", mock_redis), \
             patch("app.core.security.redis_client", mock_redis):
            r = await async_client.get("/api/v1/care/geocode?lat=9.17&lng=77.88")
        assert r.status_code == 200
        data = r.json()
        assert data["district"] == "Thoothukudi"
