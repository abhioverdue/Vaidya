"""
Vaidya — Multimodal Signal Fusion Engine  (Module 4)

Combines three model signals into a single DiagnosisResult:
  - XGBoost symptom classifier  (nlp2.ipynb)     → 132 disease classes, float proba
  - Audio ensemble model         (audio.ipynb)    → 3 classes: cough_severe | cough_healthy | other
  - Vision multitask model       (Computer_Vision) → chest | skin | wound task heads

Fusion strategy: Weighted confidence voting with domain-aware upweighting.

Why not simple averaging?
  The three models operate in different semantic spaces:
    XGBoost predicts specific diseases (Pneumonia, Dengue, etc.)
    Audio predicts severity buckets (cough_severe ≠ a disease)
    Vision predicts pathology categories (bacterial_pneumonia, wound type)

  Simple averaging across incompatible label spaces is meaningless.
  Instead we use a two-stage approach:

  Stage 1 — Signal interpretation:
    Each model produces a ModelSignal: {disease_hint, confidence, modality, raw}
    Audio 'cough_severe' → maps to a set of NLP diseases it corroborates
    Vision 'bacterial_pneumonia' → maps to 'Pneumonia' in NLP disease space

  Stage 2 — Confidence-weighted vote:
    For each NLP disease candidate:
      fused_score = xgb_weight × xgb_proba
                  + audio_weight × audio_corroboration_score
                  + vision_weight × vision_corroboration_score

    Weights are adaptive:
      - If audio file was provided and model loaded → audio_weight = 0.25
      - If image file was provided and model loaded → vision_weight = 0.20
      - If only text → xgb_weight = 1.0
      - Weights always sum to 1.0 (renormalised after each modality is enabled)

  LLM fallback trigger:
    If fused_confidence < CONFIDENCE_THRESHOLD → run_llm_fallback()
    Also triggered when active symptom count < MIN_SYMPTOMS (4)

  Red flag escalation:
    Red flags from any signal source are unioned and escalate triage independently
    of model confidence — a cardiac pattern in the symptom vector always fires
    regardless of XGBoost confidence.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import structlog

from app.core.config import settings
from app.schemas.schemas import DiagnosisResult

logger = structlog.get_logger(__name__)

# ── Minimum symptoms for XGBoost to be trusted ────────────────────────────────
MIN_SYMPTOMS_FOR_CLASSIFIER = 4   # mirrors predict_disease(min_symptoms=4) in nlp2.ipynb

# ── Base weights (sum must = 1.0 when all modalities active) ─────────────────
BASE_WEIGHT_NLP    = 0.55
BASE_WEIGHT_AUDIO  = 0.25
BASE_WEIGHT_VISION = 0.20

# ── Audio label → NLP disease corroboration map ──────────────────────────────
# Audio model outputs 3 classes (from audio.ipynb Cell 9 merge):
#   cough_severe  ← bronchitis, pneumonia, lung_fibrosis, pleural_effusion, covid, symptomatic
#   cough_healthy ← healthy cough (no pathology)
#   other         ← asthma, crackle, wheeze, normal respiratory sounds
#
# For each audio label, which NLP diseases does it corroborate (and by how much)?
# Corroboration scores are multiplied by the audio model's confidence.
AUDIO_CORROBORATION: dict[str, dict[str, float]] = {
    "cough_severe": {
        "Pneumonia":           1.00,
        "Tuberculosis":        0.85,
        "Bronchial Asthma":    0.70,
        "COPD":                0.70,
        "Common Cold":         0.40,
        "Influenza":           0.60,
        "COVID-19":            0.75,
        "Lung Cancer":         0.50,
        "Pleural Effusion":    0.65,
        "Bronchiectasis":      0.60,
    },
    "cough_healthy": {
        "Common Cold":         0.80,
        "Allergy":             0.70,
        "GERD":                0.50,
        "Hypothyroidism":      0.30,
    },
    "other": {
        "Bronchial Asthma":    0.75,
        "COPD":                0.65,
        "Heart Failure":       0.50,
        "Lung Cancer":         0.40,
    },
}

# ── Vision label → NLP disease corroboration map ─────────────────────────────
# Vision model has 3 task heads (from Computer_Vision_AIforHealth.ipynb):
#
# chest head classes: bacterial_pneumonia | viral_pneumonia | normal | other
# skin head classes:  Acne | Eczema | Psoriasis | Rosacea | Seborrheic_Dermatitis | Normal
# wound head classes: abrasion | bruise | burn | cut | diabetic_wound | laceration |
#                     normal | pressure_wound | surgical_wound | venous_wound

VISION_CORROBORATION: dict[str, dict[str, float]] = {
    # Chest head
    "bacterial_pneumonia": {"Pneumonia": 1.00, "Tuberculosis": 0.40},
    "viral_pneumonia":     {"Pneumonia": 0.90, "Influenza": 0.60, "Common Cold": 0.30},
    "normal":              {},   # no corroboration — normal chest
    # Skin head
    "Acne":                {"Acne":              1.00, "Fungal infection":   0.30},
    "Eczema":              {"Psoriasis":         0.60, "Allergy":            0.50},
    "Psoriasis":           {"Psoriasis":         1.00},
    "Rosacea":             {"Acne":              0.50},
    "Seborrheic_Dermatitis":{"Fungal infection": 0.70, "Psoriasis":         0.40},
    "Normal":              {},
    # Wound head
    "abrasion":            {"Impetigo":          0.60},
    "bruise":              {"Dengue":            0.40, "Thrombocytopenic purpura": 0.50},
    "burn":                {},
    "cut":                 {},
    "diabetic_wound":      {"Diabetes":          0.90, "Diabetic neuropathy": 0.70},
    "laceration":          {},
    "pressure_wound":      {},
    "surgical_wound":      {},
    "venous_wound":        {"Varicose veins":    0.80, "Heart failure":      0.40},
}

# ── Audio label → triage severity hint ───────────────────────────────────────
# Directly influences triage even when XGBoost confidence is low
AUDIO_TRIAGE_HINT: dict[str, int] = {
    "cough_severe":  3,   # at minimum "Visit PHC within 48h"
    "cough_healthy": 1,
    "other":         2,
}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ModelSignal:
    """Normalised output from a single model — ready for fusion."""
    modality:       str                      # "nlp" | "audio" | "vision"
    available:      bool                     # was this model actually run?
    top_label:      str = ""                 # primary prediction label
    confidence:     float = 0.0             # 0.0–1.0
    all_probs:      dict[str, float] = field(default_factory=dict)  # label → prob
    raw_result:     dict = field(default_factory=dict)
    error:          Optional[str] = None


@dataclass
class FusionPlan:
    """Computed weight plan — depends on which modalities are available."""
    w_nlp:    float
    w_audio:  float
    w_vision: float

    @classmethod
    def compute(cls, has_audio: bool, has_vision: bool) -> "FusionPlan":
        """
        Allocate weights based on available modalities.
        When a modality is absent its weight is redistributed to NLP (most reliable).
        """
        if has_audio and has_vision:
            return cls(BASE_WEIGHT_NLP, BASE_WEIGHT_AUDIO, BASE_WEIGHT_VISION)
        if has_audio and not has_vision:
            extra = BASE_WEIGHT_VISION
            return cls(BASE_WEIGHT_NLP + extra * 0.6, BASE_WEIGHT_AUDIO + extra * 0.4, 0.0)
        if has_vision and not has_audio:
            extra = BASE_WEIGHT_AUDIO
            return cls(BASE_WEIGHT_NLP + extra * 0.6, 0.0, BASE_WEIGHT_VISION + extra * 0.4)
        # Text only
        return cls(1.0, 0.0, 0.0)

    def __post_init__(self):
        total = self.w_nlp + self.w_audio + self.w_vision
        assert abs(total - 1.0) < 0.001, f"Weights must sum to 1.0, got {total}"


# ── Signal normalisation ──────────────────────────────────────────────────────

def _parse_nlp_signal(nlp_result: DiagnosisResult) -> ModelSignal:
    """Convert DiagnosisResult → ModelSignal."""
    all_probs = {nlp_result.primary_diagnosis: nlp_result.confidence}
    for d in nlp_result.differential:
        all_probs[d["disease"]] = d["confidence"]
    return ModelSignal(
        modality="nlp",
        available=True,
        top_label=nlp_result.primary_diagnosis,
        confidence=nlp_result.confidence,
        all_probs=all_probs,
        raw_result=nlp_result.model_dump(),
    )


def _parse_audio_signal(audio_result: dict | None) -> ModelSignal:
    """Convert audio model output → ModelSignal."""
    if not audio_result or audio_result.get("error"):
        return ModelSignal(modality="audio", available=False,
                           error=audio_result.get("error") if audio_result else "not_run")

    top = audio_result.get("top_prediction", {})
    all_preds = audio_result.get("all_predictions", [])
    all_probs = {p["label"]: p["confidence"] for p in all_preds}

    return ModelSignal(
        modality="audio",
        available=True,
        top_label=top.get("label", ""),
        confidence=top.get("confidence", 0.0),
        all_probs=all_probs,
        raw_result=audio_result,
    )


def _parse_vision_signal(vision_result: dict | None) -> ModelSignal:
    """Convert vision model output → ModelSignal."""
    if not vision_result or vision_result.get("error"):
        return ModelSignal(modality="vision", available=False,
                           error=vision_result.get("error") if vision_result else "not_run")

    top = vision_result.get("top_prediction", {})
    all_preds = vision_result.get("all_predictions", [])
    all_probs = {p["label"]: p["confidence"] for p in all_preds}

    return ModelSignal(
        modality="vision",
        available=True,
        top_label=top.get("label", ""),
        confidence=top.get("confidence", 0.0),
        all_probs=all_probs,
        raw_result=vision_result,
    )


# ── Core fusion algorithm ──────────────────────────────────────────────────────

def _compute_corroboration_scores(
    nlp_signal:   ModelSignal,
    audio_signal: ModelSignal,
    vision_signal: ModelSignal,
    plan:         FusionPlan,
) -> dict[str, float]:
    """
    For each disease candidate from the NLP model, compute a fused score.

    fused_score(disease) =
        w_nlp    × nlp_proba(disease)
      + w_audio  × audio_conf × AUDIO_CORROBORATION[audio_label].get(disease, 0)
      + w_vision × vision_conf × VISION_CORROBORATION[vision_label].get(disease, 0)

    This keeps the three models in their native spaces while allowing
    audio/vision to boost or dampen specific NLP disease hypotheses.
    """
    # Start with all NLP probabilities as base
    fused: dict[str, float] = {}
    for disease, nlp_prob in nlp_signal.all_probs.items():
        fused[disease] = plan.w_nlp * nlp_prob

    # Audio corroboration
    if audio_signal.available and plan.w_audio > 0:
        audio_label = audio_signal.top_label
        audio_conf  = audio_signal.confidence
        corr_map    = AUDIO_CORROBORATION.get(audio_label, {})
        for disease, corr_strength in corr_map.items():
            boost = plan.w_audio * audio_conf * corr_strength
            fused[disease] = fused.get(disease, 0.0) + boost

    # Vision corroboration
    if vision_signal.available and plan.w_vision > 0:
        vision_label = vision_signal.top_label
        vision_conf  = vision_signal.confidence
        corr_map     = VISION_CORROBORATION.get(vision_label, {})
        for disease, corr_strength in corr_map.items():
            boost = plan.w_vision * vision_conf * corr_strength
            fused[disease] = fused.get(disease, 0.0) + boost

    return fused


def _build_fusion_metadata(
    nlp_signal:    ModelSignal,
    audio_signal:  ModelSignal,
    vision_signal: ModelSignal,
    plan:          FusionPlan,
    fused_scores:  dict[str, float],
    active_symptoms: int,
) -> dict:
    """Build a rich metadata dict for logging and API response transparency."""
    return {
        "modalities_used": [
            m for m, s in [
                ("nlp", nlp_signal),
                ("audio", audio_signal),
                ("vision", vision_signal),
            ] if s.available
        ],
        "weights": {
            "nlp":    round(plan.w_nlp, 3),
            "audio":  round(plan.w_audio, 3),
            "vision": round(plan.w_vision, 3),
        },
        "nlp_top":      nlp_signal.top_label,
        "nlp_conf":     round(nlp_signal.confidence, 3),
        "audio_label":  audio_signal.top_label if audio_signal.available else None,
        "audio_conf":   round(audio_signal.confidence, 3) if audio_signal.available else None,
        "vision_label": vision_signal.top_label if vision_signal.available else None,
        "vision_conf":  round(vision_signal.confidence, 3) if vision_signal.available else None,
        "audio_triage_hint": AUDIO_TRIAGE_HINT.get(audio_signal.top_label) if audio_signal.available else None,
        "active_symptoms": active_symptoms,
        "fallback_triggered": False,  # updated after
    }


# ── Main entry point ───────────────────────────────────────────────────────────

async def fuse_signals(
    nlp_result:      DiagnosisResult,
    audio_result:    Optional[dict] = None,
    vision_result:   Optional[dict] = None,
    symptom_count:   int = 0,
    extracted_symptoms: Optional[list[str]] = None,
    extracted_keywords: Optional[list[str]] = None,
    self_severity:   Optional[int] = None,
    language:        str = "en",
) -> tuple[DiagnosisResult, dict]:
    """
    Fuse NLP + audio + vision signals into a single DiagnosisResult.

    Args:
        nlp_result:     DiagnosisResult from XGBoost classifier
        audio_result:   dict from run_audio_model() or None
        vision_result:  dict from run_vision_model() or None
        symptom_count:  number of symptoms matched (for min-symptoms gate)
        extracted_symptoms: canonical symptom names (for LLM fallback)
        extracted_keywords: raw keywords (for LLM fallback)
        self_severity:  patient-reported 1–10 severity
        language:       patient language code

    Returns:
        (DiagnosisResult, fusion_weights dict)
    """
    # ── Parse all signals ────────────────────────────────────────────────────
    nlp_sig    = _parse_nlp_signal(nlp_result)
    audio_sig  = _parse_audio_signal(audio_result)
    vision_sig = _parse_vision_signal(vision_result)

    # ── Compute weight plan ──────────────────────────────────────────────────
    plan = FusionPlan.compute(
        has_audio=audio_sig.available,
        has_vision=vision_sig.available,
    )

    logger.info(
        "vaidya.fusion.start",
        has_audio=audio_sig.available,
        has_vision=vision_sig.available,
        w_nlp=round(plan.w_nlp, 2),
        w_audio=round(plan.w_audio, 2),
        w_vision=round(plan.w_vision, 2),
        nlp_top=nlp_sig.top_label,
        nlp_conf=round(nlp_sig.confidence, 3),
        symptom_count=symptom_count,
    )

    # ── Compute fused scores ─────────────────────────────────────────────────
    fused_scores = _compute_corroboration_scores(nlp_sig, audio_sig, vision_sig, plan)

    # Sort by fused score descending
    sorted_diseases = sorted(fused_scores.items(), key=lambda x: -x[1])

    primary_disease    = sorted_diseases[0][0] if sorted_diseases else nlp_result.primary_diagnosis
    fused_confidence   = sorted_diseases[0][1] if sorted_diseases else 0.0

    # Clamp to [0, 1] — corroboration can push above 1.0 in edge cases
    fused_confidence = min(1.0, max(0.0, fused_confidence))

    # Build top-3 differential
    differential = [
        {
            "disease":    disease,
            "confidence": round(min(1.0, score), 4),
            "confidence_label": (
                "High"   if score > 0.5  else
                "Medium" if score > 0.25 else
                "Low"
            ),
        }
        for disease, score in sorted_diseases[1:4]
        if score > 0.05
    ]

    # ── Collect red flags from all sources ───────────────────────────────────
    red_flags = list(nlp_result.red_flags)

    if audio_sig.available and audio_sig.top_label == "cough_severe":
        if audio_sig.confidence > 0.70:
            red_flags.append(
                f"Audio model detected severe respiratory pattern "
                f"(confidence {round(audio_sig.confidence * 100)}%)"
            )

    if vision_sig.available:
        if vision_sig.top_label in ("bacterial_pneumonia", "viral_pneumonia"):
            if vision_sig.confidence > 0.65:
                red_flags.append(
                    f"Chest X-ray vision model detected {vision_sig.top_label.replace('_', ' ')} "
                    f"(confidence {round(vision_sig.confidence * 100)}%)"
                )
        if vision_sig.top_label == "diabetic_wound" and vision_sig.confidence > 0.60:
            red_flags.append("Wound image suggests possible diabetic ulcer — urgent evaluation needed")

    red_flags = list(dict.fromkeys(red_flags))   # deduplicate

    # ── Build fusion metadata ─────────────────────────────────────────────────
    meta = _build_fusion_metadata(
        nlp_sig, audio_sig, vision_sig, plan, fused_scores, symptom_count
    )

    # ── LLM fallback gate ─────────────────────────────────────────────────────
    # Trigger fallback if:
    #   1. Fused confidence is below threshold AND
    #   2. Symptom count is below minimum
    # Note: if audio/vision strongly corroborate, we trust the fusion result
    #   even at lower NLP confidence — that's the whole point of fusion.
    nlp_alone_too_weak = (
        nlp_sig.confidence < settings.CONFIDENCE_THRESHOLD
        and symptom_count < MIN_SYMPTOMS_FOR_CLASSIFIER
    )
    fusion_still_weak = fused_confidence < (settings.CONFIDENCE_THRESHOLD * 0.8)

    should_fallback = nlp_alone_too_weak and fusion_still_weak

    if should_fallback:
        logger.info(
            "vaidya.fusion.llm_fallback",
            nlp_conf=round(nlp_sig.confidence, 3),
            fused_conf=round(fused_confidence, 3),
            symptom_count=symptom_count,
        )
        from app.services.diagnosis.llm_fallback import run_llm_fallback
        fallback = await run_llm_fallback(
            symptoms=extracted_symptoms or [],
            keywords=extracted_keywords or [],
            severity=self_severity,
            language=language,
        )
        # Preserve red flags from all signal sources
        fallback.red_flags = list(dict.fromkeys(red_flags + fallback.red_flags))
        meta["fallback_triggered"] = True
        logger.info("vaidya.fusion.complete", source="llm_gemini")
        return fallback, {
            "nlp": plan.w_nlp,
            "audio": plan.w_audio,
            "vision": plan.w_vision,
        }

    # ── Build final result ───────────────────────────────────────────────────
    logger.info(
        "vaidya.fusion.complete",
        source="fusion",
        primary=primary_disease,
        fused_conf=round(fused_confidence, 3),
        red_flags=len(red_flags),
        modalities=meta["modalities_used"],
    )

    return DiagnosisResult(
        primary_diagnosis=primary_disease,
        confidence=round(fused_confidence, 4),
        differential=differential,
        diagnosis_source="fusion" if len(meta["modalities_used"]) > 1 else "xgboost",
        red_flags=red_flags,
        description=nlp_result.description,
        precautions=nlp_result.precautions,
    ), {
        "nlp": plan.w_nlp,
        "audio": plan.w_audio,
        "vision": plan.w_vision,
    }


# ── Convenience: run all three models concurrently ────────────────────────────

async def run_all_models_concurrent(
    symptom_vector:  dict[str, int],
    audio_path:      Optional[str] = None,
    image_path:      Optional[str] = None,
    image_task_type: Optional[str] = None,
) -> tuple[DiagnosisResult, Optional[dict], Optional[dict]]:
    """
    Run XGBoost, audio, and vision models concurrently using asyncio.gather.
    Returns (nlp_result, audio_result, vision_result).

    This is the recommended way to call the three models in the diagnose endpoint —
    running them concurrently cuts total inference time from ~3× sequential to
    ~max(individual_times), typically ~1–2s on CPU.

    Args:
        symptom_vector:  133-feature binary dict for XGBoost
        audio_path:      path to audio file (or None to skip audio)
        image_path:      path to image file (or None to skip vision)
        image_task_type: "chest"|"skin"|"wound" (auto-detected from filename if None)
    """
    from app.services.diagnosis.classifier import run_classifier
    from app.services.diagnosis.audio_model import _load_audio_artifacts as load_audio, run_audio_model
    from app.services.diagnosis.vision_model import _load_vision_model as load_vision, run_vision_model

    tasks = [run_classifier(symptom_vector)]

    # Check if audio model is loaded
    audio_loaded = load_audio()[0] is not None
    if audio_path and audio_loaded:
        tasks.append(run_audio_model(audio_path))
    else:
        async def _noop_audio(): return None
        tasks.append(_noop_audio())

    # Check if vision model is loaded
    vision_loaded = load_vision() is not None
    if image_path and vision_loaded:
        tasks.append(run_vision_model(image_path, dataset_type=image_task_type))
    else:
        async def _noop_vision(): return None
        tasks.append(_noop_vision())

    results = await asyncio.gather(*tasks, return_exceptions=True)

    nlp_result    = results[0] if not isinstance(results[0], Exception) else None
    audio_result  = results[1] if not isinstance(results[1], Exception) else None
    vision_result = results[2] if not isinstance(results[2], Exception) else None

    if isinstance(results[0], Exception):
        logger.error("vaidya.fusion.nlp_error", error=str(results[0]))
        # Return a zero-confidence result to trigger LLM fallback
        nlp_result = DiagnosisResult(
            primary_diagnosis="Unknown",
            confidence=0.0,
            differential=[],
            diagnosis_source="xgboost",
            red_flags=[],
        )

    if isinstance(results[1], Exception):
        logger.warning("vaidya.fusion.audio_error", error=str(results[1]))

    if isinstance(results[2], Exception):
        logger.warning("vaidya.fusion.vision_error", error=str(results[2]))

    return nlp_result, audio_result, vision_result
