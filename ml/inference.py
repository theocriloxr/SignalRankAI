import xgboost as xgb
import os

MODEL_PATH = os.getenv("ML_MODEL_PATH", "ml/model.json")

class MLFilter:
    def __init__(self):
        self.model = xgb.XGBClassifier()
        try:
            self.model.load_model(MODEL_PATH)
            self.active = True
        except Exception:
            self.active = False

    def ml_filter(self, features, threshold=0.6):
        if not self.active:
            return True, None
        try:
            prob = self.model.predict_proba([list(features.values())])[0][1]
            return prob >= threshold, prob
        except Exception:
            return True, None
