"""
Vaidya — XGBoost symptom classifier service
Loads trained artifacts from nlp2.ipynb (Cell 14):
  joblib.dump(model,        "final_nlp_model.pkl")   -> NLP_MODEL_PATH
  joblib.dump(le,           "label_encoder.pkl")     -> NLP_ENCODER_PATH
  joblib.dump(symptom_cols, "final_symptom_list.pkl")-> NLP_SYMPTOM_LIST_PATH

No scaler used in NLP pipeline — raw binary symptom vector fed directly to XGBoost.
Inference mirrors predict_disease() from nlp2.ipynb Cell 12 exactly.
"""

import asyncio
from functools import lru_cache

import joblib
import numpy as np
import structlog

from app.core.config import settings
from app.schemas.schemas import DiagnosisResult

logger = structlog.get_logger(__name__)

# Disease descriptions / precautions loaded from CSVs at startup
DISEASE_DESCRIPTIONS: dict[str, str] = {}
DISEASE_PRECAUTIONS: dict[str, list[str]] = {}


@lru_cache(maxsize=1)
def _load_model():
    """
    Load and cache NLP artifacts — exact filenames from nlp2.ipynb Cell 14:
      final_nlp_model.pkl      — XGBoost classifier
      label_encoder.pkl        — LabelEncoder (le) with disease class names
      final_symptom_list.pkl   — symptom_cols list (column order from Training.csv)
    """
    try:
        model        = joblib.load(settings.NLP_MODEL_PATH)          # final_nlp_model.pkl
        encoder      = joblib.load(settings.NLP_ENCODER_PATH)        # label_encoder.pkl
        symptom_list = joblib.load(settings.NLP_SYMPTOM_LIST_PATH)   # final_symptom_list.pkl
        logger.info(
            "vaidya.classifier.loaded",
            model_type=type(model).__name__,
            n_symptoms=len(symptom_list),
            n_classes=len(encoder.classes_),
        )
        return model, encoder, symptom_list
    except FileNotFoundError as exc:
        logger.warning("vaidya.classifier.model_not_found", detail=str(exc))
        return None, None, None


def _load_metadata():
    """Load disease descriptions and precautions from CSVs (from nlp2 dataset)."""
    import os
    import pandas as pd

    desc_path = f"{settings.MODEL_DIR}/nlp/symptom_Description.csv"
    prec_path = f"{settings.MODEL_DIR}/nlp/symptom_precaution.csv"

    if os.path.exists(desc_path):
        desc_df = pd.read_csv(desc_path)
        desc_df["Disease"] = desc_df["Disease"].str.strip()
        DISEASE_DESCRIPTIONS.update(
            dict(zip(desc_df["Disease"], desc_df["Description"]))
        )

    if os.path.exists(prec_path):
        prec_df = pd.read_csv(prec_path)
        prec_df["Disease"] = prec_df["Disease"].str.strip()
        for _, row in prec_df.iterrows():
            disease = row["Disease"]
            precs = [p for p in row.values[1:] if isinstance(p, str) and p.strip()]
            DISEASE_PRECAUTIONS[disease] = precs


try:
    _load_metadata()
except Exception as e:
    logger.warning("vaidya.classifier.metadata_load_failed", error=str(e))


def nlp_models_loaded() -> bool:
    """Return True if all NLP artifacts were loaded successfully."""
    model, encoder, symptom_list = _load_model()
    return model is not None


def check_nlp_ready() -> None:
    """Raise HTTP 503 if NLP models are not loaded."""
    if not nlp_models_loaded():
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="NLP models not loaded — place model artifacts in models/nlp/ and restart",
        )


async def run_classifier(symptom_vector: dict[str, int]) -> DiagnosisResult:
    """
    Run XGBoost inference on the binary symptom vector.
    Mirrors predict_disease() from nlp2.ipynb Cell 12:
      vec = np.zeros(len(symptom_cols))
      vec[symptom_cols.index(col)] = 1   for each matched symptom
      probs = model.predict_proba(vec.reshape(1, -1))[0]

    Args:
        symptom_vector: {symptom_name: 0|1} keyed on canonical symptom names

    Returns:
        DiagnosisResult — top prediction + top-3 differential
    """
    check_nlp_ready()  # raises HTTP 503 if artifacts missing
    model, encoder, symptom_list = _load_model()

    # Build feature vector in EXACT column order from training (symptom_list)
    # This matches: vec = np.zeros(len(symptom_cols)) in the notebook
    vec = np.zeros(len(symptom_list))
    for i, col in enumerate(symptom_list):
        if symptom_vector.get(col, 0) == 1:
            vec[i] = 1

    # Run blocking predict_proba in thread pool (doesn't block async event loop)
    loop = asyncio.get_event_loop()
    proba = await loop.run_in_executor(
        None, model.predict_proba, vec.reshape(1, -1)
    )
    proba = proba[0]

    # Top-3 predictions — matches notebook output format
    top_indices = np.argsort(proba)[::-1][:3]
    classes = encoder.classes_

    primary_idx        = top_indices[0]
    primary_disease    = classes[primary_idx]
    primary_confidence = float(proba[primary_idx])

    differential = [
        {
            "disease":    classes[i],
            "confidence": round(float(proba[i]), 4),
            "confidence_label": (
                "High"   if proba[i] > 0.5  else
                "Medium" if proba[i] > 0.25 else
                "Low"
            ),
        }
        for i in top_indices[1:]
        if float(proba[i]) > 0.05
    ]

    red_flags = _detect_red_flags(symptom_vector)

    logger.info(
        "vaidya.classifier.result",
        primary=primary_disease,
        confidence=round(primary_confidence, 3),
        differential_count=len(differential),
    )

    return DiagnosisResult(
        primary_diagnosis=primary_disease,
        confidence=primary_confidence,
        differential=differential,
        diagnosis_source="xgboost",
        red_flags=red_flags,
        description=DISEASE_DESCRIPTIONS.get(primary_disease),
        precautions=DISEASE_PRECAUTIONS.get(primary_disease, []),
    )


def _detect_red_flags(symptom_vector: dict[str, int]) -> list[str]:
    """
    Hard-coded emergency pattern matching — runs independently of the ML model.
    Based on WHO Emergency Triage Assessment & Treatment guidelines.
    """
    flags = []
    sv = symptom_vector

    if sv.get("chest_pain") and sv.get("breathlessness"):
        flags.append("Chest pain + breathlessness — possible cardiac event")

    if sv.get("loss_of_consciousness"):
        flags.append("Loss of consciousness reported")

    if sv.get("high_fever") and sv.get("stiff_neck"):
        flags.append("High fever + stiff neck — possible meningitis")

    if sv.get("sudden_severe_headache"):
        flags.append("Sudden severe headache — possible subarachnoid haemorrhage")

    if sv.get("coughing_of_blood") or sv.get("blood_in_sputum"):
        flags.append("Haemoptysis (blood in cough/sputum) detected")

    if sv.get("yellowish_skin") and sv.get("abdominal_pain"):
        flags.append("Jaundice + abdominal pain — possible hepatic emergency")

    if sv.get("chest_pain") and sv.get("sweating") and sv.get("nausea"):
        flags.append("Chest pain + sweating + nausea — classic MI triad")

    return flags
