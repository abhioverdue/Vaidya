"""
Vaidya — Care routing service (Module 7 — complete)

Orchestrates:
  1. Overpass API → OSM hospitals within radius
  2. Nominatim   → reverse geocode patient GPS → district/state
  3. ABDM        → enrich top 5 results with PMJAY empanelment
  4. Ranker      → score hospitals by distance × type × triage × insurance
  5. Redis       → 24h cache on 1 km GPS grid cell
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

import structlog

from app.core.config import settings
from app.schemas.schemas import HospitalListResponse, HospitalResult
from app.services.care.overpass import (
    query_overpass,
    reverse_geocode,
    haversine_km,
)
from app.services.care.abdm import enrich_with_empanelment
from app.services.care.ranker import score_hospitals
from app.services.care.esanjeevani import get_available_slots, book_slot

logger = structlog.get_logger(__name__)


def _fallback_hospitals(lat: float, lng: float) -> list[dict]:
    return [
        {
            "osm_id":        "fallback_1",
            "name":          "Nearest Primary Health Centre",
            "hospital_type": "phc",
            "address":       "Contact ASHA worker for directions",
            "distance_km":   0.0,
            "phone":         "108",
            "ambulance_108": True,
            "open_24h":      False,
            "pmjay_empanelled": True,
            "latitude":      lat,
            "longitude":     lng,
        }
    ]


async def find_nearby_hospitals(
    lat:          float,
    lng:          float,
    radius_m:     int = 50_000,
    specialty:    Optional[str] = None,
    triage_level: int = 2,
    pmjay_eligible: bool = False,
    redis=None,
) -> HospitalListResponse:
    """
    Find, enrich, and rank nearby hospitals.

    Pipeline:
      1. Cache check (1 km grid, 24h TTL)
      2. Overpass → raw OSM facilities
      3. Nominatim → district/state for patient location
      4. ABDM → PMJAY empanelment on top 10 results (parallel)
      5. Ranker → composite score for triage level + insurance
      6. Cache store
    """
    # ── Stage 1: cache ────────────────────────────────────────────────────────
    grid_lat  = round(lat, 2)
    grid_lng  = round(lng, 2)
    cache_key = f"hospitals:{grid_lat}:{grid_lng}:{radius_m}:{specialty or 'all'}"

    if redis:
        cached = await redis.get(cache_key)
        if cached:
            logger.debug("vaidya.care.cache_hit")
            return HospitalListResponse(**json.loads(cached))

    # ── Stage 2: Overpass OSM query ───────────────────────────────────────────
    facilities = await query_overpass(lat, lng, radius_m, specialty)

    if not facilities:
        logger.warning("vaidya.care.overpass_empty", lat=lat, lng=lng)
        facilities = _fallback_hospitals(lat, lng)

    # ── Stage 3: Nominatim reverse geocode ────────────────────────────────────
    geo = await reverse_geocode(lat, lng)
    district = geo.get("district", "")
    state    = geo.get("state", "")

    # ── Stage 4: ABDM empanelment enrichment (top 10 only — async parallel) ──
    state_code = _state_name_to_code(state)
    facilities = await enrich_with_empanelment(facilities[:10], state_code=state_code)

    # ── Stage 5: Rank by composite score ─────────────────────────────────────
    ranked = score_hospitals(
        hospitals=facilities,
        triage_level=triage_level,
        pmjay_eligible=pmjay_eligible,
        max_results=10,
    )

    logger.info(
        "vaidya.care.hospitals_ranked",
        count=len(ranked),
        district=district,
        triage=triage_level,
    )

    # ── Stage 6: Build response and cache ─────────────────────────────────────
    response = HospitalListResponse(
        results=[
            HospitalResult(id=uuid.uuid4(), **{
                k: v for k, v in h.items()
                if k in HospitalResult.model_fields
            })
            for h in ranked
        ],
        total=len(ranked),
        patient_location={
            "lat":      lat,
            "lng":      lng,
            "district": district,
            "state":    state,
        },
    )

    if redis:
        await redis.setex(
            cache_key,
            settings.REDIS_TTL_HOSPITALS,
            response.model_dump_json(),
        )

    return response


# ── State name → ISO code (Nominatim returns full names) ─────────────────────

_STATE_NAME_TO_CODE: dict[str, str] = {
    "andhra pradesh":    "AP",
    "arunachal pradesh": "AR",
    "assam":             "AS",
    "bihar":             "BR",
    "chhattisgarh":      "CG",
    "goa":               "GA",
    "gujarat":           "GJ",
    "haryana":           "HR",
    "himachal pradesh":  "HP",
    "jharkhand":         "JH",
    "karnataka":         "KA",
    "kerala":            "KL",
    "madhya pradesh":    "MP",
    "maharashtra":       "MH",
    "manipur":           "MN",
    "meghalaya":         "ML",
    "mizoram":           "MZ",
    "nagaland":          "NL",
    "odisha":            "OR",
    "punjab":            "PB",
    "rajasthan":         "RJ",
    "sikkim":            "SK",
    "tamil nadu":        "TN",
    "telangana":         "TS",
    "tripura":           "TR",
    "uttar pradesh":     "UP",
    "uttarakhand":       "UK",
    "west bengal":       "WB",
    "delhi":             "DL",
    "jammu and kashmir": "JK",
    "ladakh":            "LA",
}


def _state_name_to_code(name: str) -> Optional[str]:
    return _STATE_NAME_TO_CODE.get(name.lower().strip()) if name else None
