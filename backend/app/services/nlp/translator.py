"""
Vaidya — Hindi/Tamil → English translation service
Module 2 — IndicTrans2 (AI4Bharat, free, self-hostable)

Architecture:
  1. IndicTrans2 microservice (http://indictrans2:8001) — best accuracy
  2. Local phrase map — longest-phrase-first substitution
  3. Word-token fallback — individual word lookup for remaining Indic tokens
"""

import asyncio
import re
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ── Hindi phrase/word map ──────────────────────────────────────────────────────
# Covers all 133 canonical symptoms + common rural patient phrasing.
HINDI_TO_ENGLISH: dict[str, str] = {
    # ── Fever ──────────────────────────────────────────────────────────────────
    "तेज बुखार":               "high fever",
    "हल्का बुखार":             "mild fever",
    "बुखार":                   "fever",
    "ठंड लगना":                "chills",
    "कंपकंपी":                 "shivering",
    "बदन गरम होना":            "fever",
    # ── Respiratory ────────────────────────────────────────────────────────────
    "सांस लेने में तकलीफ":    "breathlessness",
    "सांस फूलना":              "breathlessness",
    "सांस नहीं आना":           "breathlessness",
    "छाती में दर्द":           "chest pain",
    "छाती में जकड़न":          "chest tightness",
    "बलगम में खून":            "blood in sputum",
    "खांसी में खून":           "coughing of blood",
    "चिपचिपा बलगम":            "mucoid sputum",
    "जंग जैसा बलगम":           "rusty sputum",
    "बलगम":                    "phlegm",
    "खांसी":                   "cough",
    "गले में खराश":            "throat irritation",
    "गला खराब":               "sore throat",
    "गले में धब्बे":           "patches in throat",
    "साइनस में दबाव":          "sinus pressure",
    "नाक बंद":                 "congestion",
    "नाक बहना":                "runny nose",
    "लगातार छींकें":           "continuous sneezing",
    # ── GI ─────────────────────────────────────────────────────────────────────
    "जी मिचलाना":              "nausea",
    "उल्टी":                   "vomiting",
    "दस्त":                    "diarrhoea",
    "पेट में खून बहना":        "stomach bleeding",
    "पेट में सूजन":            "swelling of stomach",
    "पेट फूलना":               "distention of abdomen",
    "पेट में जलन":             "acidity",
    "बदहजमी":                  "indigestion",
    "पेट में दर्द":            "abdominal pain",
    "पेट दर्द":                "stomach pain",
    "मल में खून":              "bloody stool",
    "गुदा में दर्द":           "pain in anal region",
    "गुदा में जलन":            "irritation in anus",
    "मल त्याग में दर्द":       "pain during bowel movements",
    "गैस निकलना":              "passage of gases",
    "अंदरूनी खुजली":           "internal itching",
    "कब्ज":                    "constipation",
    # ── Liver / Jaundice ───────────────────────────────────────────────────────
    "आंखें पीली":              "yellowing of eyes",
    "पीली त्वचा":              "yellowish skin",
    "गाढ़ा पेशाब":             "dark urine",
    "पीला पेशाब":              "yellow urine",
    "जिगर खराब":               "acute liver failure",
    "पानी भर जाना":            "fluid overload",
    # ── Pain ───────────────────────────────────────────────────────────────────
    "आंखों के पीछे दर्द":      "pain behind the eyes",
    "गर्दन अकड़ना":            "stiff neck",
    "गर्दन दर्द":              "neck pain",
    "कमर दर्द":                "back pain",
    "जोड़ों में सूजन":         "swelling joints",
    "जोड़ों में दर्द":         "joint pain",
    "घुटने में दर्द":          "knee pain",
    "कूल्हे में दर्द":         "hip joint pain",
    "मांसपेशियों में दर्द":    "muscle pain",
    "बदन दर्द":                "body ache",
    "पैर में दर्द":            "leg pain",
    "चलने में दर्द":           "painful walking",
    # ── Neurological ───────────────────────────────────────────────────────────
    "एक तरफ कमजोरी":           "weakness of one body side",
    "चेतना में बदलाव":          "altered sensorium",
    "बोलने में दिक्कत":        "slurred speech",
    "सिर घूमना":               "spinning movements",
    "संतुलन खोना":             "loss of balance",
    "अस्थिरता":                "unsteadiness",
    "चक्कर आना":               "dizziness",
    "बेहोशी":                  "loss of consciousness",
    "कोमा":                    "coma",
    "ध्यान न लग पाना":         "lack of concentration",
    "दृष्टि में गड़बड़ी":       "visual disturbances",
    "धुंधली दृष्टि":           "blurred and distorted vision",
    "सूंघने की शक्ति जाना":    "loss of smell",
    # ── Urinary ────────────────────────────────────────────────────────────────
    "बार बार पेशाब":           "polyuria",
    "पेशाब से बदबू":           "foul smell of urine",
    "मूत्राशय में परेशानी":    "bladder discomfort",
    "पेशाब में धब्बे":         "spotting urination",
    "पेशाब में जलन":           "burning micturition",
    # ── Skin ───────────────────────────────────────────────────────────────────
    "मवाद वाले दाने":          "pus filled pimples",
    "शरीर पर लाल धब्बे":       "red spots over body",
    "नाक के पास लाल घाव":      "red sore around nose",
    "रंग बदलने वाले धब्बे":    "dischromic patches",
    "त्वचा उखड़ना":            "skin peeling",
    "सूजे नाखून":              "inflammatory nails",
    "नाखून में गड्ढे":         "small dents in nails",
    "नाखून टूटना":             "brittle nails",
    "पीला पपड़ी":              "yellow crust ooze",
    "त्वचा में जलन":           "skin irritation",
    "चकत्ते":                  "skin rash",
    "छाले":                    "blister",
    "खुजली":                   "itching",
    # ── Swelling / Vascular ────────────────────────────────────────────────────
    "पिंडली में नसें उभरना":   "prominent veins on calf",
    "गांठें सूजना":            "swelled lymph nodes",
    "गांठदार त्वचा विस्फोट":   "nodal skin eruptions",
    "नसें सूजना":              "swollen blood vessels",
    "हाथ पैर सूजना":           "swollen extremeties",
    "चेहरा और आंखें सूजना":    "puffy face and eyes",
    "पैर सूजना":               "swollen legs",
    # ── Cardiac ────────────────────────────────────────────────────────────────
    "दिल की धड़कन तेज":        "fast heart rate",
    "धड़कन":                   "palpitations",
    # ── Endocrine / Metabolic ──────────────────────────────────────────────────
    "थायरॉइड बढ़ना":           "enlarged thyroid",
    "अनियमित शुगर":            "irregular sugar level",
    "अत्यधिक भूख":             "excessive hunger",
    "भूख बढ़ना":               "increased appetite",
    "मोटापा":                  "obesity",
    "वजन बढ़ना":               "weight gain",
    "वजन कम होना":             "weight loss",
    # ── General ────────────────────────────────────────────────────────────────
    "अनियमित मासिक धर्म":      "abnormal menstruation",
    "मांसपेशियों का क्षय":     "muscle wasting",
    "मांसपेशियों में कमजोरी":  "muscle weakness",
    "हाथ पैर में कमजोरी":     "weakness in limbs",
    "हाथ पैर ठंडे":           "cold hands and feets",
    "पानी की कमी":             "dehydration",
    "धंसी आंखें":              "sunken eyes",
    "आंखें लाल":               "redness of eyes",
    "आंखों से पानी":           "watering from eyes",
    "मुंह में छाले":           "ulcers on tongue",
    "होंठ सूखना":              "drying and tingling lips",
    "अकड़न":                   "movement stiffness",
    "अस्वस्थता":               "malaise",
    "बेचैनी":                  "restlessness",
    "सुस्ती":                  "lethargy",
    "घबराहट":                  "anxiety",
    "चिड़चिड़ापन":             "irritability",
    "अवसाद":                   "depression",
    "मूड बदलना":               "mood swings",
    "थकान":                    "fatigue",
    "कमजोरी":                  "weakness",
    "भूख न लगना":              "loss of appetite",
    "पसीना आना":               "sweating",
    # ── Duration phrases ───────────────────────────────────────────────────────
    "कई दिनों से":             "for several days",
    "1 हफ्ते से":              "for 1 week",
    "3 दिन से":                "for 3 days",
    "2 दिन से":                "for 2 days",
    "कल से":                   "since yesterday",
    "आज से":                   "since today",
}

# ── Tamil phrase/word map ──────────────────────────────────────────────────────
TAMIL_TO_ENGLISH: dict[str, str] = {
    # ── Fever ──────────────────────────────────────────────────────────────────
    "அதிக காய்ச்சல்":          "high fever",
    "லேசான காய்ச்சல்":         "mild fever",
    "காய்ச்சல்":               "fever",
    "குளிர்":                  "chills",
    "நடுக்கம்":                "shivering",
    # ── Respiratory ────────────────────────────────────────────────────────────
    "மூச்சு திணறல்":           "breathlessness",
    "மூச்சுத் திணறல்":         "breathlessness",
    "மார்பு வலி":              "chest pain",
    "மார்பில் இறுக்கம்":       "chest tightness",
    "சளியில் ரத்தம்":          "blood in sputum",
    "இருமலில் ரத்தம்":         "coughing of blood",
    "பிசுபிசுப்பான சளி":       "mucoid sputum",
    "துரு போன்ற சளி":          "rusty sputum",
    "சளி":                     "phlegm",
    "இருமல்":                  "cough",
    "தொண்டை கரகரப்பு":         "throat irritation",
    "தொண்டை வலி":              "sore throat",
    "தொண்டையில் திட்டுகள்":    "patches in throat",
    "சைனஸ் அழுத்தம்":          "sinus pressure",
    "மூக்கடைப்பு":             "congestion",
    "மூக்கு ஒழுகுதல்":         "runny nose",
    "தொடர் தும்மல்":           "continuous sneezing",
    # ── GI ─────────────────────────────────────────────────────────────────────
    "குமட்டல்":                "nausea",
    "வாந்தி":                  "vomiting",
    "வயிற்றுப்போக்கு":         "diarrhoea",
    "வயிற்றில் ரத்தம்":        "stomach bleeding",
    "வயிறு வீக்கம்":           "swelling of stomach",
    "வயிறு உப்புசம்":          "distention of abdomen",
    "அஜீரணம்":                 "indigestion",
    "அமிலத்தன்மை":             "acidity",
    "வயிற்று வலி":             "abdominal pain",
    "மலத்தில் ரத்தம்":         "bloody stool",
    "ஆசனவாயில் வலி":           "pain in anal region",
    "ஆசனவாயில் எரிச்சல்":      "irritation in anus",
    "மலம் கழிக்கும் போது வலி": "pain during bowel movements",
    "வாயு வெளியேறுதல்":        "passage of gases",
    "உள் அரிப்பு":             "internal itching",
    "மலச்சிக்கல்":             "constipation",
    # ── Liver / Jaundice ───────────────────────────────────────────────────────
    "கண்கள் மஞ்சளாக":          "yellowing of eyes",
    "மஞ்சள் தோல்":             "yellowish skin",
    "அடர் நிற சிறுநீர்":       "dark urine",
    "மஞ்சள் சிறுநீர்":         "yellow urine",
    "கல்லீரல் செயலிழப்பு":     "acute liver failure",
    "நீர் தேக்கம்":             "fluid overload",
    # ── Pain ───────────────────────────────────────────────────────────────────
    "கண்களுக்கு பின்னால் வலி":  "pain behind the eyes",
    "கழுத்து விறைப்பு":         "stiff neck",
    "கழுத்து வலி":              "neck pain",
    "முதுகு வலி":               "back pain",
    "மூட்டுகளில் வீக்கம்":      "swelling joints",
    "மூட்டு வலி":               "joint pain",
    "முழங்கால் வலி":            "knee pain",
    "இடுப்பு மூட்டு வலி":      "hip joint pain",
    "தசை வலி":                  "muscle pain",
    "உடல் வலி":                 "body ache",
    "நடக்கும் போது வலி":        "painful walking",
    # ── Neurological ───────────────────────────────────────────────────────────
    "ஒரு பக்க பலவீனம்":         "weakness of one body side",
    "மாற்றப்பட்ட உணர்வு":       "altered sensorium",
    "பேசுவதில் சிரமம்":         "slurred speech",
    "சுழல் உணர்வு":             "spinning movements",
    "சமநிலை இழப்பு":            "loss of balance",
    "நிலையற்ற தன்மை":           "unsteadiness",
    "தலைச்சுற்றல்":             "dizziness",
    "மயக்கம்":                  "loss of consciousness",
    "கோமா":                     "coma",
    "கவனம் குறைதல்":            "lack of concentration",
    "பார்வை குழப்பம்":          "visual disturbances",
    "மங்கலான பார்வை":           "blurred and distorted vision",
    "மணம் தெரியாமல் போதல்":     "loss of smell",
    # ── Urinary ────────────────────────────────────────────────────────────────
    "அடிக்கடி சிறுநீர்":        "polyuria",
    "சிறுநீரில் துர்நாற்றம்":   "foul smell of urine",
    "சிறுநீர்ப்பை அசௌகர்யம்":  "bladder discomfort",
    "சிறுநீரில் திட்டுகள்":     "spotting urination",
    "சிறுநீரில் எரிச்சல்":      "burning micturition",
    # ── Skin ───────────────────────────────────────────────────────────────────
    "சீழ் நிரம்பிய பருக்கள்":   "pus filled pimples",
    "உடலில் சிவப்பு திட்டுகள்": "red spots over body",
    "மூக்கருகே சிவப்பு புண்":   "red sore around nose",
    "நிற மாற்ற திட்டுகள்":      "dischromic patches",
    "தோல் உரிதல்":              "skin peeling",
    "நகம் வீக்கம்":             "inflammatory nails",
    "நகத்தில் குழிகள்":         "small dents in nails",
    "உடையக்கூடிய நகங்கள்":      "brittle nails",
    "மஞ்சள் மேலடுக்கு":         "yellow crust ooze",
    "தோல் எரிச்சல்":            "skin irritation",
    "தோல் வியாதி":              "skin rash",
    "கொப்புளம்":                "blister",
    "அரிப்பு":                  "itching",
    # ── Swelling / Vascular ────────────────────────────────────────────────────
    "கன்று காலில் நரம்பு":      "prominent veins on calf",
    "நிணநீர் கணு வீக்கம்":      "swelled lymph nodes",
    "கணு தோல் படை":             "nodal skin eruptions",
    "நரம்பு வீக்கம்":           "swollen blood vessels",
    "கை கால் வீக்கம்":          "swollen extremeties",
    "முகம் கண் வீக்கம்":        "puffy face and eyes",
    "கால் வீக்கம்":             "swollen legs",
    # ── Cardiac ────────────────────────────────────────────────────────────────
    "இதய துடிப்பு அதிகரிப்பு":  "fast heart rate",
    "படபடப்பு":                 "palpitations",
    # ── Endocrine / Metabolic ──────────────────────────────────────────────────
    "தைராய்டு வீக்கம்":         "enlarged thyroid",
    "சர்க்கரை அளவு மாறுபாடு":  "irregular sugar level",
    "அதிக பசி":                 "excessive hunger",
    "பசி அதிகரிப்பு":           "increased appetite",
    "உடல் பருமன்":              "obesity",
    "எடை அதிகரிப்பு":           "weight gain",
    "எடை குறைவு":               "weight loss",
    # ── General ────────────────────────────────────────────────────────────────
    "மாதவிலக்கு கோளாறு":        "abnormal menstruation",
    "தசை தேய்மானம்":            "muscle wasting",
    "தசை பலவீனம்":              "muscle weakness",
    "கை கால் பலவீனம்":          "weakness in limbs",
    "கை கால் குளிர்":           "cold hands and feets",
    "நீர்ச்சத்து இழப்பு":       "dehydration",
    "கண் குழிவு":               "sunken eyes",
    "கண் சிவப்பு":              "redness of eyes",
    "கண்ணீர் வடிதல்":           "watering from eyes",
    "வாயில் புண்":              "ulcers on tongue",
    "உதடு வறட்சி":              "drying and tingling lips",
    "இயக்கம் விறைப்பு":         "movement stiffness",
    "உடல் அசதி":                "malaise",
    "அமைதியின்மை":              "restlessness",
    "சோம்பல்":                  "lethargy",
    "பதட்டம்":                  "anxiety",
    "எரிச்சல்":                 "irritability",
    "மனச்சோர்வு":               "depression",
    "மனநிலை மாற்றம்":           "mood swings",
    "சோர்வு":                   "fatigue",
    "பலவீனம்":                  "weakness",
    "பசியின்மை":                "loss of appetite",
    "வியர்வை":                  "sweating",
    # ── Duration phrases ───────────────────────────────────────────────────────
    "பல நாட்களாக":              "for several days",
    "ஒரு வாரமாக":              "for 1 week",
    "3 நாட்களாக":              "for 3 days",
    "2 நாட்களாக":              "for 2 days",
    "நேற்று முதல்":            "since yesterday",
    "இன்று முதல்":             "since today",
}

# ── Regex patterns to detect remaining Indic script after phrase replacement ──
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]+")
_TAMIL_RE      = re.compile(r"[஀-௿]+")


def _local_translate(text: str, source_lang: str) -> str:
    """
    Two-pass dictionary translation fallback.
    Pass 1: longest-phrase-first substitution.
    Pass 2: word-by-word lookup for any remaining Indic tokens.
    """
    phrase_map = HINDI_TO_ENGLISH if source_lang == "hi" else TAMIL_TO_ENGLISH
    script_re  = _DEVANAGARI_RE    if source_lang == "hi" else _TAMIL_RE

    # Pass 1 — multi-word phrases (longest first)
    result = text
    for native, english in sorted(phrase_map.items(), key=lambda x: -len(x[0])):
        if native in result:
            result = result.replace(native, english)

    # Pass 2 — individual Indic tokens still remaining
    def _lookup_token(m: re.Match) -> str:
        token = m.group()
        return phrase_map.get(token, token)   # leave untranslated if unknown

    result = script_re.sub(_lookup_token, result)
    return result.strip()


async def translate_to_english(
    text: str,
    source_lang: str,
    timeout: int = 3,          # fail fast — 3 s instead of 10 s
) -> dict[str, str]:
    """
    Translate Hindi or Tamil symptom text to English.

    Priority:
      1. IndicTrans2 microservice (best accuracy, self-hosted)
      2. Local phrase map + word-token fallback (instant, covers all 133 symptoms)

    Returns:
        {"translated": str, "method": "indictrans2"|"local_map"|"passthrough"}
    """
    if source_lang == "en":
        return {"translated": text, "method": "passthrough"}

    if source_lang not in ("hi", "ta"):
        logger.warning("vaidya.translator.unsupported_lang", lang=source_lang)
        return {"translated": text, "method": "passthrough"}

    src_code = "hin_Deva" if source_lang == "hi" else "tam_Taml"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "http://indictrans2:8001/translate",
                json={"text": text, "src_lang": src_code, "tgt_lang": "eng_Latn"},
            )
            if response.status_code == 200:
                translated = response.json().get("translated", text)
                logger.info(
                    "vaidya.translator.indictrans2",
                    src=source_lang,
                    src_len=len(text),
                    tgt_len=len(translated),
                )
                return {"translated": translated, "method": "indictrans2"}

    except (httpx.ConnectError, httpx.TimeoutException):
        logger.debug(
            "vaidya.translator.indictrans2_unavailable",
            src=source_lang,
            note="falling back to local phrase map",
        )
    except Exception as exc:
        logger.warning("vaidya.translator.error", error=str(exc))

    translated = _local_translate(text, source_lang)
    phrase_map = HINDI_TO_ENGLISH if source_lang == "hi" else TAMIL_TO_ENGLISH
    logger.info(
        "vaidya.translator.local_map",
        src=source_lang,
        replaced_terms=sum(1 for p in phrase_map if p in text),
    )
    return {"translated": translated, "method": "local_map"}
