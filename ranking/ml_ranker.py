import os
import joblib

MODEL_PATH = "ranking/ranker_model.pkl"

def load_ranker():
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    return None
