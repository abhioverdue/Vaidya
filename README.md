# Vaidya — AI Health Triage for Rural India

Vaidya is a multimodal AI triage system built for rural and peri-urban India. It combines on-device machine learning with cloud AI to deliver symptom assessment, triage classification, and care navigation — in English, Hindi, and Tamil — with or without an internet connection.

---

## What it does

A patient describes their symptoms by voice, text, or quick-tap chips. Vaidya runs them through a trained XGBoost classifier (132 diseases, 133 canonical symptoms). When confidence falls below threshold, Google Gemini 1.5 Flash is invoked for nuanced reasoning. The result is a triage level (1–5), primary diagnosis, differential, red-flag warnings, a plain-language description, and actionable precautions — all in the patient's language.

When there is no internet, the same symptom vector runs through a 261 KB TFLite model bundled directly in the APK.

---

## Architecture

```
Patient device (React Native / Expo)
│
├─ Online path
│   └─ FastAPI backend
│       ├─ Whisper STT          — voice → transcript
│       ├─ spaCy NLP extractor  — text → 133-feature binary vector
│       ├─ XGBoost classifier   — vector → ranked diagnoses
│       ├─ Gemini 1.5 Flash     — fallback when confidence < 0.60
│       ├─ Audio XGBoost        — respiratory audio analysis
│       ├─ Vision PyTorch       — chest X-ray / skin / wound
│       └─ Fusion engine        — weighted combination of all signals
│
└─ Offline path
    └─ TFLite (261 KB, bundled in APK)
        └─ Same 133-symptom input → 132-disease output
```

**Infrastructure (Docker Compose)**

| Service | Purpose |
|---|---|
| `api` | FastAPI + Uvicorn (async) |
| `celery_worker` | Background jobs (ASHA notifications, analytics) |
| `celery_beat` | Scheduled tasks (outbreak detection, reports) |
| `postgres` | TimescaleDB — PostgreSQL 15 + time-series |
| `redis` | Cache (hospitals 24h, symptoms 10min, geocoding 1h) |
| `nginx` | Reverse proxy + TLS termination |
| `prometheus` + `grafana` | Metrics and dashboards |
| `vault` | Secrets management (production) |

---

## Machine Learning Models

### NLP Symptom Classifier
**Notebook:** `notebooks/nlp2.ipynb`

XGBoost multi-class classifier trained on the Kaggle Disease-Symptom dataset.

| Artifact | File | Size |
|---|---|---|
| Classifier | `backend/models/nlp/final_nlp_model.pkl` | 14 MB |
| Label encoder | `backend/models/nlp/label_encoder.pkl` | 1.2 KB |
| Symptom list | `backend/models/nlp/final_symptom_list.pkl` | 2.3 KB |

- Input: `float32[1, 133]` — binary presence of each canonical symptom
- Output: probabilities over 132 disease classes
- Inference mirrors `predict_disease()` from notebook Cell 12 exactly

### Audio Respiratory Classifier
**Notebook:** `notebooks/audio.ipynb`

XGBoost classifier on MFCC + spectral features extracted from respiratory recordings.

| Artifact | File | Size |
|---|---|---|
| Model | `backend/models/audio/audio_model.pkl` | 41 MB |
| Scaler | `backend/models/audio/audio_scaler.pkl` | 3.9 KB |
| Label encoder | `backend/models/audio/audio_label_encoder.pkl` | 512 B |

- Classes: `cough_severe`, `cough_healthy`, `other`
- Features: librosa MFCC, zero-crossing rate, spectral centroid

### Vision Multi-Task Model
**Notebook:** `notebooks/Computer_Vision_AIforHealth.ipynb`

PyTorch `HybridMultiTaskModel` with three task heads trained on public medical image datasets.

| Artifact | File | Size |
|---|---|---|
| Weights | `backend/models/vision/hybrid_multitask_model.pth` | 170 MB |

- Task heads: chest (bacterial/viral pneumonia), skin conditions, wound classification
- Accepts JPEG/PNG via `POST /api/v1/diagnose/image`

### On-Device TFLite Model

Converted from the XGBoost NLP classifier — same weights, same feature space, 261 KB.

| Artifact | File | Size |
|---|---|---|
| TFLite | `frontend/src/assets/models/vaidya_symptom_classifier.tflite` | 261 KB |
| ONNX (web fallback) | `frontend/src/assets/models/vaidya_symptom_classifier.onnx` | 4.6 MB |
| Disease labels | `frontend/src/assets/models/disease_labels.json` | 784 B |
| Symptom list | `frontend/src/assets/models/symptom_list.json` | 2.7 KB |

To rebuild the TFLite model from the XGBoost source:

```bash
cd backend
python - <<'EOF'
import joblib, numpy as np, tensorflow as tf

model   = joblib.load("models/nlp/final_nlp_model.pkl")
encoder = joblib.load("models/nlp/label_encoder.pkl")
cols    = joblib.load("models/nlp/final_symptom_list.pkl")

@tf.function(input_signature=[tf.TensorSpec([None, len(cols)], tf.float32)])
def predict(x):
    return tf.py_function(
        lambda v: model.predict_proba(v.numpy()).astype(np.float32), [x], tf.float32
    )

converter = tf.lite.TFLiteConverter.from_concrete_functions(
    [predict.get_concrete_function()]
)
tflite_model = converter.convert()
open("../frontend/src/assets/models/vaidya_symptom_classifier.tflite", "wb").write(tflite_model)
print(f"TFLite: {len(tflite_model) // 1024} KB")
EOF
```

---

## Gemini AI Integration

Gemini 1.5 Flash is used in two places:

### 1. Diagnosis fallback
**File:** `backend/app/services/diagnosis/llm_fallback.py`

Triggered automatically when XGBoost confidence is below `0.60`. Gemini receives the extracted symptom list, severity, duration, and red flags, and returns a structured JSON response with primary diagnosis, differential, triage level, description, and precautions.

```
POST /api/v1/llm/diagnose         — explicit LLM diagnosis (bypass XGBoost)
POST /api/v1/llm/diagnose/stream  — streaming response via SSE
```

### 2. Disease metadata enrichment
**File:** `backend/app/services/diagnosis/classifier.py`

When a disease has no description or precautions in cache, Gemini is called once on-demand with a structured JSON-schema prompt. The result is stored in the module-level cache — subsequent requests for the same disease are free.

**Setup:** Get a free key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) (free tier: 15 RPM, 1M tokens/day).

```bash
# backend/.env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-1.5-flash
```

---

## eSanjeevani Integration

eSanjeevani is India's national teleconsultation platform. After a triage result, patients can book a government OPD slot without leaving the app.

```
GET  /api/v1/care/teleconsult               — list available slots
POST /api/v1/care/teleconsult/book          — book a slot
GET  /api/v1/care/teleconsult/{id}/status   — check booking status
POST /api/v1/care/teleconsult/{id}/cancel   — cancel booking
GET  /api/v1/care/coverage                  — PMJAY / state scheme eligibility
```

Hospital and PHC discovery uses the OpenStreetMap Overpass API ranked by distance, facility type, and 108 ambulance availability. ABDM facility registry is used as a secondary source.

```bash
# backend/.env
ESANJEEVANI_BASE_URL=https://esanjeevaniopd.in/api/v2
ABDM_BASE_URL=https://dev.abdm.gov.in/gateway
ABDM_CLIENT_ID=your_abdm_client_id
ABDM_CLIENT_SECRET=your_abdm_client_secret
```

---

## API Reference

All routes are under `/api/v1` with rate limiting applied globally. Interactive docs at `http://localhost:8000/docs`.

| Module | Prefix | Key endpoints |
|---|---|---|
| Input | `/input` | `POST /text`, `POST /voice`, `WS /voice/stream` |
| NLP | `/nlp` | `POST /extract`, `GET /symptoms` |
| Diagnose | `/diagnose` | `POST /predict`, `POST /predict/text`, `POST /audio`, `POST /image` |
| LLM | `/llm` | `POST /diagnose`, `POST /diagnose/stream` |
| Triage | `/triage` | `POST /assess`, `POST /emergency`, `GET /levels` |
| Care | `/care` | `GET /hospitals`, `GET /teleconsult`, `POST /teleconsult/book` |
| Patients | `/patients` | `POST /`, `GET /{id}`, `DELETE /{id}` |
| ASHA | `/asha` | `GET /queue`, `GET /nearby`, `POST /resolve/{id}` |
| Consent | `/consent` | `POST /grant`, `POST /revoke`, `GET /status/{id}`, `GET /audit/{id}` |
| Analytics | `/analytics` | `GET /dashboard/district`, `GET /outbreaks/active`, `GET /hotspots` |

---

## Mobile App

Built with Expo 54 + React Native 0.81. Primary target: Android. iOS supported.

**Screens**
- Language select — English / हिन्दी / தமிழ்
- Symptom input — voice, free text, quick-tap chips, duration and severity
- Analysis — animated step-by-step progress
- Result — triage level, diagnosis, confidence, red flags, precautions, differential
- Care finder — GPS map + facility list filtered by type (PHC / CHC / District / Private)
- Settings — language, AI model status, privacy controls

**Offline mode**

The TFLite model is bundled in the APK. When offline, symptom text is normalized to canonical names via a 150+ alias dictionary (English, romanized Hindi, romanized Tamil), then run through on-device inference. Results include triage level and differential — no network required.

**Languages**

| Language | Voice input | UI |
|---|---|---|
| English | ✓ | ✓ |
| Hindi | ✓ | ✓ |
| Tamil | ✓ | ✓ |

---

## Getting Started

### Prerequisites

- Docker Compose v2+
- Node.js 20+
- EAS CLI — `npm install -g eas-cli`
- Gemini API key — [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

### Backend

```bash
# 1. Copy and fill environment variables
cp backend/.env.example backend/.env
# At minimum: GEMINI_API_KEY, SECRET_KEY

# 2. First-time setup — builds image, starts all services, runs migrations, seeds data
make setup

# 3. Verify health
make verify
# → API ✓  DB ✓  Redis ✓  Gemini ✓

# Day-to-day
make logs    # tail all logs
make down    # stop everything
make test    # run pytest
```

### Android APK (preview build)

```bash
cd frontend
npm install

# Link to your EAS account (first time only)
eas login
eas build:configure

# Set your machine's LAN IP in eas.json → build.preview.env.EXPO_PUBLIC_API_URL
# e.g. "EXPO_PUBLIC_API_URL": "http://192.168.1.x:8000"
# Find your IP: ipconfig (Windows) or ifconfig (Mac/Linux)

npx eas build --platform android --profile preview
# Scan the QR code from the EAS dashboard to install
```

### Local development

```bash
cd frontend
npm install
echo "EXPO_PUBLIC_API_URL=http://192.168.1.x:8000" > .env
npx expo start
```

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Google AI Studio key |
| `GEMINI_MODEL` | No | Default: `gemini-1.5-flash` |
| `DATABASE_URL` | Yes | PostgreSQL async URL |
| `REDIS_URL` | No | Default: `redis://redis:6379/0` |
| `SECRET_KEY` | Yes | JWT signing key (`openssl rand -hex 32`) |
| `ESANJEEVANI_BASE_URL` | No | eSanjeevani OPD API base |
| `ABDM_CLIENT_ID` | No | ABDM gateway client ID |
| `ABDM_CLIENT_SECRET` | No | ABDM gateway secret |
| `SENTRY_DSN` | No | Error tracking |
| `FCM_SERVER_KEY` | No | Firebase push notifications |

### Frontend (`frontend/.env`)

| Variable | Description |
|---|---|
| `EXPO_PUBLIC_API_URL` | Backend URL (e.g. `http://192.168.1.x:8000`) |

---

## Project Structure

```
Vaidya-gemini/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # Route handlers (10 modules)
│   │   ├── core/               # Config, security, database
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   └── services/
│   │       ├── diagnosis/      # classifier, fusion, llm_fallback, audio, vision
│   │       ├── nlp/            # extractor, transcriber, translator, detector
│   │       ├── triage/         # rule engine
│   │       ├── care/           # hospital finder, eSanjeevani, ABDM
│   │       └── notifications/  # FCM, SMS
│   ├── models/                 # Trained ML artifacts
│   ├── migrations/             # Alembic scripts
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                # Expo Router screens
│   │   ├── components/ui/      # Shared UI components
│   │   ├── constants/          # Design tokens, colors, typography
│   │   ├── hooks/              # useTriage, useDemoMode
│   │   ├── services/           # API client, offline model, demo data
│   │   ├── store/              # Zustand global state
│   │   └── assets/models/      # Bundled TFLite + labels
│   ├── app.json
│   └── eas.json
├── notebooks/
│   ├── nlp2.ipynb                          # NLP classifier training
│   ├── audio.ipynb                         # Audio model training
│   └── Computer_Vision_AIforHealth.ipynb   # Vision model training
├── docker-compose.yml
└── Makefile
```

---

## Compliance

- **DPDP Act 2023** — Consent grant, revoke, and immutable audit trail via `/api/v1/consent/*`. Right-to-delete at `DELETE /api/v1/patients/{id}`.
- **ABDM** — Health ID integration for patient identity.
- **No PII stored** — Session records are anonymized. Audio and images are not persisted after inference.

---

## Disclaimer

Vaidya is an AI-assisted triage aid. It does not replace examination, diagnosis, or prescription by a licensed physician. In a medical emergency, call **108** immediately.

