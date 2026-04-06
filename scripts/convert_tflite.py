#!/usr/bin/env python3
"""
Vaidya — Convert XGBoost symptom classifier to TFLite for offline inference.

Usage:
    python scripts/convert_tflite.py \
        --model models/nlp/final_nlp_model.pkl \
        --encoder models/nlp/label_encoder.pkl \
        --symptoms models/nlp/final_symptom_list.pkl \
        --output frontend/src/assets/models/

Requirements:
    pip install skl2onnx onnx onnxruntime tf2onnx tensorflow joblib scikit-learn

Pipeline:
    1. Load XGBoost + LabelEncoder + symptom list from joblib files
    2. Export to ONNX via skl2onnx
    3. Validate ONNX model with test input
    4. Convert ONNX → TFLite via tf2onnx + TFLite converter
    5. Quantise to int8 (reduces model size ~4x, minimal accuracy loss)
    6. Save disease_labels.json alongside the .tflite file
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np


def convert(model_path: str, encoder_path: str, symptoms_path: str, output_dir: str):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # ── Load artifacts ─────────────────────────────────────────────────────────
    print("Loading XGBoost model...")
    model        = joblib.load(model_path)
    encoder      = joblib.load(encoder_path)
    symptom_list = joblib.load(symptoms_path)

    n_features = len(symptom_list)
    n_classes  = len(encoder.classes_)
    print(f"  Features: {n_features}, Classes: {n_classes}")

    # ── Save disease labels ────────────────────────────────────────────────────
    labels_path = output / "disease_labels.json"
    with open(labels_path, "w") as f:
        json.dump(encoder.classes_.tolist(), f, indent=2)
    print(f"Saved {labels_path}")

    # ── ONNX export ────────────────────────────────────────────────────────────
    print("Converting XGBoost → ONNX...")
    try:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
        import onnx

        onnx_model = convert_sklearn(
            model,
            "XGBoostSymptomClassifier",
            [("input", FloatTensorType([None, n_features]))],
            target_opset={"": 15, "ai.onnx.ml": 3},
        )
        onnx_path = output / "vaidya_symptom_classifier.onnx"
        with open(onnx_path, "wb") as f:
            f.write(onnx_model.SerializeToString())
        print(f"Saved {onnx_path}")

        # Validate ONNX
        import onnxruntime as ort
        sess    = ort.InferenceSession(str(onnx_path))
        test_in = np.zeros((1, n_features), dtype=np.float32)
        test_in[0, :5] = 1.0   # fake 5 symptoms
        out = sess.run(None, {"input": test_in})
        print(f"  ONNX validation OK — output shape: {out[1].shape}")

    except ImportError as e:
        print(f"ERROR: {e}\nInstall: pip install skl2onnx onnx onnxruntime")
        sys.exit(1)

    # ── TFLite conversion ──────────────────────────────────────────────────────
    print("Converting ONNX → TFLite...")
    try:
        import subprocess
        tf_saved_model_path = output / "tf_saved_model"
        subprocess.run([
            "python", "-m", "tf2onnx.convert",
            "--onnx",     str(onnx_path),
            "--output",   str(output / "vaidya_symptom_classifier.pb"),
            "--opset",    "15",
        ], check=True)

        import tensorflow as tf

        # Representative dataset for int8 quantisation
        def representative_dataset():
            for _ in range(200):
                vec = np.zeros((1, n_features), dtype=np.float32)
                # Random symptom pattern (2–8 symptoms active)
                n_active = np.random.randint(2, 9)
                indices  = np.random.choice(n_features, n_active, replace=False)
                vec[0, indices] = 1.0
                yield [vec]

        # Load as TF concrete function
        converter = tf.lite.TFLiteConverter.from_saved_model(str(tf_saved_model_path))
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset  = representative_dataset
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        converter.inference_input_type     = tf.float32
        converter.inference_output_type    = tf.float32

        tflite_model = converter.convert()
        tflite_path  = output / "vaidya_symptom_classifier.tflite"
        with open(tflite_path, "wb") as f:
            f.write(tflite_model)

        size_kb = len(tflite_model) / 1024
        print(f"Saved {tflite_path} ({size_kb:.1f} KB)")

    except (ImportError, subprocess.CalledProcessError) as e:
        print(f"WARNING: TFLite conversion failed: {e}")
        print("The ONNX model was saved — use tf2onnx manually if needed.")

    print("\nDone! Copy these files to frontend/src/assets/models/:")
    print(f"  {output / 'vaidya_symptom_classifier.tflite'}")
    print(f"  {output / 'disease_labels.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Vaidya XGBoost → TFLite")
    parser.add_argument("--model",    default="models/nlp/final_nlp_model.pkl")
    parser.add_argument("--encoder",  default="models/nlp/label_encoder.pkl")
    parser.add_argument("--symptoms", default="models/nlp/final_symptom_list.pkl")
    parser.add_argument("--output",   default="frontend/src/assets/models/")
    args = parser.parse_args()

    convert(args.model, args.encoder, args.symptoms, args.output)
