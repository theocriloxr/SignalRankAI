import os

try:
    import xgboost as xgb  # type: ignore
except Exception:  # pragma: no cover
    xgb = None

MODEL_PATH = os.getenv("ML_MODEL_PATH", "ml/model.json")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

class MLFilter:
    def __init__(self):
        # Opt-in ML filtering; default off to avoid blocking signals when a model
        # is missing, mis-specified, or features are not aligned.
        if not _env_bool("ML_ENABLED", False):
            self.active = False
            self.model = None
            return

        # If the dependency isn't installed, fail open (do not block signals).
        if xgb is None:
            self.active = False
            self.model = None
            return

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
