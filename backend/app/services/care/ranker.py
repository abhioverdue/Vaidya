"""
Vaidya — Hospital ranking engine

Scores each candidate hospital on 4 dimensions and returns a ranked list.

Ranking formula:
    score = (w_dist × dist_score)
          + (w_type × type_score)
          + (w_triage × triage_score)
          + (w_insurance × insurance_score)

Weights are adaptive: triage urgency shifts weight from distance → type.
At triage level 5 (emergency), the nearest facility wins regardless of type.
At triage level 1 (self-care), distance dominates — no reason to travel far.

Components:
  dist_score     — inverse distance (closer = higher)
  type_score     — govt/PHC preferred for PMJAY coverage + free care
  triage_score   — bonus for 24h availability + 108 ambulance on urgent triage
  insurance_score — PMJAY empanelled gets a boost for eligible patients

All scores normalised to [0, 1].
"""

from __future__ import annotations

import math
from typing import Optional


# ── Type score: government facilities preferred ──────────────────────────────
TYPE_SCORE: dict[str, float] = {
    "phc":      1.00,   # free care, always preferred
    "chc":      0.90,
    "district": 0.80,
    "esic":     0.70,   # only for ESIC-registered workers, but generally good
    "private":  0.40,
    "other":    0.30,
}


def score_hospitals(
    hospitals:      list[dict],
    triage_level:   int,
    pmjay_eligible: bool = False,
    max_results:    int  = 10,
) -> list[dict]:
    """
    Rank a list of hospital dicts by composite score.

    Args:
        hospitals:      List from Overpass (PMJAY flags already set)
        triage_level:   1–5 from triage engine
        pmjay_eligible: Whether patient has PMJAY coverage
        max_results:    Cap on returned results

    Returns:
        Sorted list (highest score first), each dict enriched with _score and _rank.
    """
    if not hospitals:
        return []

    # ── Adaptive weights based on triage urgency ──────────────────────────────
    # Level 5 (emergency): nearest first — no time to be picky about type
    # Level 1 (self-care): prefer familiar nearby PHC
    w_dist, w_type, w_triage, w_ins = _weights(triage_level)

    # Normalise distances for scoring (find max distance in this result set)
    distances = [h.get("distance_km", 50.0) for h in hospitals]
    max_dist  = max(distances) if distances else 1.0
    if max_dist == 0:
        max_dist = 1.0

    scored = []
    for h in hospitals:
        dist_km  = h.get("distance_km", 50.0)
        h_type   = h.get("hospital_type", "other")
        open_24h = h.get("open_24h", False)
        amb_108  = h.get("ambulance_108", False)
        pmjay    = h.get("pmjay_empanelled", False)

        # Distance score: exponential decay — doubles in value per 10 km halved
        # Normalised: 0 km → 1.0, max_dist → 0.05
        dist_score = math.exp(-3.0 * dist_km / max_dist)

        # Type score
        type_score = TYPE_SCORE.get(h_type, 0.3)

        # Triage score: bonus for 24h + ambulance on urgent/emergency cases
        if triage_level >= 4:
            triage_score = (0.6 if open_24h else 0.2) + (0.4 if amb_108 else 0.0)
        elif triage_level == 3:
            triage_score = 0.7 if open_24h else 0.4
        else:
            triage_score = 0.5   # low urgency: all facilities equally fine

        # Insurance score
        if pmjay_eligible and pmjay:
            ins_score = 1.0
        elif not pmjay_eligible:
            ins_score = 0.5   # neutral when patient doesn't have PMJAY
        else:
            ins_score = 0.0   # PMJAY patient at non-empanelled hospital pays OOP

        composite = (
            w_dist    * dist_score
            + w_type    * type_score
            + w_triage  * triage_score
            + w_ins     * ins_score
        )

        enriched = {**h, "_score": round(composite, 4)}
        scored.append(enriched)

    scored.sort(key=lambda x: -x["_score"])

    # Add rank and clean internal key
    for i, h in enumerate(scored[:max_results], start=1):
        h["rank"]    = i
        h.pop("_score", None)

    return scored[:max_results]


def _weights(triage_level: int) -> tuple[float, float, float, float]:
    """
    Return (w_distance, w_type, w_triage, w_insurance) for a triage level.
    All weights sum to 1.0.

    Philosophy:
      Level 5 (emergency): fastest access overrides everything
      Level 4 (urgent):    24h + ambulance matters a lot
      Level 3 (semi-urgent): govt-first for free care
      Level 1-2 (mild):   distance + familiar govt facility
    """
    return {
        5: (0.50, 0.10, 0.35, 0.05),   # nearest first
        4: (0.35, 0.20, 0.35, 0.10),   # 24h + ambulance critical
        3: (0.30, 0.35, 0.20, 0.15),   # govt preference for free care
        2: (0.40, 0.35, 0.10, 0.15),
        1: (0.45, 0.35, 0.05, 0.15),   # relaxed — distance + familiar PHC
    }.get(triage_level, (0.40, 0.30, 0.15, 0.15))
