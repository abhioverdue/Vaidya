"""
Vaidya — vision model service
Exact inference replica from Computer_Vision_AIforHealth.ipynb (Cell 5).

Trained file: hybrid_multitask_model.pth
  Architecture: HybridMultiTaskModel — dual EfficientNet-B3 + ResNet-50 backbones
  Task heads (dataset_type arg selects which head to use):
    "chest"  → 4 classes: bacterial_pneumonia | viral_pneumonia | normal | (other)
    "skin"   → skin disease classes from SkinDisease dataset
    "wound"  → wound classification classes from Wound_dataset

Transform (val_transform from notebook Cell 5, albumentations):
  A.Resize(224, 224)
  A.Normalize(mean=(0.485,0.456,0.406), std=(0.229,0.224,0.225))
  ToTensorV2()

Usage: pass image path + dataset_type ("chest" | "skin" | "wound")
Default dataset_type is inferred from filename if not provided.
"""

import asyncio
import base64
import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import structlog
import torch

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Class labels per task head — from Kaggle dataset structures used in training
CHEST_CLASSES  = ["bacterial_pneumonia", "viral_pneumonia", "normal", "other"]
SKIN_CLASSES   = ["Acne", "Eczema", "Psoriasis", "Rosacea", "Seborrheic_Dermatitis", "Normal"]
WOUND_CLASSES  = ["abrasion", "bruise", "burn", "cut", "diabetic_wound", "laceration", "normal", "pressure_wound", "surgical_wound", "venous_wound"]

TASK_CLASSES = {
    "chest": CHEST_CLASSES,
    "skin":  SKIN_CLASSES,
    "wound": WOUND_CLASSES,
}

# Below this top-prediction confidence, fall back to Gemini vision
VISION_CONFIDENCE_THRESHOLD = 0.50

_MIME_MAP = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
             ".gif": "image/gif", ".webp": "image/webp"}


@lru_cache(maxsize=1)
def _load_vision_model():
    """Load and cache the full torch model — map to CPU for inference."""
    try:
        model = torch.load(
            settings.VISION_MODEL_PATH,
            map_location=torch.device("cpu"),
        )
        model.eval()
        logger.info("vaidya.vision_model.loaded", path=settings.VISION_MODEL_PATH)
        return model
    except FileNotFoundError as exc:
        logger.warning("vaidya.vision_model.not_found", error=str(exc))
        return None
    except Exception as exc:
        logger.error("vaidya.vision_model.load_error", error=str(exc))
        return None


def _get_val_transform():
    """
    Exact val_transform from notebook Cell 5 — albumentations pipeline.
    Recreated here so we don't depend on albumentations at module import time.
    """
    try:
        import albumentations as A
        from albumentations.pytorch import ToTensorV2
        return A.Compose([
            A.Resize(224, 224),
            A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
            ToTensorV2(),
        ])
    except ImportError:
        # Fallback to torchvision if albumentations not installed
        from torchvision import transforms
        return transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])


def _infer_task_type(file_path: str) -> str:
    """
    Try to infer dataset_type from filename hint.
    Defaults to 'chest' as most medically critical.
    """
    name = Path(file_path).name.lower()
    if any(kw in name for kw in ["xray", "chest", "pneumonia", "lung"]):
        return "chest"
    if any(kw in name for kw in ["wound", "burn", "cut", "abrasion", "bruise", "laceration"]):
        return "wound"
    if any(kw in name for kw in ["skin", "acne", "rash", "eczema", "psoriasis"]):
        return "skin"
    return "chest"   # default — most critical for triage


def _run_inference(model, image_path: str, dataset_type: str) -> dict:
    """
    CPU inference — exact forward pass from evaluate_model() in notebook Cell 5:
      img = val_transform(image=np.array(img))["image"]
      img = img.unsqueeze(0).to(device)
      output = model(img, dataset_type)
      pred = output.argmax(1).item()
    """
    from PIL import Image

    transform = _get_val_transform()
    classes   = TASK_CLASSES.get(dataset_type, CHEST_CLASSES)

    img = Image.open(image_path).convert("RGB")

    # Handle both albumentations and torchvision transforms
    if hasattr(transform, "transforms") and hasattr(transform, "additional_targets"):
        # albumentations
        transformed = transform(image=np.array(img))
        tensor = transformed["image"]
    else:
        # torchvision
        tensor = transform(img)

    tensor = tensor.unsqueeze(0).to(torch.device("cpu"))

    with torch.no_grad():
        output = model(tensor, dataset_type)
        probs  = torch.softmax(output, dim=1)[0].numpy()

    top3_idx = np.argsort(probs)[::-1][:3]

    predictions = [
        {
            "label":            classes[i] if i < len(classes) else f"class_{i}",
            "confidence":       round(float(probs[i]), 4),
            "confidence_label": (
                "High"   if probs[i] > 0.6 else
                "Medium" if probs[i] > 0.3 else
                "Low"
            ),
        }
        for i in top3_idx
    ]

    return {
        "dataset_type":    dataset_type,
        "top_prediction":  predictions[0],
        "all_predictions": predictions,
        "signal_source":   "vision_model",
    }


async def _gemini_vision_fallback(file_path: str, dataset_type: str) -> dict | None:
    """
    Use Gemini's multimodal vision when the PyTorch model is unavailable or
    returns low-confidence predictions.  Returns same dict shape as _run_inference.
    """
    if not settings.GEMINI_API_KEY:
        return None

    try:
        image_bytes = Path(file_path).read_bytes()
        b64         = base64.b64encode(image_bytes).decode()
        mime_type   = _MIME_MAP.get(Path(file_path).suffix.lower(), "image/jpeg")

        classes      = TASK_CLASSES.get(dataset_type, CHEST_CLASSES)
        classes_str  = " | ".join(classes)

        prompt_text = (
            f"You are a medical image classifier. Analyse this {dataset_type} medical image.\n"
            f"Classify it into one of these categories: {classes_str}\n\n"
            f"Return ONLY valid JSON with exactly this structure — no prose:\n"
            f'{{"top_prediction": {{"label": "...", "confidence": 0.0}}, '
            f'"all_predictions": ['
            f'{{"label": "...", "confidence": 0.0}}, '
            f'{{"label": "...", "confidence": 0.0}}, '
            f'{{"label": "...", "confidence": 0.0}}]}}\n\n'
            f"Rules:\n"
            f"- all_predictions must list exactly 3 entries ordered highest to lowest confidence\n"
            f"- confidence values across all entries must sum to approximately 1.0\n"
            f"- labels must be chosen only from the category list above\n"
            f"- top_prediction must match all_predictions[0]"
        )

        messages = [{
            "role": "user",
            "parts": [
                {"inlineData": {"mimeType": mime_type, "data": b64}},
                {"text": prompt_text},
            ],
        }]

        from app.services.diagnosis.llm_fallback import _call_gemini
        raw = await _call_gemini(messages)
        if not raw:
            return None

        data = None
        for candidate in [raw, re.sub(r"```(?:json)?|```", "", raw).strip()]:
            try:
                data = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        if not data:
            logger.warning("vaidya.vision_model.gemini_parse_failed", preview=raw[:120])
            return None

        all_preds = data.get("all_predictions", [])[:3]
        # Pad to 3 if Gemini returned fewer
        while len(all_preds) < 3:
            all_preds.append({"label": classes[-1], "confidence": 0.0})

        for p in all_preds:
            conf = float(p.get("confidence", 0.0))
            p["confidence"]       = round(conf, 4)
            p["confidence_label"] = "High" if conf > 0.6 else "Medium" if conf > 0.3 else "Low"

        top = all_preds[0]
        logger.info(
            "vaidya.vision_model.gemini_fallback_ok",
            task=dataset_type,
            top=top.get("label"),
            confidence=top.get("confidence"),
        )
        return {
            "dataset_type":    dataset_type,
            "top_prediction":  top,
            "all_predictions": all_preds,
            "signal_source":   "gemini_vision",
        }

    except Exception as exc:
        logger.warning("vaidya.vision_model.gemini_fallback_error", error=str(exc))
        return None


async def run_vision_model(file_path: str, dataset_type: str | None = None) -> dict:
    """
    Run the hybrid multitask vision model on an uploaded image.

    Args:
        file_path:    path to uploaded image file
        dataset_type: "chest" | "skin" | "wound" (auto-inferred if None)

    Returns:
        dict with top_prediction, all_predictions, dataset_type
    """
    task  = dataset_type or _infer_task_type(file_path)
    model = _load_vision_model()

    if model is not None:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None, _run_inference, model, file_path, task
            )
            top_conf = result["top_prediction"]["confidence"]
            logger.info(
                "vaidya.vision_model.result",
                task=task,
                top=result["top_prediction"]["label"],
                confidence=top_conf,
            )
            if top_conf >= VISION_CONFIDENCE_THRESHOLD:
                return result

            # Low confidence — try Gemini to get a better read
            logger.info(
                "vaidya.vision_model.low_confidence_gemini",
                task=task,
                pytorch_conf=top_conf,
            )
            gemini = await _gemini_vision_fallback(file_path, task)
            return gemini if gemini else result

        except Exception as exc:
            logger.error("vaidya.vision_model.inference_error", error=str(exc))

    # Model not loaded or inference crashed — fall back to Gemini
    logger.info("vaidya.vision_model.pytorch_unavailable_gemini", task=task)
    gemini = await _gemini_vision_fallback(file_path, task)
    if gemini:
        return gemini

    return {
        "error": "Vision model not loaded and Gemini vision fallback unavailable",
        "note":  "Place hybrid_multitask_model.pth in models/vision/ or set GEMINI_API_KEY",
        "signal_source": "vision_model",
    }
