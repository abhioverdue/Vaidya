"""
Vaidya — Google Places API hospital finder

Replaces Overpass as the primary hospital source.
~100-300ms vs Overpass ~5-28s. Uses the same Google Maps API key as the frontend.

Endpoint: Places Nearby Search v1 (legacy JSON API — no billing account needed for basic results)
Parallel requests for "hospital" type + "PHC clinic health centre" keyword to cover
government facilities that Google doesn't tag as hospital.
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

PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"


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
    if re.search(r"government|govt|ggh|stanley|kilpauk|royapettah|kasturba", n):
        return "district"
    if "hospital" in types or "emergency_room" in types:
        return "private"
    return "phc"


async def _fetch_places(client: httpx.AsyncClient, params: dict) -> list[dict]:
    try:
        resp = await client.get(PLACES_NEARBY_URL, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "")
        if status not in ("OK", "ZERO_RESULTS"):
            logger.warning("vaidya.places.bad_status", status=status)
            return []
        return data.get("results", [])
    except Exception as exc:
        logger.warning("vaidya.places.fetch_failed", error=str(exc))
        return []


async def query_google_places(
    lat: float,
    lng: float,
    radius_m: int,
    specialty: Optional[str] = None,
) -> list[dict]:
    """
    Query Google Places Nearby Search for healthcare facilities.
    Makes two parallel requests:
      1. type=hospital  — picks up hospitals, nursing homes, etc.
      2. keyword search — picks up PHCs, CHCs, clinics Google doesn't tag as hospital
    Returns normalised facility dicts matching the Overpass output schema.
    """
    key = settings.GOOGLE_MAPS_API_KEY
    if not key:
        return []

    radius = min(radius_m, 50_000)  # Places API cap at 50km
    base_params = {
        "location": f"{lat},{lng}",
        "radius":   radius,
        "key":      key,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        results_hosp, results_phc = await asyncio.gather(
            _fetch_places(client, {**base_params, "type": "hospital"}),
            _fetch_places(client, {**base_params, "keyword": "PHC primary health centre clinic health centre"}),
        )

    facilities: list[dict] = []
    seen: set[str] = set()

    for place in results_hosp + results_phc:
        pid = place.get("place_id", "")
        if pid in seen:
            continue
        seen.add(pid)

        loc  = place.get("geometry", {}).get("location", {})
        h_lat = loc.get("lat", lat)
        h_lng = loc.get("lng", lng)
        name  = place.get("name", "").strip()
        if not name:
            continue

        types    = place.get("types", [])
        hosp_type = _classify_type(name, types)
        oh        = place.get("opening_hours", {})

        facilities.append({
            "osm_id":          pid,
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
        })

    logger.info(
        "vaidya.places.ok",
        count=len(facilities),
        radius_km=round(radius / 1000),
    )
    return facilities
