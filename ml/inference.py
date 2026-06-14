import os
import json
import base64
import tempfile
from pathlib import Path
import logging

import numpy as np

try:
    import psycopg2
except Exception:  # pragma: no cover
    psycopg2 = None

from ml.schema_version import migrate_feature_payload, normalize_model_payload

try:
    import xgboost as xgb  # type: ignore
except Exception:  # pragma: no cover
    xgb = None

# Use absolute path relative to project root so it works both locally and on Railway
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_MODEL_PATH = str(PROJECT_ROOT / "ml" / "model.json")


def _resolve_model_path() -> str:
    """Resolve model path from supported env names.

    Priority:
    1) ML_MODEL_PATH (current)
    2) XGBOOST_MODEL_PATH (legacy/compat)
    3) default project model path
    """
    return (
        os.getenv("ML_MODEL_PATH")
        or os.getenv("XGBOOST_MODEL_PATH")
        or DEFAULT_MODEL_PATH
    )


MODEL_PATH = _resolve_model_path()
logger = logging.getLogger(__name__)


def calculate_dynamic_threshold(base_threshold: float, current_auc: float, target_auc: float = 0.85) -> float:
    """
    Auto-adjusts the required score threshold based on the ML model's current performance.
    
    If the model is performing poorly (low AUC), it becomes stricter.
    If the model is performing well (high AUC), it loosens the threshold.
    
    Args:
        base_threshold: The base ML probability threshold (e.g., 0.30)
        current_auc: The current model AUC from training (0.0-1.0)
        target_auc: The target AUC to normalize against (default: 0.85)
    
    Returns:
        Dynamic threshold adjusted based on model performance
    
    Example:
        >>> calculate_dynamic_threshold(0.30, 0.70, 0.85)
        0.36  # Stricter because model is underperforming (0.70 < 0.85)
        >>> calculate_dynamic_threshold(0.30, 0.90, 0.85)
        0.28  # Looser because model is overperforming (0.90 > 0.85)
    """
    # Model is essentially guessing - block almost all trades
    if current_auc <= 0.50:
        logger.warning("[ml] Model AUC %s <= 0.50 (guessing); blocking with threshold 0.99", current_auc)
        return 0.99
    
    # Model is very strong - allow more trades
    if current_auc >= 0.95:
        logger.info("[ml] Model AUC %s >= 0.95 (excellent); loosening threshold", current_auc)
        return max(0.10, base_threshold * 0.8)
    
    # Scale the threshold inversely to model performance
    # If current_auc < target_auc, ratio < 1.0, threshold increases (stricter)
    # If current_auc > target_auc, ratio > 1.0, threshold decreases (looser)
    adjustment_factor = target_auc / current_auc
    dynamic_threshold = base_threshold * adjustment_factor
    
    # Clamp to reasonable bounds
    min_threshold = max(0.10, base_threshold * 0.5)  # At least 50% of base
    max_threshold = min(0.70, base_threshold * 1.5)  # At most 150% of base
    
    final_threshold = max(min_threshold, min(max_threshold, dynamic_threshold))
    
    logger.info(
        "[ml] Dynamic threshold: base=%s current_auc=%s target=%s -> adjusted=%s",
        base_threshold,
        current_auc,
        target_auc,
        final_threshold
    )
    
    return final_threshold


def get_current_model_auc() -> float | None:
    """
    Fetch the current model AUC from Redis.
    
    Returns:
        float: The AUC value if available, None otherwise
    """
    try:
        import redis as redis_client
        import os
        
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return None
        
        r = redis_client.from_url(redis_url, decode_responses=True)
        auc_str = r.get("ml:model:auc")
        r.close()
        
        if auc_str is not None:
            return float(auc_str)
    except Exception as e:
        logger.debug("[ml] Failed to fetch AUC from Redis: %s", e)
    
    return None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _ml_enabled() -> bool:
    """ML switch with compatibility across env naming.

    Supports both ENABLE_ML and ML_ENABLED; ML_ENABLED wins if both are set.
    """
    if os.getenv("ML_ENABLED") is not None:
        return _env_bool("ML_ENABLED", True)
    if os.getenv("ENABLE_ML") is not None:
        return _env_bool("ENABLE_ML", False)
    return True


def _runtime_state_model_payload() -> dict | None:
    if psycopg2 is None:
        return None
    try:
        from config import resolve_database_url
        dsn = resolve_database_url(async_driver=False) or ""
    except Exception:
        dsn = ""
    if not dsn:
        return None
    key = (os.getenv("ML_MODEL_RUNTIME_STATE_KEY") or "ml:model:primary").strip() or "ml:model:primary"
    try:
        conn = psycopg2.connect(dsn, connect_timeout=3)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM runtime_state WHERE key=%s AND (expires_at IS NULL OR expires_at > NOW())",
                    (key,),
                )
                row = cur.fetchone()
                if not row or row[0] is None or not isinstance(row[0], dict):
                    return None
                payload = row[0].get("payload")
                return payload if isinstance(payload, dict) else None
        finally:
            conn.close()
    except Exception:
        return None




class MLFilter:
    def __init__(self):
        # Opt-in ML filtering; default off to avoid blocking signals when a model
        # is missing, mis-specified, or features are not aligned.
        if not _ml_enabled():
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
        self.calibration_x = None
        self.calibration_y = None
        self.calibration_kind = None
        try:
            model_data = None
            try:
                with open(_resolve_model_path(), 'r') as f:
                    model_data = normalize_model_payload(json.load(f))
            except Exception:
                model_data = None

            if not model_data:
                db_payload = _runtime_state_model_payload()
                if isinstance(db_payload, dict):
                    model_data = normalize_model_payload(db_payload)

            if not model_data:
                self.active = False
                return
            
            # Extract metadata and model bytes
            model_b64 = model_data.get("model_bytes_b64")
            self.feature_cols = model_data.get("feature_cols", [])
            self.schema_version = model_data.get("schema_version")
            self.model_format_version = model_data.get("model_format_version")
            self.calibration_kind = str(model_data.get("calibration_kind") or "")
            self.calibration_x = model_data.get("calibration_x") or []
            self.calibration_y = model_data.get("calibration_y") or []
            
            if not model_b64:
                self.active = False
                return
            
            # Decode base64 and load model directly from bytes (ubj format)
            model_bytes = base64.b64decode(model_b64)
            booster = xgb.Booster()
            booster.load_model(bytearray(model_bytes))  # Load directly from memory
            self.model = booster
            self.active = True

            if str(os.getenv("RAILWAY_SERVICE_NAME") or "").strip() and MODEL_PATH == DEFAULT_MODEL_PATH:
                logger.warning("[ml] using local model path on Railway; ensure runtime_state backup key is populated for durability")
                
        except Exception as e:
            self.active = False
            self.model = None
            self.feature_cols = None
            logger.warning("[ml] inference model init failed; fail-open mode active: %s", e)

    def _apply_calibration(self, probability: float) -> float:
        try:
            xs = [float(x) for x in (self.calibration_x or [])]
            ys = [float(y) for y in (self.calibration_y or [])]
            if len(xs) >= 2 and len(xs) == len(ys):
                return float(np.interp(float(probability), xs, ys, left=ys[0], right=ys[-1]))
        except Exception:
            pass
        return float(probability)

    def ml_filter(self, features, threshold: float | None = None):
        """
        Filter signals through ML model.
        
        Args:
            features: dict of feature_name -> value
            threshold: optional confidence threshold (None = advisory only)
        
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
            prob = self._apply_calibration(float(prob))
            if threshold is None:
                return True, float(prob)
            try:
                thresh_val = float(threshold)
            except Exception:
                thresh_val = None
            if thresh_val is None:
                return True, float(prob)
            approved = prob >= thresh_val
            return approved, float(prob)
        except Exception:
            return True, None
