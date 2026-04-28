"""
Vaidya — Google Places (New) API hospital finder

Strategy: 6 parallel requests → dedup → classify → sort by distance.
  Nearby search (hard radius boundary):
    1. includedTypes: ["hospital", "emergency_room_hospital"]   — private & govt hospitals
    2. includedTypes: ["health", "doctor"]                      — clinics, PHCs, dispensaries
  Text search (locationBias — soft preference, catches what type-search misses):
    3. "PHC primary health centre sub-centre dispensary"        — rural govt primaries
    4. "CHC community health centre urban health centre"        — community tier
    5. "district hospital government hospital taluk hospital SDH" — district tier
    6. "ESIC hospital ESI dispensary maternity hospital MCH"    — specialty govt

Legacy nearbysearch (old API) is kept as inner fallback if New API returns 0.

Classification covers all common Indian naming conventions:
  PHC      — PHC, primary health centre, sub-centre, UHC, dispensary, health sub-centre,
             health post, maternity home, UPHC
  CHC      — CHC, community health centre, urban health centre
  District — district hospital, govt/government hospital, general hospital, taluk hospital,
             SDH, GH, GGH, civil hospital, rajiv gandhi, war memorial, medical college
             hospital, teaching hospital, apex hospital, zonal hospital, regional hospital
  ESIC     — ESIC, ESI, employees state insurance
  Private  — everything else tagged as hospital / nursing home / clinic
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Optional

import httpx
import structlog

from app.core.config import settings
from app.services.care.overpass import haversine_km

logger = structlog.get_logger(__name__)

PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_TEXT_URL   = "https://places.googleapis.com/v1/places:searchText"
PLACES_LEGACY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.types,places.regularOpeningHours,"
    "places.rating,places.nationalPhoneNumber,places.businessStatus"
)

# ── Text queries — one per facility tier ──────────────────────────────────────
_TEXT_QUERIES = [
    "PHC primary health centre sub-centre health sub-centre dispensary UPHC urban primary health centre",
    "CHC community health centre urban health centre UHC",
    "district hospital government hospital taluk hospital sub-district hospital SDH GH GGH civil hospital general hospital",
    "ESIC hospital ESI dispensary maternity hospital MCH government maternity home",
]

# ── Classification ─────────────────────────────────────────────────────────────

# Pre-compiled patterns for speed
_PHC_RE = re.compile(
    r"\bphc\b"
    r"|\buphc\b"
    r"|primary\s+health\s+(cent|sub)"
    r"|health\s+sub.?cent"
    r"|\bsub.?cent(re|er)?\b"
    r"|\bdispensary\b"
    r"|\buhc\b"
    r"|urban\s+primary\s+health"
    r"|urban\s+health\s+cent"
    r"|\bsub-centre\b"
    r"|health\s+post\b"
    r"|maternity\s+(home|centre|center)\b"
    r"|\banm\s+sub.?cent"                 # ANM sub-centres
    r"|health\s+and\s+wellness\s+cent",   # Ayushman Arogya Mandirs
    re.I,
)

_CHC_RE = re.compile(
    r"\bchc\b"
    r"|community\s+health\s+cent"
    r"|urban\s+community\s+health",
    re.I,
)

_ESIC_RE = re.compile(
    r"\besic\b|\besi\b|employees.?state\s+insurance",
    re.I,
)

_DISTRICT_RE = re.compile(
    r"\bdistrict\s+hosp"
    r"|\bgovt\.?\s+hosp"
    r"|\bgovernment\s+hosp"
    r"|\bgeneral\s+hosp"
    r"|\btaluk\s+hosp"
    r"|\btaluka\s+hosp"
    r"|\bsub.?district\s+hosp"
    r"|\bsdh\b"
    r"|\bgh\b"
    r"|\bggh\b"
    r"|\bcivil\s+hosp"
    r"|\bzonal\s+hosp"
    r"|\bregional\s+hosp"
    r"|\bapex\s+hosp"
    r"|\bteaching\s+hosp"
    r"|\breferral\s+hosp"
    r"|medical\s+college\s+(hosp|and)"
    r"|\bgovt\.?\s+med"
    r"|\bgovernment\s+med"
    # Well-known Tamil Nadu / pan-India govt hospital names
    r"|stanley\b|kilpauk\b|royapettah\b|kasturba\b"
    r"|rajiv\s+gandhi"
    r"|war\s+memorial\s+hosp"
    r"|safdarjung\b|aiims\b|pgimer\b|nimhans\b"
    r"|lady\s+hardinge\b|lok\s+nayak\b"
    r"|\bprimary\s+hosp\b"               # "Primary Hospital" is a govt tier in some states
    r"|government|govt\b",
    re.I,
)


def _classify_type(name: str, types: list[str]) -> str:
    """
    Return one of: phc | chc | district | esic | private | other

    Order matters — check more-specific patterns before broader ones.
    ESIC is pulled out of the district block explicitly.
    """
    # 1. PHC / primary tier (most specific rural govt)
    if _PHC_RE.search(name):
        return "phc"

    # 2. CHC / community tier
    if _CHC_RE.search(name):
        return "chc"

    # 3. ESIC (check before district so "ESIC Hospital" doesn't land in district)
    if _ESIC_RE.search(name):
        return "esic"

    # 4. District / government / medical-college tier
    if _DISTRICT_RE.search(name):
        return "district"

    # 5. Private — anything Google itself tags as hospital
    if any(t in types for t in ("hospital", "emergency_room_hospital")):
        return "private"

    return "other"


# ── New API helpers ────────────────────────────────────────────────────────────

async def _nearby(
    client: httpx.AsyncClient,
    key: str,
    lat: float,
    lng: float,
    radius: float,
    included_types: list[str],
) -> list[dict]:
    body = {
        "includedTypes": included_types,
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius,
            }
        },
        "rankPreference": "DISTANCE",
    }
    try:
        r = await client.post(
            PLACES_NEARBY_URL,
            json=body,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": _FIELD_MASK},
            timeout=8,
        )
        r.raise_for_status()
        return r.json().get("places", [])
    except Exception as exc:
        logger.warning("vaidya.places.nearby_failed", types=included_types, error=str(exc))
        return []


async def _text(
    client: httpx.AsyncClient,
    key: str,
    lat: float,
    lng: float,
    radius: float,
    query: str,
) -> list[dict]:
    body = {
        "textQuery": query,
        "maxResultCount": 20,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius,
            }
        },
    }
    try:
        r = await client.post(
            PLACES_TEXT_URL,
            json=body,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": _FIELD_MASK},
            timeout=8,
        )
        r.raise_for_status()
        return r.json().get("places", [])
    except Exception as exc:
        logger.warning("vaidya.places.text_failed", query=query[:40], error=str(exc))
        return []


def _norm_new(place: dict, lat: float, lng: float) -> dict | None:
    loc   = place.get("location", {})
    h_lat = loc.get("latitude", lat)
    h_lng = loc.get("longitude", lng)
    name  = place.get("displayName", {}).get("text", "").strip()
    if not name:
        return None
    if place.get("businessStatus") == "CLOSED_PERMANENTLY":
        return None
    types     = place.get("types", [])
    hosp_type = _classify_type(name, types)
    oh        = place.get("regularOpeningHours", {})
    return {
        "osm_id":           place.get("id", ""),
        "name":             name,
        "hospital_type":    hosp_type,
        "address":          place.get("formattedAddress", ""),
        "distance_km":      round(haversine_km(lat, lng, h_lat, h_lng), 2),
        "phone":            place.get("nationalPhoneNumber"),
        "ambulance_108":    False,
        "open_24h":         oh.get("openNow", False),
        "pmjay_empanelled": hosp_type in ("phc", "chc", "district", "esic"),
        "latitude":         h_lat,
        "longitude":        h_lng,
        "rating":           place.get("rating"),
    }


# ── Legacy fallback ────────────────────────────────────────────────────────────

async def _legacy(client: httpx.AsyncClient, params: dict) -> list[dict]:
    try:
        r = await client.get(PLACES_LEGACY_URL, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            return []
        return data.get("results", [])
    except Exception as exc:
        logger.warning("vaidya.places.legacy_failed", error=str(exc))
        return []


def _norm_legacy(place: dict, lat: float, lng: float) -> dict | None:
    loc   = place.get("geometry", {}).get("location", {})
    h_lat = loc.get("lat", lat)
    h_lng = loc.get("lng", lng)
    name  = place.get("name", "").strip()
    if not name:
        return None
    types     = place.get("types", [])
    hosp_type = _classify_type(name, types)
    oh        = place.get("opening_hours", {})
    return {
        "osm_id":           place.get("place_id", ""),
        "name":             name,
        "hospital_type":    hosp_type,
        "address":          place.get("vicinity", ""),
        "distance_km":      round(haversine_km(lat, lng, h_lat, h_lng), 2),
        "phone":            None,
        "ambulance_108":    False,
        "open_24h":         oh.get("open_now", False),
        "pmjay_empanelled": hosp_type in ("phc", "chc", "district", "esic"),
        "latitude":         h_lat,
        "longitude":        h_lng,
        "rating":           place.get("rating"),
    }


# ── Main entry ────────────────────────────────────────────────────────────────

async def query_google_places(
    lat: float,
    lng: float,
    radius_m: int,
    specialty: Optional[str] = None,
) -> list[dict]:
    """
    Run 6 parallel Google Places requests (2 nearby + 4 text) to maximise
    coverage of PHCs, CHCs, district hospitals, and ESIC facilities.
    Deduplicates by place ID, drops permanently-closed places, sorts by distance.
    Falls back to legacy nearbysearch if New API returns 0 results.
    """
    key = settings.GOOGLE_MAPS_API_KEY
    if not key:
        return []

    radius = float(min(radius_m, 50_000))

    async with httpx.AsyncClient(timeout=10) as client:
        results = await asyncio.gather(
            # Nearby — typed (hard radius boundary)
            _nearby(client, key, lat, lng, radius, ["hospital", "emergency_room_hospital"]),
            _nearby(client, key, lat, lng, radius, ["health", "doctor"]),
            # Text — one query per facility tier (soft locationBias)
            *[_text(client, key, lat, lng, radius, q) for q in _TEXT_QUERIES],
        )

    facilities: list[dict] = []
    seen: set[str] = set()

    for batch in results:
        for place in batch:
            pid = place.get("id", "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            norm = _norm_new(place, lat, lng)
            if norm:
                facilities.append(norm)

    # ── Legacy fallback ───────────────────────────────────────────────────────
    if not facilities:
        logger.info("vaidya.places.new_zero_trying_legacy", lat=lat, lng=lng)
        base = {"location": f"{lat},{lng}", "radius": int(radius), "key": key}
        async with httpx.AsyncClient(timeout=10) as client:
            leg_a, leg_b, leg_c = await asyncio.gather(
                _legacy(client, {**base, "type": "hospital"}),
                _legacy(client, {**base, "keyword": "PHC primary health centre dispensary"}),
                _legacy(client, {**base, "keyword": "district hospital government hospital taluk"}),
            )
        leg_seen: set[str] = set()
        for place in leg_a + leg_b + leg_c:
            pid = place.get("place_id", "")
            if not pid or pid in leg_seen:
                continue
            leg_seen.add(pid)
            norm = _norm_legacy(place, lat, lng)
            if norm:
                facilities.append(norm)

    facilities.sort(key=lambda h: h["distance_km"])

    type_counts = Counter(f["hospital_type"] for f in facilities)
    logger.info(
        "vaidya.places.complete",
        total=len(facilities),
        phc=type_counts.get("phc", 0),
        chc=type_counts.get("chc", 0),
        district=type_counts.get("district", 0),
        esic=type_counts.get("esic", 0),
        private=type_counts.get("private", 0),
        other=type_counts.get("other", 0),
        radius_km=round(radius / 1000),
    )
    return facilities