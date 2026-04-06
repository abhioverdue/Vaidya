# Vaidya — Deployment Guide

## Changes in this build
| Area | Change |
|------|--------|
| LLM | **Ollama / Llama replaced with Google Gemini 1.5 Flash** (free tier, 15 RPM) |
| Seed data | `seed_demo.sql` auto-loads 50 Tamil Nadu hospitals + 100 ASHA workers |
| UI/UX | Complete premium redesign — new design system, all 6 screens rebuilt |
| TFLite | XGBoost → knowledge-distilled neural network → TFLite (see `scripts/xgb_to_tflite.py`) |

---

## 1. Prerequisites
```bash
# Install
docker compose v2+, node 20+, expo-cli, eas-cli
```

## 2. Backend — Docker Compose

```bash
# 1. Copy env
cp .env.example .env
# Edit .env — set GEMINI_API_KEY (free at https://aistudio.google.com/app/apikey)

# 2. Start all services (Postgres seeds run automatically on first boot)
docker compose up -d

# 3. Run migrations
docker compose exec api alembic upgrade head

# 4. Verify seed data
docker compose exec postgres psql -U vaidya -d vaidya \
  -c "SELECT COUNT(*) FROM hospitals; SELECT COUNT(*) FROM asha_workers;"
# Expected: 50 hospitals, 100 ASHA workers
```

## 3. TFLite model (if rebuilding)

```bash
# Install dependencies
pip install xgboost scikit-learn joblib tensorflow numpy

# Run conversion (requires trained XGBoost model in models/nlp/)
python scripts/xgb_to_tflite.py

# Output written to: frontend/src/assets/models/
#   vaidya_symptom_classifier.tflite  (~260 KB)
#   disease_labels.json
#   symptom_list.json
```

## 4. Android APK — EAS Build

```bash
cd frontend

# Install deps
npm install

# Log in to Expo
npx eas login

# Configure (first time only)
npx eas build:configure

# Build APK (free tier — ~15 min queue)
npx eas build --platform android --profile preview

# Download the .apk from the URL printed in terminal
# OR build locally (requires Android SDK):
npx expo run:android --variant release
```

### app.json API URL
Edit `frontend/app.json` → `extra.apiBaseUrl`:
- **Android emulator**: `http://10.0.2.2:8000`
- **Physical device** on same WiFi: `http://192.168.X.X:8000`
- **Production**: `https://your-domain.com`

## 5. Offline mode
The app works fully offline:
- TFLite model bundled in APK (~260 KB)
- Symptom list and disease labels bundled
- Falls back to on-device inference when no network

## 6. Gemini API key
- Free tier: **15 RPM, 1 million tokens/day** — sufficient for a rural PHC
- Get key: https://aistudio.google.com/app/apikey
- Set in `.env` as `GEMINI_API_KEY=...`
- The backend `llm_fallback.py` calls `gemini-1.5-flash` directly via REST

## 7. Architecture

```
Android APK (Expo)
  ├── Online:  FastAPI → Gemini 1.5 Flash → XGBoost → PostgreSQL
  └── Offline: TFLite (distilled XGBoost, 132 diseases)

Docker services:
  postgres   (TimescaleDB) — patient data, hospitals, ASHA workers
  redis      — symptom cache, session cache
  api        (FastAPI)     — all ML inference + API
  celery     — ASHA alerts, follow-up tasks
  nginx      — reverse proxy
  prometheus + grafana — observability
```
