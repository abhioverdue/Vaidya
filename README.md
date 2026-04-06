# Vaidya-gemini

AI-powered rural health triage app — offline-capable, multilingual (EN/HI/TA), powered by Google Gemini 1.5 Flash + TFLite on-device model.

---

## What's in this repo

```
Vaidya-gemini/
├── backend/          FastAPI (Python) — AI triage engine
├── frontend/         Expo React Native — Android APK + Web
├── scripts/          DB seeds, model conversion, load tests
├── nginx/            Reverse proxy config
├── grafana/          Dashboards
├── monitoring/       Prometheus config
├── docker-compose.yml         Local dev
├── docker-compose.prod.yml    Production
└── .env.example               Copy → .env and fill in secrets
```

---

## Quick Start

### 1. Backend (Docker)

```bash
cp .env.example .env
# Edit .env → set GEMINI_API_KEY (free at https://aistudio.google.com/app/apikey)

docker compose up -d
docker compose exec api alembic upgrade head
# Seeds 50 TN hospitals + 100 ASHA workers automatically on first boot
```

Backend runs at **http://localhost:8000** — API docs at **http://localhost:8000/docs**

---

### 2a. Android APK (via EAS — no Android Studio needed)

```bash
cd frontend
npm install

# Set your backend URL
cp .env.template .env
# Edit .env:
#   Physical device on same WiFi: EXPO_PUBLIC_API_URL=http://192.168.X.X:8000
#   Android emulator:             EXPO_PUBLIC_API_URL=http://10.0.2.2:8000

# Login to Expo (free account)
npx eas login

# Build APK — takes ~15 min on EAS free tier, no local Android SDK needed
npx eas build --platform android --profile preview

# APK download link printed in terminal when done
```

### 2b. Android APK (local build — needs Android Studio)

```bash
cd frontend
npm install
npx expo run:android --variant release
# APK at: android/app/build/outputs/apk/release/app-release.apk
```

---

### 3. Web (browser)

```bash
cd frontend
npm install

# Dev server with hot reload
npm run web
# Opens at http://localhost:8081

# Static export (deploy to Netlify / Vercel / nginx)
npm run build:web
# Output at: frontend/dist/
```

> **Web note:** Native-only modules (`@tensorflow/tfjs-react-native`, `react-native-maps`)
> are stubbed out via `metro.config.js` → `src/stubs/nativeStub.js`.
> Offline TFLite inference runs via `@tensorflow/tfjs-backend-cpu` (WebAssembly) on web.

---

## Offline Mode

The APK/web app works fully without internet:
- TFLite model (`vaidya_symptom_classifier.tflite`, ~260 KB) bundled in app
- `useTriage.ts` → `normaliseToCanonical()` maps natural-language symptoms to model features
- Covers English, Hindi (romanised), Tamil (romanised) symptom terms
- Minimum 3 symptoms required for offline inference

---

## Bug Fixes Applied (vs original)

| Fix | File | Description |
|-----|------|-------------|
| FIX-1 | offlineModel.ts | Use `loadTFLiteModel()` not `tf.loadGraphModel()` for .tflite |
| FIX-2 | offlineModel.ts | Concurrent load guard — no double GPU allocation |
| FIX-3 | offlineModel.ts | `await tensor.data()` instead of blocking `dataSync()` |
| FIX-4 | offlineModel.ts | Reset `loadAttempted` on explicit dispose |
| FIX-5 | useTriage.ts | `normaliseToCanonical()` EN/HI/TA → canonical symptom names |
| FIX-6 | useTriage.ts | Analysis steps advance only as work actually completes |
| FIX-7 | offlineModel.ts | Remove `react-native-fs`, use `expo-file-system` |
| FIX-8 | offlineModel.ts | Web platform guard for tfjs-react-native GL backend |
| FIX-9 | offlineModel.ts | Guard `FileSystem` calls from web |
| Web | metro.config.js | Stub native-only modules for web bundling |
| LLM | extractor.py | Replaced Ollama with Gemini 1.5 Flash |

---

## Key Env Vars

| Variable | Where | Description |
|----------|-------|-------------|
| `GEMINI_API_KEY` | `.env` | Get free at aistudio.google.com |
| `EXPO_PUBLIC_API_URL` | `frontend/.env` | Backend URL for the app |
| `POSTGRES_PASSWORD` | `.env` | DB password |
| `SECRET_KEY` | `.env` | JWT secret — use `openssl rand -hex 32` |

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Mobile/Web | Expo 51, React Native 0.74, expo-router |
| On-device AI | TFLite (132-disease XGBoost distilled model) |
| Backend AI | Google Gemini 1.5 Flash |
| Backend API | FastAPI + Celery + PostgreSQL (TimescaleDB) + Redis |
| Languages | English, Hindi, Tamil |
| Observability | Prometheus + Grafana |
# Vaidya
# Vaidya
# Vaidya
