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

# Hardcoded fallback precautions — used when CSV files are unavailable in deployment
FALLBACK_PRECAUTIONS: dict[str, list[str]] = {
    "Fungal infection":                ["Keep skin dry and clean", "Use prescribed antifungal cream", "Avoid sharing clothes or towels", "Wear breathable cotton clothing"],
    "Allergy":                         ["Identify and avoid your triggers", "Take prescribed antihistamines", "Wash hands and face after going outside", "Keep windows closed during high pollen season"],
    "GERD":                            ["Avoid spicy, oily, and acidic foods", "Eat smaller, more frequent meals", "Do not lie down within 2 hours of eating", "Elevate your head while sleeping"],
    "Drug Reaction":                   ["Stop the suspected drug immediately and consult a doctor", "Note all medications you have taken", "Carry a drug allergy card", "Do not take the drug again without doctor advice"],
    "Peptic ulcer diseae":             ["Avoid spicy and acidic foods", "Do not skip meals", "Avoid NSAIDs and aspirin without a doctor", "Reduce stress and avoid alcohol"],
    "Diabetes":                        ["Monitor blood sugar regularly", "Follow a low-sugar, balanced diet", "Exercise for 30 minutes daily", "Take medications as prescribed and attend check-ups"],
    "Gastroenteritis":                 ["Drink ORS (oral rehydration solution) frequently", "Avoid solid food until vomiting stops", "Wash hands thoroughly before eating", "Avoid dairy products until fully recovered"],
    "Bronchial Asthma":                ["Keep your reliever inhaler accessible at all times", "Avoid smoke, dust, and pollen", "Do not exercise in cold dry air", "Follow your prescribed inhaler routine daily"],
    "Hypertension":                    ["Reduce salt intake significantly", "Exercise regularly and maintain a healthy weight", "Monitor blood pressure daily", "Avoid alcohol and smoking"],
    "Migraine":                        ["Rest immediately in a dark, quiet room", "Apply a cold or warm compress to your forehead", "Stay well hydrated", "Keep a diary to identify your personal triggers"],
    "Jaundice":                        ["Rest completely and avoid all physical exertion", "Drink plenty of clean fluids", "Avoid fatty foods and alcohol completely", "Seek medical review to identify the cause"],
    "Malaria":                         ["Complete the full course of antimalarial medication", "Sleep under a mosquito net every night", "Apply insect repellent on exposed skin", "Remove stagnant water around your home"],
    "Chicken pox":                     ["Keep skin cool and dry", "Do not scratch — it spreads the rash and causes scarring", "Apply calamine lotion for itch relief", "Isolate from unvaccinated or pregnant individuals"],
    "Dengue":                          ["Rest and drink plenty of fluids, including ORS", "Take paracetamol only — avoid aspirin and ibuprofen", "Monitor platelet count daily", "Use mosquito nets and repellents"],
    "Typhoid":                         ["Drink only boiled or sealed bottled water", "Complete the full prescribed antibiotic course", "Eat freshly cooked food only — avoid raw vegetables", "Practice strict hand hygiene"],
    "Hepatitis A":                     ["Rest and avoid alcohol completely", "Drink only clean, boiled water", "Eat light, easily digestible food", "Do not share utensils, towels, or personal items"],
    "Hepatitis B":                     ["Take prescribed antiviral medications regularly", "Avoid alcohol completely", "Practice safe sex", "Get close contacts vaccinated against hepatitis B"],
    "Tuberculosis":                    ["Complete the full 6-month treatment — do not stop early", "Cover your mouth and nose when coughing or sneezing", "Ventilate your living space with fresh air daily", "Get household contacts tested and vaccinated"],
    "Common Cold":                     ["Rest and drink plenty of warm fluids", "Use saline nasal drops to relieve congestion", "Take steam inhalation twice a day", "Avoid cold beverages and exposure to cold air"],
    "Pneumonia":                       ["Complete the full antibiotic course even when feeling better", "Rest completely and drink plenty of fluids", "Avoid smoking", "Follow up with a chest X-ray after treatment"],
    "Heart attack":                    ["Call 108 immediately — every minute matters", "Chew a regular aspirin (325 mg) if not allergic", "Rest in a comfortable position while waiting for help", "Do not eat or drink anything"],
    "Urinary tract infection":         ["Drink at least 2 litres of water daily", "Complete the full antibiotic course", "Urinate frequently — do not hold it in", "Maintain personal hygiene and wear cotton underwear"],
    "Hypothyroidism":                  ["Take thyroid medication at the same time every morning on an empty stomach", "Avoid eating for 30 minutes after your tablet", "Get thyroid levels tested every 3–6 months", "Eat a balanced diet — avoid excessive iodine or soy"],
    "Hyperthyroidism":                 ["Take prescribed antithyroid medication consistently", "Avoid iodine-rich foods (seaweed, iodised salt)", "Rest and reduce stress", "Attend regular thyroid function tests"],
    "Osteoarthritis":                  ["Exercise gently — swimming and walking are best", "Maintain a healthy weight to reduce joint stress", "Apply hot or cold packs for pain relief", "Avoid high-impact activities like running"],
    "Arthritis":                       ["Do gentle range-of-motion exercises daily", "Apply warm or cold packs to affected joints", "Take prescribed anti-inflammatory medications", "Maintain a healthy weight"],
    "Dimorphic hemmorhoids(piles)":    ["Eat a high-fibre diet with plenty of vegetables", "Drink at least 2 litres of water daily", "Do not strain during bowel movements", "Apply ice pack to relieve pain and swelling"],
    "Varicose veins":                  ["Elevate your legs above heart level when resting", "Avoid prolonged standing or sitting", "Wear compression stockings during the day", "Walk regularly to improve circulation"],
    "psoriasis":                       ["Moisturise affected skin twice daily", "Avoid skin injuries and scratching", "Use prescribed topical treatments as directed", "Reduce stress through yoga or meditation"],
    "Impetigo":                        ["Keep the affected area clean and dry", "Apply prescribed antibiotic cream as directed", "Do not scratch or touch the sores", "Wash hands frequently and avoid sharing towels"],
    "Cervical spondylosis":            ["Do gentle neck exercises daily", "Avoid prolonged screen time without breaks", "Use a supportive, low pillow while sleeping", "Apply a warm heat pack to the neck for pain relief"],
    "Paralysis (brain hemorrhage)":    ["Call 108 emergency immediately", "Do not move the patient — keep them still", "Note the exact time symptoms started", "Keep the airway clear and monitor breathing"],
    "Brain Hemorrhage":                ["Call 108 emergency immediately", "Do not give food or water", "Keep the patient still and calm", "Monitor breathing and consciousness until help arrives"],
    "Alcoholic hepatitis":             ["Stop consuming alcohol immediately and completely", "Follow a doctor-prescribed nutritional plan", "Take prescribed medications consistently", "Attend regular liver function tests"],
}


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


# ── Severe-disease guards ─────────────────────────────────────────────────────
# These diseases must NOT be predicted unless at least one "anchor" symptom is
# present. Without a focal-neurological or organ-specific sign, the XGBoost
# model over-fires on common symptom clusters (headache + vomiting).
SEVERE_DISEASE_GUARDS: dict[str, dict] = {
    "Brain Hemorrhage": {
        "anchors": [
            "weakness_of_one_body_side", "altered_sensorium",
            "loss_of_consciousness", "slurred_speech",
            "loss_of_balance", "unsteadiness", "coma",
        ],
        "min_total": 3,
    },
    "Paralysis (brain hemorrhage)": {
        "anchors": [
            "weakness_of_one_body_side", "altered_sensorium",
            "loss_of_consciousness", "slurred_speech",
        ],
        "min_total": 2,
    },
}


def _passes_guard(disease: str, symptom_vector: dict[str, int]) -> bool:
    """Return False if a severe disease is predicted without its anchor symptoms."""
    guard = SEVERE_DISEASE_GUARDS.get(disease)
    if guard is None:
        return True
    total_active = sum(1 for v in symptom_vector.values() if v)
    has_anchor = any(symptom_vector.get(s) for s in guard["anchors"])
    return has_anchor or total_active >= guard["min_total"] + 2


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
    loop = asyncio.get_running_loop()
    proba = await loop.run_in_executor(
        None, model.predict_proba, vec.reshape(1, -1)
    )
    proba = proba[0]

    # Top-5 candidates; primary is first that passes severe-disease guard
    top_indices = np.argsort(proba)[::-1][:5]
    classes = encoder.classes_

    primary_idx, primary_disease, primary_confidence = None, None, 0.0
    for idx in top_indices:
        candidate = classes[idx]
        if _passes_guard(candidate, symptom_vector):
            primary_idx        = idx
            primary_disease    = candidate
            primary_confidence = float(proba[idx])
            break
    if primary_idx is None:          # all guarded (extremely unlikely)
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
        for i in top_indices
        if i != primary_idx and float(proba[i]) > 0.05
    ][:3]

    red_flags = _detect_red_flags(symptom_vector)

    logger.info(
        "vaidya.classifier.result",
        primary=primary_disease,
        confidence=round(primary_confidence, 3),
        differential_count=len(differential),
    )

    precautions = (
        DISEASE_PRECAUTIONS.get(primary_disease)
        or FALLBACK_PRECAUTIONS.get(primary_disease)
        or ["Consult a licensed doctor for a confirmed diagnosis",
            "Rest and stay well hydrated",
            "Monitor your symptoms and seek care if they worsen",
            "Call 108 if you experience sudden or severe symptoms"]
    )

    return DiagnosisResult(
        primary_diagnosis=primary_disease,
        confidence=primary_confidence,
        differential=differential,
        diagnosis_source="xgboost",
        red_flags=red_flags,
        description=DISEASE_DESCRIPTIONS.get(primary_disease),
        precautions=precautions,
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

    if sv.get("headache") and sv.get("altered_sensorium"):
        flags.append("Headache with altered sensorium — possible neurological emergency")

    if sv.get("coughing_of_blood") or sv.get("blood_in_sputum"):
        flags.append("Haemoptysis (blood in cough/sputum) detected")

    if sv.get("yellowish_skin") and sv.get("abdominal_pain"):
        flags.append("Jaundice + abdominal pain — possible hepatic emergency")

    if sv.get("chest_pain") and sv.get("sweating") and sv.get("nausea"):
        flags.append("Chest pain + sweating + nausea — classic MI triad")

    return flags
