"""
Vaidya — Google Places (New) API hospital finder

Uses the Places API (New) v1 — more comprehensive than legacy, returns PHCs/CHCs
that the old nearbysearch often missed. Three parallel searches:
  1. includedTypes: ["hospital"]
  2. includedTypes: ["health", "doctor", "pharmacy"]
  3. textQuery: "primary health centre PHC CHC community health centre" near location

Legacy fallback is retained if the New API returns nothing (quota / billing edge cases).
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

import httpx
import structlog

from app.core.config import settings
from app.services.care.overpass import haversine_km

logger = structlog.get_logger(__name__)

# New Places API (v1)
PLACES_NEW_URL  = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
# Legacy fallback
PLACES_LEGACY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

_NEW_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.types,places.regularOpeningHours,"
    "places.rating,places.nationalPhoneNumber,places.businessStatus"
)


def _classify_type(name: str, types: list[str]) -> str:
    n = name.lower()
    if re.search(r"\bphc\b|primary\s+health\s+cent", n):
        return "phc"
    if re.search(r"\bchc\b|community\s+health\s+cent", n):
        return "chc"
    if re.search(r"district\s+hosp|govt\s+hosp|government\s+hosp|rajiv\s+gandhi|general\s+hosp", n):
        return "district"
    if re.search(r"\besic\b", n):
        return "esic"
    if re.search(r"government|govt|ggh|stanley|kilpauk|royapettah|kasturba|civil\s+hosp", n):
        return "district"
    if any(t in types for t in ("hospital", "emergency_room")):
        return "private"
    return "other"


# ── New API helpers ────────────────────────────────────────────────────────────

async def _fetch_new_nearby(
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
                "radius": float(radius),
            }
        },
        "rankPreference": "DISTANCE",
    }
    headers = {
        "X-Goog-Api-Key":     key,
        "X-Goog-FieldMask":   _NEW_FIELD_MASK,
        "Content-Type":       "application/json",
    }
    try:
        resp = await client.post(PLACES_NEW_URL, json=body, headers=headers, timeout=8)
        resp.raise_for_status()
        return resp.json().get("places", [])
    except Exception as exc:
        logger.warning("vaidya.places.new_fetch_failed", types=included_types, error=str(exc))
        return []


async def _fetch_new_text(
    client: httpx.AsyncClient,
    key: str,
    lat: float,
    lng: float,
    radius: float,
) -> list[dict]:
    body = {
        "textQuery": "primary health centre PHC CHC community health centre clinic",
        "maxResultCount": 20,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius),
            }
        },
    }
    headers = {
        "X-Goog-Api-Key":   key,
        "X-Goog-FieldMask": _NEW_FIELD_MASK,
        "Content-Type":     "application/json",
    }
    try:
        resp = await client.post(PLACES_TEXT_URL, json=body, headers=headers, timeout=8)
        resp.raise_for_status()
        return resp.json().get("places", [])
    except Exception as exc:
        logger.warning("vaidya.places.text_fetch_failed", error=str(exc))
        return []


def _norm_new(place: dict, lat: float, lng: float) -> dict | None:
    loc  = place.get("location", {})
    h_lat = loc.get("latitude", lat)
    h_lng = loc.get("longitude", lng)
    name  = place.get("displayName", {}).get("text", "").strip()
    if not name:
        return None
    types    = place.get("types", [])
    hosp_type = _classify_type(name, types)
    oh = place.get("regularOpeningHours", {})
    return {
        "osm_id":          place.get("id", ""),
        "name":            name,
        "hospital_type":   hosp_type,
        "address":         place.get("formattedAddress", ""),
        "distance_km":     round(haversine_km(lat, lng, h_lat, h_lng), 2),
        "phone":           place.get("nationalPhoneNumber"),
        "ambulance_108":   False,
        "open_24h":        oh.get("openNow", False),
        "pmjay_empanelled":hosp_type in ("phc", "chc", "district", "esic"),
        "latitude":        h_lat,
        "longitude":       h_lng,
        "rating":          place.get("rating"),
    }


# ── Legacy API fallback ────────────────────────────────────────────────────────

async def _fetch_legacy(client: httpx.AsyncClient, params: dict) -> list[dict]:
    try:
        resp = await client.get(PLACES_LEGACY_URL, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            logger.warning("vaidya.places.legacy_bad_status", status=data.get("status"))
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
    oh = place.get("opening_hours", {})
    return {
        "osm_id":          place.get("place_id", ""),
        "name":            name,
        "hospital_type":   hosp_type,
        "address":         place.get("vicinity", ""),
        "distance_km":     round(haversine_km(lat, lng, h_lat, h_lng), 2),
        "phone":           None,
        "ambulance_108":   False,
        "open_24h":        oh.get("open_now", False),
        "pmjay_empanelled":hosp_type in ("phc", "chc", "district", "esic"),
        "latitude":        h_lat,
        "longitude":       h_lng,
        "rating":          place.get("rating"),
    }


# ── Main entry point ───────────────────────────────────────────────────────────

async def query_google_places(
    lat: float,
    lng: float,
    radius_m: int,
    specialty: Optional[str] = None,
) -> list[dict]:
    """
    Query Google Places (New) for healthcare facilities.
    Three parallel requests → deduped → sorted by distance.
    Falls back to legacy nearbysearch if New API returns nothing.
    """
    key = settings.GOOGLE_MAPS_API_KEY
    if not key:
        return []

    radius = float(min(radius_m, 50_000))

    async with httpx.AsyncClient(timeout=10) as client:
        hosp_raw, health_raw, text_raw = await asyncio.gather(
            _fetch_new_nearby(client, key, lat, lng, radius, ["hospital"]),
            _fetch_new_nearby(client, key, lat, lng, radius, ["health", "doctor"]),
            _fetch_new_text(client, key, lat, lng, radius),
        )

    facilities: list[dict] = []
    seen: set[str] = set()

    for place in hosp_raw + health_raw + text_raw:
        pid = place.get("id", "")
        if pid in seen:
            continue
        seen.add(pid)
        norm = _norm_new(place, lat, lng)
        if norm:
            facilities.append(norm)

    # Legacy fallback if new API returned nothing
    if not facilities:
        logger.info("vaidya.places.new_empty_trying_legacy", lat=lat, lng=lng)
        base = {"location": f"{lat},{lng}", "radius": int(radius), "key": key}
        async with httpx.AsyncClient(timeout=10) as client:
            leg_hosp, leg_phc = await asyncio.gather(
                _fetch_legacy(client, {**base, "type": "hospital"}),
                _fetch_legacy(client, {**base, "keyword": "PHC primary health centre clinic"}),
            )
        leg_seen: set[str] = set()
        for place in leg_hosp + leg_phc:
            pid = place.get("place_id", "")
            if pid in leg_seen:
                continue
            leg_seen.add(pid)
            norm = _norm_legacy(place, lat, lng)
            if norm:
                facilities.append(norm)

    facilities.sort(key=lambda h: h["distance_km"])

    logger.info("vaidya.places.ok", count=len(facilities), radius_km=round(radius / 1000))
    return facilities
