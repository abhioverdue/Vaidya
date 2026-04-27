"""
Vaidya — symptom extraction service  (Module 3 — complete)
Pipeline:
  1. Redis cache check  (TTL 10 min — same text → skip all inference)
  2. Translation        (hi/ta → en via translator.py from Module 2)
  3. LLM extraction     (Gemini 2.0 Flash with engineered system prompt + few-shot)
  4. spaCy NER pass     (en_core_web_sm — catches what LLM misses)
  5. Canonical mapping  (synonym map → difflib fuzzy match → 133-feature vector)
  6. Validation & cache persist

Design decisions:
  - Two-pass extraction: LLM for semantic understanding + spaCy for clinical NER.
    Neither alone is reliable enough. LLM handles vague patient language;
    spaCy catches specific medical terms the LLM might rephrase.
  - Temperature=0.05: near-deterministic. Medical extraction must be consistent —
    same input must produce same output across retries.
  - Few-shot examples in system prompt: 5 worked examples covering EN/HI/TA
    and edge cases (cardiac emergency, jaundice, GI symptoms).
  - Structured output enforced via output schema in system prompt +
    aggressive JSON parsing with multiple fallback strategies.
  - Regex fallback: if both LLM and spaCy fail, a keyword scanner over the
    133 canonical terms + synonym map runs as last resort.
"""

import asyncio
import difflib
import hashlib
import json
import re
from functools import lru_cache
from typing import Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.schemas.schemas import ExtractedSymptoms
from app.services.nlp.prompt_loader import get_extraction_system_prompt, get_few_shot_examples
from app.services.nlp.translator import translate_to_english

logger = structlog.get_logger(__name__)

# ── Canonical symptom list (133 features — exact Training.csv columns) ──────────
CANONICAL_SYMPTOMS: list[str] = [
    "itching", "skin_rash", "nodal_skin_eruptions", "continuous_sneezing",
    "shivering", "chills", "joint_pain", "stomach_pain", "acidity",
    "ulcers_on_tongue", "muscle_wasting", "vomiting", "burning_micturition",
    "spotting_urination", "fatigue", "weight_gain", "anxiety",
    "cold_hands_and_feets", "mood_swings", "weight_loss", "restlessness",
    "lethargy", "patches_in_throat", "irregular_sugar_level", "cough",
    "high_fever", "sunken_eyes", "breathlessness", "sweating", "dehydration",
    "indigestion", "headache", "yellowish_skin", "dark_urine", "nausea",
    "loss_of_appetite", "pain_behind_the_eyes", "back_pain", "constipation",
    "abdominal_pain", "diarrhoea", "mild_fever", "yellow_urine",
    "yellowing_of_eyes", "acute_liver_failure", "fluid_overload",
    "swelling_of_stomach", "swelled_lymph_nodes", "malaise",
    "blurred_and_distorted_vision", "phlegm", "throat_irritation",
    "redness_of_eyes", "sinus_pressure", "runny_nose", "congestion",
    "chest_pain", "weakness_in_limbs", "fast_heart_rate",
    "pain_during_bowel_movements", "pain_in_anal_region", "bloody_stool",
    "irritation_in_anus", "neck_pain", "dizziness", "cramps", "bruising",
    "obesity", "swollen_legs", "swollen_blood_vessels", "puffy_face_and_eyes",
    "enlarged_thyroid", "brittle_nails", "swollen_extremeties",
    "excessive_hunger", "extra_marital_contacts", "drying_and_tingling_lips",
    "slurred_speech", "knee_pain", "hip_joint_pain", "muscle_weakness",
    "stiff_neck", "swelling_joints", "movement_stiffness", "spinning_movements",
    "loss_of_balance", "unsteadiness", "weakness_of_one_body_side",
    "loss_of_smell", "bladder_discomfort", "foul_smell_of_urine",
    "continuous_feel_of_urine", "passage_of_gases", "internal_itching",
    "toxic_look_(typhos)", "depression", "irritability", "muscle_pain",
    "altered_sensorium", "red_spots_over_body", "belly_pain",
    "abnormal_menstruation", "dischromic_patches", "watering_from_eyes",
    "increased_appetite", "polyuria", "family_history", "mucoid_sputum",
    "rusty_sputum", "lack_of_concentration", "visual_disturbances",
    "receiving_blood_transfusion", "receiving_unsterile_injections",
    "coma", "stomach_bleeding", "distention_of_abdomen",
    "history_of_alcohol_consumption", "blood_in_sputum",
    "prominent_veins_on_calf", "palpitations", "painful_walking",
    "pus_filled_pimples", "blackheads", "scurring", "skin_peeling",
    "silver_like_dusting", "small_dents_in_nails", "inflammatory_nails",
    "blister", "red_sore_around_nose", "yellow_crust_ooze",
    "coughing_of_blood", "loss_of_consciousness",
]

# ── Synonym map (sorted longest-first applied at runtime) ──────────────────────
SYNONYM_MAP: dict[str, str] = {
    "difficulty breathing":  "breathlessness",
    "short of breath":       "breathlessness",
    "chest tightness":       "chest_pain",
    "nausea and vomiting":   "nausea",
    "loose motions":         "diarrhoea",
    "loose stool":           "diarrhoea",
    "loose stools":          "diarrhoea",
    "runny stomach":         "diarrhoea",
    "stomach cramping":      "cramps",
    "body pain":             "muscle_pain",
    "body ache":             "muscle_pain",
    "body aches":            "muscle_pain",
    "low grade fever":       "mild_fever",
    "low-grade fever":       "mild_fever",
    "high fever":            "high_fever",
    "heart racing":          "palpitations",
    "heart pounding":        "palpitations",
    "blood in cough":        "coughing_of_blood",
    "blood in sputum":       "blood_in_sputum",
    "coughing blood":        "coughing_of_blood",
    "passed out":            "loss_of_consciousness",
    "sore throat":           "throat_irritation",
    "throat pain":           "throat_irritation",
    "throat ache":           "throat_irritation",
    "skin itching":          "itching",
    "yellow eyes":           "yellowing_of_eyes",
    "yellow skin":           "yellowish_skin",
    "stomach pain":          "stomach_pain",
    "stomach ache":          "stomach_pain",
    "tummy ache":            "stomach_pain",
    "belly pain":            "belly_pain",
    "back ache":             "back_pain",
    "neck stiffness":        "stiff_neck",
    "blurry vision":         "blurred_and_distorted_vision",
    "blurred vision":        "blurred_and_distorted_vision",
    "arm numbness":          "weakness_in_limbs",
    "leg numbness":          "weakness_in_limbs",
    "limb weakness":         "weakness_in_limbs",
    "spinning sensation":    "spinning_movements",
    "loss of balance":       "loss_of_balance",
    "loss of smell":         "loss_of_smell",
    "loss of appetite":      "loss_of_appetite",
    "loss of consciousness": "loss_of_consciousness",
    "irregular periods":     "abnormal_menstruation",
    "missed period":         "abnormal_menstruation",
    "increased thirst":      "dehydration",
    "frequent urination":    "polyuria",
    "painful urination":     "burning_micturition",
    "burning urination":     "burning_micturition",
    "fever":                 "high_fever",
    "temperature":           "high_fever",
    "pyrexia":               "high_fever",
    "coughing":              "cough",
    "breathless":            "breathlessness",
    "jaundice":              "yellowish_skin",
    "vomit":                 "vomiting",
    "throwing up":           "vomiting",
    "diarrhea":              "diarrhoea",
    "headaches":             "headache",
    "migraine":              "headache",
    "rash":                  "skin_rash",
    "tired":                 "fatigue",
    "tiredness":             "fatigue",
    "exhaustion":            "fatigue",
    "exhausted":             "fatigue",
    "weakness":              "fatigue",
    "weak":                  "fatigue",
    "fits":                  "altered_sensorium",
    "seizure":               "altered_sensorium",
    "seizures":              "altered_sensorium",
    "convulsion":            "altered_sensorium",
    "fainted":               "loss_of_consciousness",
    "syncope":               "dizziness",
    "palpitation":           "palpitations",
    "itchy":                 "itching",
    "numb":                  "weakness_in_limbs",
    "numbness":              "weakness_in_limbs",
    "mucus":                 "phlegm",
    "constipated":           "constipation",
    "bloated":               "distention_of_abdomen",
    "bloating":              "distention_of_abdomen",
    "heartburn":             "acidity",
    "acid reflux":           "acidity",
    "confused":              "altered_sensorium",
    "confusion":             "altered_sensorium",
    "dehydrated":            "dehydration",
    "thirsty":               "dehydration",
    "acne":                  "pus_filled_pimples",
    "pimples":               "pus_filled_pimples",
    # HIV / AIDS
    "aids":                  "extra_marital_contacts",
    "hiv":                   "extra_marital_contacts",
    "hiv positive":          "extra_marital_contacts",
    "hiv aids":              "extra_marital_contacts",
    "hiv/aids":              "extra_marital_contacts",
    "immunodeficiency":      "muscle_wasting",
    "muscle wasting":        "muscle_wasting",
    "blood transfusion":     "receiving_blood_transfusion",
    "unsterile injection":   "receiving_unsterile_injections",
    "unsterile injections":  "receiving_unsterile_injections",
    # Genital / penile symptoms
    "penile pain":           "internal_itching",
    "penile discharge":      "internal_itching",
    "penile itching":        "internal_itching",
    "penile sore":           "internal_itching",
    "penis pain":            "internal_itching",
    "penis sore":            "internal_itching",
    "penis discharge":       "internal_itching",
    "pain in penis":         "internal_itching",
    "genital pain":          "internal_itching",
    "genital discharge":     "internal_itching",
    "genital itching":       "internal_itching",
    "genital sore":          "internal_itching",
    "groin pain":            "internal_itching",
    "vaginal pain":          "internal_itching",
    "vaginal discharge":     "internal_itching",
    "vaginal itching":       "internal_itching",
    "urethral discharge":    "burning_micturition",
    "urethral pain":         "burning_micturition",
    "std":                   "internal_itching",
    "sexually transmitted":  "internal_itching",
    # Trauma / musculoskeletal (not in 41-disease dataset — triggers LLM fallback)
    "ankle pain":            "joint_pain",
    "ankle swollen":         "swelling_joints",
    "ankle swelling":        "swelling_joints",
    "swollen ankle":         "swelling_joints",
    "ankle injury":          "painful_walking",
    "ankle sprain":          "painful_walking",
    "ankle fracture":        "painful_walking",
    "ankle hurt":            "joint_pain",
    "sprain":                "painful_walking",
    "fracture":              "painful_walking",
    "broken bone":           "painful_walking",
    "bone pain":             "joint_pain",
    "limping":               "painful_walking",
    "can't walk":            "painful_walking",
    "cannot walk":           "painful_walking",
    "difficulty walking":    "painful_walking",
    "joint swelling":        "swelling_joints",
    "swollen joint":         "swelling_joints",
    "torn ligament":         "joint_pain",
    "knee swollen":          "swelling_joints",
    "knee injury":           "knee_pain",
    "wrist pain":            "joint_pain",
    "wrist swollen":         "swelling_joints",
    "shoulder pain":         "joint_pain",
    "elbow pain":            "joint_pain",
}


# ── spaCy (lazy loaded, optional) ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_spacy():
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        logger.info("vaidya.extractor.spacy_loaded")
        return nlp
    except OSError:
        logger.warning("vaidya.extractor.spacy_model_missing",
                       hint="Run: python -m spacy download en_core_web_sm")
        return None
    except ImportError:
        logger.warning("vaidya.extractor.spacy_not_installed")
        return None


# ── Ollama chat call ───────────────────────────────────────────────────────────

def _build_messages(english_text: str) -> list[dict]:
    """
    Build Gemini /generateContent contents from system prompt + few-shot examples.
    Examples from get_few_shot_examples() are in Ollama {input, output} dict format;
    we flatten them into a single text block for the Gemini API.
    """
    system_prompt = get_extraction_system_prompt(version="v1")
    examples      = get_few_shot_examples(version="v1")

    # Flatten examples to plain text — Gemini uses a single user-turn
    examples_text = "\n\n".join(
        f"EXAMPLE_INPUT:\n{ex['input']}\nEXAMPLE_OUTPUT:\n{ex['output']}"
        for ex in examples
    )

    combined = (
        f"SYSTEM:\n{system_prompt}\n\n"
        f"FEW-SHOT EXAMPLES:\n{examples_text}\n\n"
        f"PATIENT INPUT:\n{english_text}"
    )
    return [{"role": "user", "parts": [{"text": combined}]}]


@retry(
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=False,
)
async def _call_gemini_extractor(english_text: str) -> str | None:
    """Call Gemini REST API for symptom extraction."""
    from app.services.diagnosis.llm_fallback import _call_gemini  # avoids circular import
    messages = _build_messages(english_text)
    return await _call_gemini(messages)


# ── JSON parsing (4 fallback strategies) ─────────────────────────────────────

def _parse_json(raw: str) -> dict | None:
    if not raw:
        return None
    for attempt in [
        lambda s: json.loads(s.strip()),
        lambda s: json.loads(re.sub(r"```(?:json)?", "", s).strip()),
        lambda s: json.loads(re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", s, re.DOTALL).group()),
        lambda s: json.loads(s[s.find("{") : s.rfind("}") + 1]),
    ]:
        try:
            return attempt(raw)
        except Exception:
            continue
    logger.warning("vaidya.extractor.json_all_strategies_failed", preview=raw[:150])
    return None


# ── spaCy NER pass ────────────────────────────────────────────────────────────

def _spacy_extract(text: str) -> list[str]:
    nlp = _load_spacy()
    if not nlp:
        return []
    try:
        doc   = nlp(text.lower())
        found = []
        for token in doc:
            w = token.lemma_.lower().strip()
            if w in SYNONYM_MAP:
                found.append(SYNONYM_MAP[w])
            elif w.replace(" ", "_") in CANONICAL_SYMPTOMS:
                found.append(w.replace(" ", "_"))
        for chunk in doc.noun_chunks:
            p = chunk.text.lower().strip()
            if p in SYNONYM_MAP:
                found.append(SYNONYM_MAP[p])
        return list(set(found))
    except Exception as exc:
        logger.warning("vaidya.extractor.spacy_error", error=str(exc))
        return []


# ── Regex fallback ────────────────────────────────────────────────────────────

def _regex_fallback(text: str) -> dict:
    text_lower  = text.lower()
    canonical   = []
    keywords    = []
    for phrase in sorted(SYNONYM_MAP.keys(), key=len, reverse=True):
        if phrase in text_lower:
            canonical.append(SYNONYM_MAP[phrase])
            keywords.append(phrase)
    for sym in CANONICAL_SYMPTOMS:
        if sym.replace("_", " ") in text_lower and sym not in canonical:
            canonical.append(sym)
            keywords.append(sym.replace("_", " "))
    return {
        "symptoms": list(dict.fromkeys(canonical)),
        "duration": None, "severity_estimate": None,
        "body_parts": [], "red_flags": [], "onset_type": None,
        "raw_keywords": list(dict.fromkeys(keywords)),
        "context_notes": "regex_fallback",
    }


# ── Canonical mapping ─────────────────────────────────────────────────────────

def _clamp_severity(val) -> int | None:
    if val is None:
        return None
    try:
        return max(1, min(10, int(val)))
    except (TypeError, ValueError):
        return None


def _map_to_canonical(
    raw: dict,
    spacy_extra: list[str],
) -> tuple[ExtractedSymptoms, list[str], dict[str, int]]:
    """Map extracted strings → canonical names → 133-feature binary vector."""
    candidates = list(raw.get("symptoms", [])) + \
                 list(raw.get("raw_keywords", [])) + \
                 spacy_extra

    matched:   list[str] = []
    unmatched: list[str] = []

    for sym in candidates:
        if not sym or not isinstance(sym, str):
            continue
        lower = sym.lower().strip()
        snake = lower.replace(" ", "_").replace("-", "_")

        if lower in SYNONYM_MAP:
            matched.append(SYNONYM_MAP[lower])
        elif snake in CANONICAL_SYMPTOMS:
            matched.append(snake)
        else:
            close = difflib.get_close_matches(snake, CANONICAL_SYMPTOMS, n=1, cutoff=0.65)
            if close:
                matched.append(close[0])
            else:
                # Second attempt: space-separated form
                spaced    = lower.replace("_", " ")
                can_spaced = [s.replace("_", " ") for s in CANONICAL_SYMPTOMS]
                close2 = difflib.get_close_matches(spaced, can_spaced, n=1, cutoff=0.65)
                if close2:
                    matched.append(CANONICAL_SYMPTOMS[can_spaced.index(close2[0])])
                else:
                    unmatched.append(sym)

    matched = list(dict.fromkeys(matched))   # deduplicate, preserve order
    vector  = {col: 0 for col in CANONICAL_SYMPTOMS}
    for sym in matched:
        if sym in vector:
            vector[sym] = 1

    extracted = ExtractedSymptoms(
        symptoms=matched,
        duration=raw.get("duration"),
        severity_estimate=_clamp_severity(raw.get("severity_estimate")),
        body_parts=raw.get("body_parts", []),
        raw_keywords=raw.get("raw_keywords", []),
    )
    return extracted, unmatched, vector


# ── Main public API ────────────────────────────────────────────────────────────

async def extract_symptoms(
    text: str,
    language: Optional[str],
    redis,
) -> tuple[ExtractedSymptoms, list[str], dict[str, int]]:
    """
    Full 6-stage extraction pipeline.
    Returns (ExtractedSymptoms, unmatched_terms, symptom_vector_133).
    """
    # Stage 1: cache
    cache_key = f"nlp:v3:{hashlib.sha256(text.encode()).hexdigest()[:24]}"
    cached = await redis.get(cache_key)
    if cached:
        logger.debug("vaidya.extractor.cache_hit")
        d = json.loads(cached)
        return ExtractedSymptoms(**d["extracted"]), d.get("unmatched", []), d["vector"]

    # Stage 2: translate
    english_text = text
    if language and language != "en":
        tr           = await translate_to_english(text, language)
        english_text = tr["translated"]
        logger.debug("vaidya.extractor.translated", method=tr["method"])

    # Stage 3: LLM
    llm_data = None
    source   = "llm"
    try:
        raw = await _call_gemini_extractor(english_text)
        if raw:
            llm_data = _parse_json(raw)
    except Exception as exc:
        logger.error("vaidya.extractor.llm_error", error=str(exc))

    if not llm_data:
        logger.warning("vaidya.extractor.using_regex_fallback")
        llm_data = _regex_fallback(english_text)
        source   = "regex_fallback"

    # Stage 4: spaCy (run_in_executor requires the running loop, not get_event_loop)
    loop         = asyncio.get_running_loop()
    spacy_extras = await loop.run_in_executor(None, _spacy_extract, english_text)

    logger.info(
        "vaidya.extractor.stages_done",
        source=source,
        llm_symptoms=len(llm_data.get("symptoms", [])),
        spacy_extras=len(spacy_extras),
    )

    # Stage 5: map to canonical
    extracted, unmatched, vector = _map_to_canonical(llm_data, spacy_extras)

    # Stage 6: cache
    await redis.setex(
        cache_key,
        settings.REDIS_TTL_SYMPTOMS,
        json.dumps({
            "extracted": extracted.model_dump(),
            "vector":    vector,
            "unmatched": unmatched,
        }),
    )

    logger.info(
        "vaidya.extractor.complete",
        matched=len(extracted.symptoms),
        unmatched=len(unmatched),
        vector_active=sum(vector.values()),
    )
    return extracted, unmatched, vector


def build_symptom_vector(symptoms: list[str]) -> dict[str, int]:
    """Build 133-feature binary vector from canonical symptom name list."""
    vector = {col: 0 for col in CANONICAL_SYMPTOMS}
    for sym in symptoms:
        if sym in vector:
            vector[sym] = 1
    return vector
