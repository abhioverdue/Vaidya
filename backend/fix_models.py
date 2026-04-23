"""
Re-saves the XGBoost model in the current native format to eliminate
the serialization warning about older pickle format.
Run once from the backend directory with venv active:
    python fix_models.py
"""
import joblib
import os

NLP_MODEL_PATH   = "models/nlp/final_nlp_model.pkl"
ENCODER_PATH     = "models/nlp/label_encoder.pkl"
SYMPTOM_PATH     = "models/nlp/final_symptom_list.pkl"

print("Loading models...")
model        = joblib.load(NLP_MODEL_PATH)
encoder      = joblib.load(ENCODER_PATH)
symptom_list = joblib.load(SYMPTOM_PATH)

print(f"  XGBoost type : {type(model).__name__}")
print(f"  Classes      : {len(encoder.classes_)}")
print(f"  Symptoms     : {len(symptom_list)}")

# Re-save XGBoost booster in native UBJ format (eliminates pickle warning)
booster_path = "models/nlp/xgb_booster.ubj"
model.get_booster().save_model(booster_path)
print(f"  Saved booster → {booster_path}")

# Re-dump all three artifacts with current versions
joblib.dump(model,        NLP_MODEL_PATH, compress=3)
joblib.dump(encoder,      ENCODER_PATH,   compress=3)
joblib.dump(symptom_list, SYMPTOM_PATH,   compress=3)
print("  Re-saved all pkl files with current sklearn/xgboost versions")
print("Done — restart uvicorn, warnings should be gone.")
