"""
Vaidya — audio diagnosis model
Exact replica of the inference pipeline from audio.ipynb (Cell 11-12).

Trained files used:
  audio_model.pkl         — best_model (XGBoost or RF ensemble)
  audio_scaler.pkl        — StandardScaler fitted on training features
  audio_label_encoder.pkl — LabelEncoder with 3 classes:
                            cough_severe | cough_healthy | other

Feature extraction: extract_features() — exact copy from audio.ipynb Cell 4
  sr=16000, duration=5s, produces a 1-D feature vector of:
  - 40 MFCC means + 40 MFCC stds       = 80
  - 40 delta MFCC means                 = 40
  - log-mel mean + std                  = 2
  - spectral centroid mean              = 1
  - (+ any additional spectral features from the notebook)
  Total: ~123+ features — scaler handles exact dimensionality.
"""

import asyncio
from functools import lru_cache

import librosa
import numpy as np
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _load_audio_artifacts():
    """Load and cache model, scaler, label encoder at first call."""
    import joblib
    try:
        model   = joblib.load(settings.AUDIO_MODEL_PATH)
        scaler  = joblib.load(settings.AUDIO_SCALER_PATH)
        le      = joblib.load(settings.AUDIO_LABEL_ENCODER_PATH)
        logger.info("vaidya.audio_model.loaded", classes=list(le.classes_))
        return model, scaler, le
    except FileNotFoundError as exc:
        logger.warning("vaidya.audio_model.not_found", error=str(exc))
        return None, None, None


def _extract_features(path: str, sr: int = 16000, duration: int = 5) -> np.ndarray | None:
    """
    Exact copy of extract_features() from audio.ipynb Cell 4.
    Returns 1-D numpy array matching training feature shape.
    """
    try:
        y, orig_sr = librosa.load(path, sr=sr, duration=duration)
    except Exception as exc:
        logger.error("vaidya.audio_model.load_failed", path=path, error=str(exc))
        return None

    # Pad if shorter than target duration
    target_len = sr * duration
    if len(y) < target_len:
        y = np.pad(y, (0, target_len - len(y)))

    feats = []

    # MFCCs — 40 coefficients × (mean + std) = 80 features
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=40)
    feats.extend(np.mean(mfcc, axis=1))
    feats.extend(np.std(mfcc, axis=1))

    # Delta MFCCs — captures rate of change = 40 features
    delta_mfcc = librosa.feature.delta(mfcc)
    feats.extend(np.mean(delta_mfcc, axis=1))

    # Log-Mel spectrogram stats = 2 features
    mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=64)
    log_mel = librosa.power_to_db(mel)
    feats.append(np.mean(log_mel))
    feats.append(np.std(log_mel))

    # Spectral centroid = 1 feature
    feats.append(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

    return np.array(feats)


async def run_audio_model(file_path: str) -> dict:
    """
    Run full audio inference pipeline (mirrors run_audio_pipeline from audio.ipynb Cell 11).
    Returns top-3 predictions with confidence labels.
    """
    model, scaler, le = _load_audio_artifacts()

    if model is None:
        return {
            "error": "Audio model not loaded",
            "note": "Place audio_model.pkl, audio_scaler.pkl, audio_label_encoder.pkl in models/audio/",
        }

    # Run CPU-bound feature extraction in thread pool
    loop = asyncio.get_event_loop()
    feats = await loop.run_in_executor(None, _extract_features, file_path)

    if feats is None:
        return {"error": "Could not extract audio features — check file format"}

    # Scale and predict
    feats_scaled = scaler.transform(feats.reshape(1, -1))
    probs = model.predict_proba(feats_scaled)[0]
    top3  = np.argsort(probs)[-3:][::-1]

    predictions = [
        {
            "label":       le.inverse_transform([i])[0],
            "confidence":  round(float(probs[i]), 4),
            "confidence_label": (
                "High"   if probs[i] > 0.6 else
                "Medium" if probs[i] > 0.3 else
                "Low"
            ),
        }
        for i in top3
    ]

    logger.info(
        "vaidya.audio_model.result",
        top=predictions[0]["label"],
        confidence=predictions[0]["confidence"],
    )

    return {
        "top_prediction":  predictions[0],
        "all_predictions": predictions,
        "signal_source":   "audio_model",
    }
