"""
Vaidya — Care routing service (Module 7 — complete)

Orchestrates:
  1. Google Places API → fast (~200ms), reliable hospital search  [PRIMARY]
  2. Overpass API      → OSM fallback if Google Places unavailable  [SECONDARY]
  3. Static DB         → bundled Chennai hospital list              [TERTIARY]
  4. Nominatim         → reverse geocode patient GPS → district/state
  5. ABDM              → enrich top 5 results with PMJAY empanelment
  6. Ranker            → score by distance × type × triage × insurance
  7. Redis             → 24h cache on 1 km GPS grid cell
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

import structlog

from app.core.config import settings
from app.schemas.schemas import HospitalListResponse, HospitalResult
from app.services.care.overpass import (
    query_overpass,
    reverse_geocode,
    haversine_km,
)
from app.services.care.google_places import query_google_places
from app.services.care.abdm import enrich_with_empanelment
from app.services.care.ranker import score_hospitals
from app.services.care.esanjeevani import get_available_slots, book_slot

logger = structlog.get_logger(__name__)

_STATIC_DB_PATH = Path(__file__).parent.parent.parent / "data" / "hospitals_static.json"
_static_hospitals: list[dict] | None = None


def _load_static_hospitals() -> list[dict]:
    global _static_hospitals
    if _static_hospitals is not None:
        return _static_hospitals
    try:
        with open(_STATIC_DB_PATH, encoding="utf-8") as f:
            _static_hospitals = json.load(f).get("hospitals", [])
        logger.info("vaidya.care.static_db_loaded", count=len(_static_hospitals))
    except Exception as exc:
        logger.warning("vaidya.care.static_db_load_failed", error=str(exc))
        _static_hospitals = []
    return _static_hospitals


def _static_hospitals_near(lat: float, lng: float, radius_m: int, specialty: Optional[str] = None) -> list[dict]:
    result = []
    for h in _load_static_hospitals():
        dist_km = haversine_km(lat, lng, h["latitude"], h["longitude"])
        if dist_km * 1000 <= radius_m:
            result.append({
                "osm_id":          h.get("id", "static"),
                "name":            h["name"],
                "hospital_type":   h.get("hospital_type", "other"),
                "address":         h.get("address"),
                "distance_km":     round(dist_km, 2),
                "phone":           h.get("phone"),
                "ambulance_108":   h.get("ambulance_108", False),
                "open_24h":        h.get("open_24h", False),
                "pmjay_empanelled":h.get("pmjay_empanelled", False),
                "latitude":        h["latitude"],
                "longitude":       h["longitude"],
            })
    return result


def _fallback_hospitals(lat: float, lng: float) -> list[dict]:
    # Return empty — frontend shows "no hospitals found" instead of a fake pin in the sea.
    return []


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

    # ── Stage 2: Google Places (primary — fast) ───────────────────────────────
    facilities = await query_google_places(lat, lng, radius_m, specialty)

    # ── Stage 3: Overpass fallback if Places returned nothing ─────────────────
    if not facilities:
        logger.info("vaidya.care.places_empty_trying_overpass", lat=lat, lng=lng)
        facilities = await query_overpass(lat, lng, radius_m, specialty)

    # ── Stage 4: Static DB if both live sources failed ─────────────────────────
    if not facilities:
        logger.warning("vaidya.care.live_sources_empty", lat=lat, lng=lng)
        static = _static_hospitals_near(lat, lng, radius_m, specialty)
        if static:
            logger.info("vaidya.care.using_static_db", count=len(static), lat=lat, lng=lng)
            facilities = static
        else:
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
