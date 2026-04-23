"""
Vaidya — audio preprocessing utilities
Handles format conversion, VAD (voice activity detection),
and quality checks before passing to Whisper.

Rural India context:
  - Patients record on cheap Android phones → lots of background noise
  - Common formats: ogg (WhatsApp voice), webm (browser MediaRecorder), mp3, wav
  - Recordings often too short (patient stops speaking early) or too long (ambient noise)
  - 2G/3G uploads = compressed, lower bitrate audio
"""

import os
import tempfile
from pathlib import Path

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Quality thresholds
MIN_DURATION_S  = 1.0    # reject clips shorter than 1 second
MAX_DURATION_S  = 120.0  # reject clips longer than 2 minutes (likely error)
MIN_RMS_ENERGY  = 0.001  # below this = silence / too quiet


def check_audio_quality(audio_path: str) -> dict:
    """
    Run basic quality checks on the audio before Whisper.
    Returns dict with 'ok' flag and 'reason' if rejected.
    """
    try:
        import librosa

        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        duration = len(y) / sr
        rms = float(np.sqrt(np.mean(y ** 2)))

        if duration < MIN_DURATION_S:
            return {"ok": False, "reason": f"Audio too short ({duration:.1f}s). Please record for at least 1 second."}

        if duration > MAX_DURATION_S:
            return {"ok": False, "reason": f"Audio too long ({duration:.0f}s). Maximum 2 minutes."}

        if rms < MIN_RMS_ENERGY:
            return {"ok": False, "reason": "Audio appears silent. Please speak clearly into the microphone."}

        return {
            "ok": True,
            "duration_s": round(duration, 2),
            "rms_energy": round(rms, 4),
            "sample_rate": sr,
        }

    except Exception as exc:
        logger.warning("vaidya.audio_qc.failed", error=str(exc))
        return {"ok": True, "reason": "quality check skipped"}  # don't block on QC failure


def reduce_noise(audio_path: str) -> str:
    """
    Light noise reduction using spectral gating (noisereduce library).
    Returns path to denoised file. Falls back to original if library unavailable.

    noisereduce is free and works well for phone microphone background noise.
    Particularly helpful for:
      - Village ambient noise (animals, wind, crowd)
      - WhatsApp voice message compression artifacts
    """
    try:
        import noisereduce as nr
        import librosa
        import soundfile as sf

        y, sr = librosa.load(audio_path, sr=16000, mono=True)

        # Use first 0.5s as noise profile (usually ambient noise before patient speaks)
        noise_sample = y[:int(sr * 0.5)] if len(y) > sr * 0.5 else y

        y_denoised = nr.reduce_noise(y=y, sr=sr, y_noise=noise_sample, prop_decrease=0.75)

        out_path = audio_path.replace(Path(audio_path).suffix, "_denoised.wav")
        sf.write(out_path, y_denoised, sr)
        logger.debug("vaidya.audio_qc.denoised", path=out_path)
        return out_path

    except ImportError:
        return audio_path   # noisereduce not installed — skip denoising
    except Exception as exc:
        logger.warning("vaidya.audio_qc.denoise_failed", error=str(exc))
        return audio_path


def convert_to_wav(input_path: str) -> str:
    """
    Convert any audio format to 16kHz mono WAV for Whisper.
    Handles: ogg (WhatsApp), webm (browser), mp3, m4a, flac.
    """
    suffix = Path(input_path).suffix.lower()
    if suffix == ".wav":
        return input_path

    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(input_path)
        audio = audio.set_frame_rate(16000).set_channels(1)

        out_path = str(Path(input_path).with_suffix("")) + "_16k.wav"
        audio.export(out_path, format="wav")
        logger.debug("vaidya.audio_qc.converted", from_fmt=suffix, to="wav")
        return out_path

    except ImportError:
        logger.warning("vaidya.audio_qc.pydub_missing")
        return input_path
    except Exception as exc:
        logger.warning("vaidya.audio_qc.convert_failed", error=str(exc))
        return input_path


def preprocess_audio(input_path: str, denoise: bool = True) -> dict:
    """
    Full preprocessing pipeline:
      1. Convert to 16kHz WAV
      2. Quality check (duration, energy)
      3. Noise reduction (optional)

    Returns:
        {
            "ok": bool,
            "processed_path": str,
            "reason": str (if not ok),
            "quality": dict
        }
    """
    # Step 1: Convert format
    wav_path = convert_to_wav(input_path)

    # Step 2: Quality check
    quality = check_audio_quality(wav_path)
    if not quality["ok"]:
        return {"ok": False, "processed_path": wav_path, "reason": quality["reason"], "quality": quality}

    # Step 3: Noise reduction
    if denoise:
        wav_path = reduce_noise(wav_path)

    return {
        "ok": True,
        "processed_path": wav_path,
        "quality": quality,
    }
