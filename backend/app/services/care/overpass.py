"""
Vaidya — Overpass API (OpenStreetMap) hospital finder

Queries the public Overpass API for healthcare facilities within a GPS radius.
Uses Nominatim for reverse geocoding (lat/lng → district/block).

Design decisions:
  - Two mirror URLs with fallback (overpass-api.de / overpass.kumi.systems)
    because overpass-api.de has ~2% downtime; kumi.systems is a European mirror
  - 1 km GPS grid cell for cache keys: hospitals at 12.9716°N and 12.9720°N
    are close enough to share the same cached result
  - Govt-first sorting: PHC → CHC → District → ESIC → Private
    mirrors NHA priority guidelines for rural triage
  - 108 ambulance detection: checks OSM tags, phone numbers, name string
  - PMJAY empanelment: annotated from ABDM lookup (async, done separately)
"""

from __future__ import annotations

import math
import re
from typing import Optional

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ── Overpass mirrors (failover order) ─────────────────────────────────────────
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# ── Hospital type priority (lower = higher priority in sort) ──────────────────
TYPE_PRIORITY: dict[str, int] = {
    "phc":      0,
    "chc":      1,
    "district": 2,
    "esic":     3,
    "private":  4,
    "other":    5,
}

# ── Overpass QL query ─────────────────────────────────────────────────────────
# Fetches:  hospital nodes + ways, clinics, healthcare centres, PHCs
# "out body center" gives centre coords for ways (not just bounding box)
OVERPASS_QL = """\
[out:json][timeout:28];
(
  node["amenity"="hospital"](around:{radius},{lat},{lng});
  node["amenity"="clinic"](around:{radius},{lat},{lng});
  node["healthcare"="centre"](around:{radius},{lat},{lng});
  node["healthcare"="hospital"](around:{radius},{lat},{lng});
  node["name"~"PHC|Primary Health|CHC|Community Health|District Hospital",i]\
(around:{radius},{lat},{lng});
  way["amenity"="hospital"](around:{radius},{lat},{lng});
  way["amenity"="clinic"](around:{radius},{lat},{lng});
);
out body center 50;
"""


# ── Haversine distance ────────────────────────────────────────────────────────

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lng2 - lng1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Facility type classifier ──────────────────────────────────────────────────

def classify_facility_type(tags: dict) -> str:
    """
    Classify an OSM facility into one of: phc, chc, district, esic, private, other.
    Uses name, operator, and healthcare tags in priority order.
    """
    name     = (tags.get("name", "") + " " + tags.get("name:en", "")).lower()
    operator = tags.get("operator", "").lower()
    hc       = tags.get("healthcare", "").lower()
    amenity  = tags.get("amenity", "").lower()

    # Government / public sector patterns
    if re.search(r"\bphc\b|primary\s+health\s+cent", name):
        return "phc"
    if re.search(r"\bchc\b|community\s+health\s+cent", name):
        return "chc"
    if re.search(r"district\s+hospital|govt|government\s+hospital", name):
        return "district"
    if re.search(r"\besic\b|employees.*state.*insurance", name + " " + operator):
        return "esic"
    # Operator-based (covers cases where name doesn't contain the type)
    if re.search(r"government|govt|nhs|phc|chc|ministry\s+of\s+health", operator):
        return "district"
    if hc == "centre" or amenity == "clinic":
        return "phc"    # treat generic centres as PHC-level
    if amenity == "hospital":
        return "private"  # if no govt markers → private
    return "other"


def has_108_ambulance(tags: dict) -> bool:
    """Detect 108 ambulance availability from OSM tags."""
    phone    = tags.get("phone", "") + " " + tags.get("contact:phone", "")
    name     = tags.get("name", "").lower()
    services = tags.get("healthcare:speciality", "").lower()
    return "108" in phone or "ambulance" in name or "ambulance" in services


def is_24h(tags: dict) -> bool:
    oh = tags.get("opening_hours", "")
    return oh in ("24/7", "Mo-Su 00:00-24:00", "24/7; PH off")


def extract_address(tags: dict) -> Optional[str]:
    """Build a readable address from OSM addr:* tags."""
    parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
        tags.get("addr:suburb", ""),
        tags.get("addr:city", "") or tags.get("addr:town", "") or tags.get("addr:village", ""),
        tags.get("addr:postcode", ""),
    ]
    addr = ", ".join(p for p in parts if p)
    return addr or tags.get("addr:full") or None


# ── Overpass query with mirror failover ───────────────────────────────────────

async def query_overpass(
    lat: float,
    lng: float,
    radius_m: int,
    specialty: Optional[str] = None,
) -> list[dict]:
    """
    Query Overpass API for healthcare facilities.
    Tries each mirror in order, returns raw parsed facility list on success.
    Falls back to empty list (caller handles fallback display).
    """
    ql = OVERPASS_QL.format(lat=lat, lng=lng, radius=radius_m)

    for mirror in OVERPASS_MIRRORS:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    mirror,
                    content=f"data={ql}",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                osm = resp.json()
                logger.debug(
                    "vaidya.overpass.ok",
                    mirror=mirror,
                    elements=len(osm.get("elements", [])),
                )
                return _parse_overpass(osm, lat, lng, specialty)

        except httpx.TimeoutException:
            logger.warning("vaidya.overpass.timeout", mirror=mirror)
        except httpx.HTTPStatusError as e:
            logger.warning("vaidya.overpass.http_error", status=e.response.status_code, mirror=mirror)
        except Exception as exc:
            logger.error("vaidya.overpass.error", mirror=mirror, error=str(exc))

    logger.error("vaidya.overpass.all_mirrors_failed")
    return []


def _parse_overpass(osm: dict, lat: float, lng: float, specialty: Optional[str]) -> list[dict]:
    """Convert raw Overpass JSON elements → normalised facility dicts."""
    facilities = []
    seen_names: set[str] = set()   # deduplicate by (name, rounded coords)

    for el in osm.get("elements", []):
        tags = el.get("tags", {})
        name = (tags.get("name") or tags.get("name:en") or "").strip()
        if not name:
            continue

        # Coordinates: node has lat/lon directly; way has center
        if el["type"] == "node":
            h_lat, h_lng = el["lat"], el["lon"]
        else:
            c = el.get("center", {})
            h_lat = c.get("lat", lat)
            h_lng = c.get("lon", lng)

        # Dedup key
        dedup = f"{name.lower()[:30]}:{round(h_lat, 3)}:{round(h_lng, 3)}"
        if dedup in seen_names:
            continue
        seen_names.add(dedup)

        # Specialty filter
        if specialty:
            spec_tag = tags.get("healthcare:speciality", "")
            if specialty.lower() not in spec_tag.lower():
                continue

        facilities.append({
            "osm_id":        str(el.get("id", "")),
            "name":          name,
            "hospital_type": classify_facility_type(tags),
            "address":       extract_address(tags),
            "distance_km":   round(haversine_km(lat, lng, h_lat, h_lng), 2),
            "phone":         tags.get("phone") or tags.get("contact:phone"),
            "ambulance_108": has_108_ambulance(tags),
            "open_24h":      is_24h(tags),
            "pmjay_empanelled": False,   # populated by ABDM lookup
            "latitude":      h_lat,
            "longitude":     h_lng,
        })

    return facilities


# ── Nominatim reverse geocoding ───────────────────────────────────────────────

async def reverse_geocode(lat: float, lng: float) -> dict:
    """
    Convert GPS coordinates → structured address (district, block, state, pin).
    Uses Nominatim (OpenStreetMap). Free, no API key needed.
    Nominatim ToS: max 1 req/sec, include User-Agent.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.NOMINATIM_URL}/reverse",
                params={
                    "lat":            lat,
                    "lon":            lng,
                    "format":         "jsonv2",
                    "addressdetails": 1,
                    "zoom":           13,    # block-level detail
                    "accept-language": "en",
                },
                headers={"User-Agent": "Vaidya/1.0 (AI health triage, rural India; contact@vaidya.health)"},
            )
            resp.raise_for_status()
            data = resp.json()
            addr = data.get("address", {})
            return {
                "display_name": data.get("display_name", ""),
                "village":   addr.get("village") or addr.get("hamlet") or addr.get("suburb"),
                "block":     addr.get("county") or addr.get("municipality"),
                "district":  addr.get("state_district") or addr.get("district"),
                "state":     addr.get("state"),
                "postcode":  addr.get("postcode"),
                "country":   addr.get("country_code", "").upper(),
            }
    except Exception as exc:
        logger.warning("vaidya.nominatim.failed", lat=lat, lng=lng, error=str(exc))
        return {"district": "", "state": "", "display_name": ""}
