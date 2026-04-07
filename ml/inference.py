import os
import json
import base64
import tempfile
from pathlib import Path
import logging

from ml.schema_version import migrate_feature_payload, normalize_model_payload

try:
    import xgboost as xgb  # type: ignore
except Exception:  # pragma: no cover
    xgb = None

# Use absolute path relative to project root so it works both locally and on Railway
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_MODEL_PATH = str(PROJECT_ROOT / "ml" / "model.json")
MODEL_PATH = os.getenv("ML_MODEL_PATH", DEFAULT_MODEL_PATH)
logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}




class MLFilter:
    def __init__(self):
        # Opt-in ML filtering; default off to avoid blocking signals when a model
        # is missing, mis-specified, or features are not aligned.
        if not _env_bool("ML_ENABLED", True):
            self.active = False
            self.model = None
            self.feature_cols = None
            return

        # If the dependency isn't installed, fail open (do not block signals).
        if xgb is None:
            self.active = False
            self.model = None
            self.feature_cols = None
            return

        self.model = None
        self.feature_cols = None
        self.schema_version = None
        self.model_format_version = None
        try:
            with open(MODEL_PATH, 'r') as f:
                model_data = normalize_model_payload(json.load(f))
            
            # Extract metadata and model bytes
            model_b64 = model_data.get("model_bytes_b64")
            self.feature_cols = model_data.get("feature_cols", [])
            self.schema_version = model_data.get("schema_version")
            self.model_format_version = model_data.get("model_format_version")
            
            if not model_b64:
                self.active = False
                return
            
            # Decode base64 and load model directly from bytes (ubj format)
            model_bytes = base64.b64decode(model_b64)
            booster = xgb.Booster()
            booster.load_model(bytearray(model_bytes))  # Load directly from memory
            self.model = booster
            self.active = True
                
        except Exception as e:
            self.active = False
            self.model = None
            self.feature_cols = None
            logger.warning("[ml] inference model init failed; fail-open mode active: %s", e)

    def ml_filter(self, features, threshold=0.6):
        """
        Filter signals through ML model.
        
        Args:
            features: dict of feature_name -> value
            threshold: confidence threshold (default 0.6)
        
        Returns:
            (approved: bool, probability: float | None)
        """
        if not self.active or self.model is None:
            return True, None
        
        try:
            # Map input features to model's expected feature order
            normalized = migrate_feature_payload(features if isinstance(features, dict) else {}, list(self.feature_cols or []))
            feature_vector = []
            for col in (self.feature_cols or []):
                feature_vector.append(float(normalized.get(col, 0.0)))
            
            if not feature_vector:
                return True, None
            
            import numpy as np
            dmatrix = xgb.DMatrix(np.array([feature_vector]))
            prob = self.model.predict(dmatrix)[0]
            approved = prob >= float(threshold)
            return approved, float(prob)
        except Exception:
            return True, None
