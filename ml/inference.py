import os
import json
import base64
import tempfile
from pathlib import Path
import logging

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
    dsn = (
        os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    if not dsn:
        return None
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    elif dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
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
