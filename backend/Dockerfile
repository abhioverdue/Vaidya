# ── Base image ────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

# System deps: audio (libsndfile), ML (libgomp for XGBoost)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    libgomp1 \
    ffmpeg \
    curl \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Use pip directly — uv does not honour --extra-index-url inside requirements.txt,
# which is needed to pull the PyTorch CPU-only wheels.
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Download spaCy model (en_core_web_sm — used by extractor.py NER pass)
RUN python -m spacy download en_core_web_sm

# Models are downloaded into the Cloud Build workspace by cloudbuild.yaml
# and copied here from the build context
COPY models/ /app/models/

# ── Development target ─────────────────────────────────────────────────────────
FROM base AS development

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production target ──────────────────────────────────────────────────────────
FROM base AS production

COPY . .

# Non-root user for security
RUN addgroup --system vaidya && adduser --system --ingroup vaidya vaidya
USER vaidya

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 1 --bind "0.0.0.0:${PORT:-8000}" --timeout 300
