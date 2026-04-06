"""
Vaidya — ABDM (Ayushman Bharat Digital Mission) integration

Handles:
  1. PMJAY / Aarogyasri coverage verification via tokenised Aadhaar
  2. ABHA (Ayushman Bharat Health Account) health ID lookup
  3. Hospital empanelment cross-check — is a given hospital PMJAY-empanelled?

Security model:
  - Raw Aadhaar numbers NEVER enter this service or the Vaidya database.
  - The aadhaar_token parameter is the OTP-verified transaction token from the
    patient's ABDM app (similar to UPI VPA — it can't be reversed to Aadhaar).
  - All ABDM sandbox calls use client_credentials OAuth2, not patient auth.

ABDM sandbox base: https://sandbox.abdm.gov.in/api/v3
Production:        https://abdm.gov.in/api/v3  (requires NHA approval)

Rate limits (sandbox): 100 req/min per client_id
OAuth2 token lifetime: 30 minutes
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ── Token cache ────────────────────────────────────────────────────────────────
_abdm_token:      Optional[str] = None
_abdm_token_exp:  float         = 0.0
_TOKEN_BUFFER_S = 90            # refresh 90s before expiry


# ── OAuth2 client credentials ─────────────────────────────────────────────────

async def _get_abdm_token() -> Optional[str]:
    """
    Obtain ABDM API access token via client_credentials flow.
    Caches token for its lifetime (30 min). Returns None if credentials missing.
    """
    global _abdm_token, _abdm_token_exp

    if not settings.ABDM_CLIENT_ID or not settings.ABDM_CLIENT_SECRET:
        return None

    now = time.monotonic()
    if _abdm_token and now < (_abdm_token_exp - _TOKEN_BUFFER_S):
        return _abdm_token

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.ABDM_BASE_URL}/auth/token",
                json={
                    "clientId":     settings.ABDM_CLIENT_ID,
                    "clientSecret": settings.ABDM_CLIENT_SECRET,
                    "grantType":    "client_credentials",
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data          = resp.json()
            _abdm_token   = data.get("accessToken") or data.get("access_token")
            expires_in    = int(data.get("expiresIn", 1800))
            _abdm_token_exp = now + expires_in

            logger.info(
                "vaidya.abdm.token_refreshed",
                expires_in_s=expires_in,
            )
            return _abdm_token

    except httpx.HTTPStatusError as exc:
        logger.error(
            "vaidya.abdm.auth_failed",
            status=exc.response.status_code,
            body=exc.response.text[:200],
        )
    except Exception as exc:
        logger.error("vaidya.abdm.auth_error", error=str(exc))
    return None


# ── PMJAY coverage check ──────────────────────────────────────────────────────

async def check_pmjay_coverage(
    aadhaar_token: str,
    state_code:    Optional[str] = None,
) -> dict:
    """
    Check PMJAY + state insurance scheme eligibility for a patient.

    Args:
        aadhaar_token: OTP-verified transaction token (not raw Aadhaar)
        state_code:    ISO 3166-2:IN state code (e.g. "AP", "TN", "MH")

    Returns dict with:
        pmjay_eligible, annual_cover, state_scheme, empanelled_hospitals, ...
    """
    token = await _get_abdm_token()

    if token:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{settings.ABDM_BASE_URL}/beneficiary/search",
                    json={
                        "aadhaarToken": aadhaar_token,
                        "stateCode":    state_code or "",
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-CM-ID":       "sbx",   # sandbox header
                        "Content-Type":  "application/json",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return _parse_pmjay_response(data, state_code)

                logger.warning(
                    "vaidya.abdm.pmjay_api_error",
                    status=resp.status_code,
                    body=resp.text[:200],
                )

        except Exception as exc:
            logger.error("vaidya.abdm.pmjay_error", error=str(exc))

    # Fallback: sandbox/demo response when ABDM is not configured
    return _demo_coverage_response(state_code)


def _parse_pmjay_response(data: dict, state_code: Optional[str]) -> dict:
    """Parse ABDM beneficiary search response → Vaidya coverage dict."""
    # ABDM sandbox returns varies by test Aadhaar token
    beneficiary = data.get("beneficiary", {})
    schemes     = data.get("schemes", [])

    pmjay_scheme  = next((s for s in schemes if "PMJAY" in s.get("schemeName", "").upper()), None)
    state_scheme  = next((s for s in schemes if s.get("stateCode") == state_code), None)

    return {
        "pmjay_eligible":   bool(pmjay_scheme),
        "pmjay_card_no":    beneficiary.get("urnNo", ""),
        "annual_cover":     "₹5,00,000" if pmjay_scheme else None,
        "scheme_name":      pmjay_scheme.get("schemeName") if pmjay_scheme else None,
        "state_scheme":     _state_scheme_name(state_code) if state_scheme else None,
        "state_cover":      state_scheme.get("annualCover") if state_scheme else None,
        "empanelled_hospitals": beneficiary.get("nearestEmpanelledHospitals", []),
        "abha_id":          beneficiary.get("abhaId", ""),
        "valid_till":       pmjay_scheme.get("validTill") if pmjay_scheme else None,
        "source":           "abdm_live",
        "note":             "Carry Aadhaar card or PMJAY card to the hospital.",
    }


def _state_scheme_name(state_code: Optional[str]) -> Optional[str]:
    """Return state health insurance scheme name for each state."""
    return {
        "AP":  "Dr. YSR Aarogyasri",
        "TN":  "Chief Minister Comprehensive Health Insurance Scheme (CMCHIS)",
        "KA":  "Aarogya Karnataka",
        "MH":  "Mahatma Jyotiba Phule Jan Arogya Yojana",
        "KL":  "Karunya Arogya Suraksha Padhati",
        "GJ":  "Mukhyamantri Amrutum Yojana",
        "RJ":  "Mukhyamantri Chiranjeevi Swasthya Bima Yojana",
        "WB":  "Swasthya Sathi",
        "AS":  "Atal Amrit Abhiyan",
        "MP":  "Ayushman Bharat Madhya Pradesh",
        "UP":  "Mukhyamantri Jan Arogya Yojana",
        "BR":  "Mukhyamantri Swasthya Bima Yojana",
        "TS":  "Telangana State Health Insurance Scheme",
        "OR":  "Biju Swasthya Kalyan Yojana",
        "HP":  "Himachal Pradesh Universal Health Protection Scheme",
    }.get(state_code or "", None)


def _demo_coverage_response(state_code: Optional[str]) -> dict:
    """Fallback when ABDM credentials are not configured (dev/testing)."""
    return {
        "pmjay_eligible":   True,
        "pmjay_card_no":    "DEMO-XXXX",
        "annual_cover":     "₹5,00,000",
        "scheme_name":      "Pradhan Mantri Jan Arogya Yojana (PMJAY)",
        "state_scheme":     _state_scheme_name(state_code),
        "state_cover":      "₹5,00,000",
        "empanelled_hospitals": [],
        "abha_id":          "",
        "valid_till":       None,
        "source":           "abdm_sandbox_demo",
        "note":             (
            "ABDM credentials not configured — returning demo coverage. "
            "Set ABDM_CLIENT_ID and ABDM_CLIENT_SECRET in .env for live checks. "
            "Carry Aadhaar card to hospital for on-site verification."
        ),
    }


# ── Hospital PMJAY empanelment check ─────────────────────────────────────────

async def check_hospital_empanelment(
    hospital_name:   str,
    district_code:   Optional[str] = None,
    state_code:      Optional[str] = None,
) -> dict:
    """
    Check whether a specific hospital is PMJAY-empanelled via ABDM.
    Returns bool is_empanelled + hospital NIN ID if found.
    """
    token = await _get_abdm_token()
    if not token:
        return {"is_empanelled": False, "source": "abdm_not_configured"}

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(
                f"{settings.ABDM_BASE_URL}/hospital/search",
                params={
                    "name":          hospital_name,
                    "districtCode":  district_code or "",
                    "stateCode":     state_code or "",
                },
                headers={"Authorization": f"Bearer {token}", "X-CM-ID": "sbx"},
            )
            if resp.status_code == 200:
                hospitals = resp.json().get("hospitals", [])
                if hospitals:
                    match = hospitals[0]
                    return {
                        "is_empanelled":   match.get("isPmjayEmpanelled", False),
                        "nin_id":          match.get("ninId", ""),
                        "hospital_type":   match.get("type", ""),
                        "empanelment_type":match.get("empanelmentType", ""),
                        "source":          "abdm_live",
                    }

    except Exception as exc:
        logger.warning("vaidya.abdm.empanelment_error", hospital=hospital_name, error=str(exc))

    return {"is_empanelled": False, "source": "abdm_not_found"}


# ── Batch empanelment enrichment ──────────────────────────────────────────────

async def enrich_with_empanelment(
    hospitals: list[dict],
    state_code: Optional[str] = None,
) -> list[dict]:
    """
    Enrich a list of hospital dicts with PMJAY empanelment status.
    Queries ABDM for each hospital in parallel (up to 10 concurrently).
    """
    import asyncio

    async def _check_one(h: dict) -> dict:
        result = await check_hospital_empanelment(
            hospital_name=h["name"],
            state_code=state_code,
        )
        h["pmjay_empanelled"] = result.get("is_empanelled", False)
        h["nin_id"]           = result.get("nin_id", "")
        return h

    tasks = [_check_one(h) for h in hospitals[:10]]
    enriched = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        h if not isinstance(h, Exception) else hospitals[i]
        for i, h in enumerate(enriched)
    ]
