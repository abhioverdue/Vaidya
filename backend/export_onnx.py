"""
Re-exports the XGBoost symptom classifier to ONNX.
The previous export had TreeEnsembleClassifier in domain='' instead of
domain='ai.onnx.ml', which ORT on Android cannot find.

Strategy: save booster to JSON → reload with feature_names=None (integer indices)
→ convert via onnxmltools (which requires f0/f1/... style names).

Run from backend/ with venv active:
    python export_onnx.py
"""
import json, os, tempfile, warnings
import numpy as np
import joblib
import xgboost as xgb
from onnxmltools import convert_xgboost
from onnxmltools.convert.common.data_types import FloatTensorType
import onnx
warnings.filterwarnings("ignore")

NLP_MODEL_PATH       = "models/nlp/final_nlp_model.pkl"
NLP_ENCODER_PATH     = "models/nlp/label_encoder.pkl"
NLP_SYMPTOM_LIST_PATH = "models/nlp/final_symptom_list.pkl"
OUT_ONNX = "../frontend/src/assets/models/vaidya_symptom_classifier.onnx"
OUT_SYMPTOMS = "../frontend/src/assets/models/symptom_list.json"
OUT_LABELS   = "../frontend/src/assets/models/disease_labels.json"

print("Loading pkl artifacts...")
model        = joblib.load(NLP_MODEL_PATH)
encoder      = joblib.load(NLP_ENCODER_PATH)
symptom_list = joblib.load(NLP_SYMPTOM_LIST_PATH)
print(f"  model type : {type(model).__name__}")
print(f"  symptoms   : {len(symptom_list)}")
print(f"  classes    : {len(encoder.classes_)}")

# Export ONNX with opset 12 — safe for onnxruntime-react-native 1.20
# FloatTensorType shape: [None, n_features]
n_features = len(symptom_list)
initial_type = [("input", FloatTensorType([None, n_features]))]

print(f"Converting to ONNX (opset 8, {n_features} features)...")

# onnxmltools requires feature names as f0/f1/... — strip the symptom names
# by round-tripping through JSON which clears feature_names on the booster.
tmp = tempfile.mktemp(suffix=".json")
model.get_booster().save_model(tmp)
booster = xgb.Booster()
booster.load_model(tmp)
booster.feature_names = None  # clears to f0, f1, ...
os.unlink(tmp)

onnx_model = convert_xgboost(
    booster,
    initial_types=initial_type,
    target_opset=8,
)

# Verify opset imports and node domains
print("ONNX opset imports:")
for op in onnx_model.opset_import:
    print(f"  domain={op.domain!r}, version={op.version}")
print("Node domains:")
for node in onnx_model.graph.node:
    print(f"  {node.op_type}: domain={node.domain!r}")

# Verify correctness: run test inference
import onnxruntime as rt
sess = rt.InferenceSession(onnx_model.SerializeToString())
test_input = np.zeros((1, n_features), dtype=np.float32)
test_input[0, 0] = 1.0
outputs = sess.run(None, {"input": test_input})
print(f"Test inference OK — output shapes: {[o.shape for o in outputs]}")

# Save ONNX
with open(OUT_ONNX, "wb") as f:
    f.write(onnx_model.SerializeToString())
print(f"Saved ONNX → {OUT_ONNX}")

# Save symptom list JSON (canonical order)
symptom_list_clean = [s.strip() for s in symptom_list]
with open(OUT_SYMPTOMS, "w") as f:
    json.dump(symptom_list_clean, f, indent=2)
print(f"Saved symptom list → {OUT_SYMPTOMS}")

# Save disease labels JSON
labels = list(encoder.classes_)
with open(OUT_LABELS, "w") as f:
    json.dump(labels, f, indent=2)
print(f"Saved disease labels → {OUT_LABELS}")

print("\nDone. Model outputs (by index):")
for i, out in enumerate(sess.get_outputs()):
    print(f"  [{i}] name={out.name!r}, shape={out.shape}, dtype={out.type}")
