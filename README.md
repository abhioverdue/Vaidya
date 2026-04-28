# Vaidya — AI Health Triage for Rural India

> **Multimodal AI triage system that lets a rural patient describe symptoms by voice or text, get an instant diagnosis with triage urgency level, and find the nearest government hospital — in Tamil, Hindi, or English.**

Live backend: `http://18.60.50.83:8000` &nbsp;·&nbsp; [API docs](http://18.60.50.83:8000/docs) &nbsp;·&nbsp; Built for **Google AI Solutions Challenge 2026**

---

## The Problem

600 million rural Indians have no reliable access to a doctor. ASHA workers (village health volunteers) handle hundreds of patients per month with no digital tools. District health officers have no real-time visibility into disease outbreaks until they've already spread.

Vaidya gives every patient, ASHA worker, and health officer a medical AI in their pocket — in their own language, offline-capable, and free.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     VAIDYA MOBILE APP                        │
│             (Expo / React Native · TypeScript)               │
│                                                              │
│   Voice Input     Text Input     Image Input    Find Care    │
│   (Whisper STT)   (Gemini)      (Vision CNN)   (G-Maps)     │
└───────┬───────────────┬──────────────┬──────────────┬────────┘
        │               │              │              │
        ▼               ▼              ▼              ▼
┌──────────────────────────────────────────────────────────────┐
│                  FASTAPI BACKEND  (AWS ECS)                   │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │             MULTIMODAL FUSION ENGINE                  │   │
│   │                                                      │   │
│   │   XGBoost Classifier   Audio CNN    Vision CNN       │   │
│   │   (132 diseases)       (Cough)      (Chest/Skin)     │   │
│   │          └──────────────┴────────────┘               │   │
│   │                Adaptive Confidence Fusion             │   │
│   │                         │                            │   │
│   │              Gemini 2.5 Flash  ← LLM fallback        │   │
│   │              (structured JSON output)  conf < 0.6    │   │
│   └─────────────────────────┬────────────────────────────┘   │
│                             │                                 │
│   ┌─────────────────────────▼────────────────────────────┐   │
│   │         TRIAGE ENGINE (Deterministic Rules)           │   │
│   │   Level 1 Self-care → Level 5 Emergency (108)        │   │
│   └──────────────────────────────────────────────────────┘   │
│                                                              │
│   Google Places API  →  Hospital Finder (PHC/CHC/District)   │
│   Firebase Firestore →  Outbreak Detection & Analytics       │
│   Firebase FCM v1    →  ASHA Worker Push Notifications       │
│   Redis (Upstash)    →  Response Caching                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Google AI Integrations

| Product | How Vaidya uses it |
|---|---|
| **Gemini 2.5 Flash** | LLM fallback diagnosis when model confidence < 60%; multimodal vision analysis of chest X-rays, skin lesions, and wound images |
| **Google Places New API** | 6 parallel requests (nearby + text search) to find PHCs, CHCs, district hospitals, and ESIC facilities within 50 km — classified by Indian health tier |
| **Firebase Firestore** | Real-time session storage, ASHA worker dispatch, outbreak signal aggregation across districts |
| **Firebase Cloud Messaging (FCM v1)** | Push alerts to ASHA workers when a high-urgency patient is triaged in their catchment area (OAuth2, migrated from deprecated legacy keys) |
| **Google Maps SDK** | Native Android map with colour-coded hospital pins by facility type (PHC / CHC / District / Private) |

---

## AI / ML Pipeline

### 1 · Speech-to-Text
**faster-whisper** (CTranslate2 int8) — 4–5× faster than standard Whisper on CPU. Auto-detects Tamil, Hindi, English, Telugu, Malayalam, Kannada.

### 2 · Symptom Extraction
**spaCy NER** extracts symptom entities, body parts, duration, and severity from free-form text. Custom normalisation maps 500+ colloquial terms to canonical medical symptoms.

### 3 · Multi-Signal Fusion
- **XGBoost** — 132 diseases, 400+ symptom features
- **Audio CNN** — cough severity (healthy / mild / severe) from 5-second clips
- **Vision CNN** — EfficientNet-B3 + ResNet-50 ensemble for chest / skin / wound
- Signals weighted by availability and individual confidence; domain-aware corroboration (cough severity boosts respiratory disease probability)

### 4 · LLM Fallback
When fusion confidence < 0.60, **Gemini 2.5 Flash** generates a structured JSON diagnosis with precautions and ICD hint. Temperature 0.15 for deterministic clinical output.

### 5 · Triage Engine
Deterministic rule engine (not ML) for CDSCO SaMD regulatory alignment. Red-flag conditions always escalate to Level 4–5 regardless of model confidence.

| Level | Label | Action |
|---|---|---|
| 1 | Self-care | Home remedies |
| 2 | Monitor | Watch & wait |
| 3 | See a doctor | PHC visit within 24 h |
| 4 | Urgent | Same-day referral |
| 5 | Emergency | Call 108 immediately |

---

## Features

### For Patients
- Describe symptoms by **voice, text, or photo** in their own language
- Instant diagnosis with triage level, red flags, and precautions
- Find the **nearest PHC / CHC / government hospital** with directions
- PMJAY empanelment status for each facility
- Works on **₹8,000 Android phones** with 2G

### For ASHA Workers
- Live **patient queue** ordered by triage urgency
- **Push notifications** for Level 4–5 cases in their village
- 30-day **activity stats** and top diagnoses

### For District Health Officers
- Real-time **district dashboard** — sessions, outbreaks, ASHA performance
- **Disease hotspots** map with case density
- Automatic **outbreak alerts** when a disease crosses threshold
- **7-day disease forecast** with confidence score
- **Live triage stream** — real-time feed of sessions as they complete

---

## Tech Stack

**Frontend** — Expo / React Native (TypeScript), Expo Router, Zustand, React Query, Firebase Auth, react-native-maps, react-native-reanimated, react-i18next

**Backend** — FastAPI, XGBoost, PyTorch, faster-whisper, spaCy, Gemini 2.5 Flash, SQLAlchemy, Redis (Upstash), Celery, structlog, Prometheus, Sentry

**Infrastructure** — AWS ECS Fargate (ap-south-2), Docker multi-stage build, Firebase Firestore, Firebase FCM v1, Google Places New API, ECR

---

## Project Structure

```
vaidya/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   ├── diagnosis/   # fusion.py · classifier.py · audio_model.py · vision_model.py · llm_fallback.py
│   │   │   ├── nlp/         # extractor.py · transcriber.py · translator.py · language_detector.py
│   │   │   ├── triage/      # engine.py (deterministic rule engine)
│   │   │   ├── care/        # google_places.py · overpass.py (OSM fallback)
│   │   │   └── notifications/ # FCM v1 push
│   │   └── routers/api/v1/  # REST endpoints
│   ├── Dockerfile           # multi-stage · non-root user · health checks
│   └── deploy.sh            # one-command ECS redeploy
├── frontend/
│   ├── src/app/             # Expo Router screens (symptom · care · ASHA · analytics)
│   ├── src/services/        # API client · Firebase auth · demo fallback
│   └── src/components/      # Design system (COLORS · TYPE · RADIUS)
└── notebooks/               # Training: nlp.ipynb · audio.ipynb · images.ipynb
```

---

## Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
python -m spacy download en_core_web_sm
# copy .env.example → .env and fill in keys
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npx expo start
# Build APK:  eas build --profile preview --platform android
```

### Required Environment Variables
```
GEMINI_API_KEY
GOOGLE_MAPS_API_KEY
FIREBASE_PROJECT_ID
FIREBASE_SERVICE_ACCOUNT_KEY   # base64 encoded JSON
REDIS_URL
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/diagnose/predict` | Multimodal triage (text + audio + image) |
| `POST` | `/api/v1/diagnose/predict/text` | Text-only triage |
| `GET` | `/api/v1/care/hospitals` | Nearby hospitals via Google Places |
| `GET` | `/api/v1/analytics/dashboard/district` | District health KPIs |
| `GET` | `/api/v1/analytics/outbreaks/active` | Active outbreak alerts |
| `GET` | `/api/v1/asha/nearby` | Nearby ASHA workers by GPS |
| `GET` | `/health` | Health check |

Interactive docs: [http://18.60.50.83:8000/docs](http://18.60.50.83:8000/docs)

---

## Impact

- **600M+** rural Indians with limited healthcare access
- **1M+ ASHA workers** across India currently using paper-based systems
- Supports **6 Indian languages** — Tamil, Hindi, English, Telugu, Malayalam, Kannada
- Zero consultation fees · works offline · runs on low-end Android
