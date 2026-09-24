"""Bounded live-feature sampling for ML drift monitoring.

The inference path records numeric model features in memory and periodically
publishes a small aggregate sample to Redis. No user identifiers, prices,
credentials, or raw signal payloads are persisted here.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Mapping

from core.redis_state import state

_KEY = "signalrankai:ml:live_feature_stats"
_LOCK = threading.Lock()
_SAMPLES: dict[str, deque[float]] = defaultdict(
    lambda: deque(maxlen=max(32, int(os.getenv("ML_DRIFT_LIVE_SAMPLE_POINTS", "256") or 256)))
)
_COUNT = 0
_LAST_PUBLISH_MONO = 0.0


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def snapshot_feature_samples() -> dict[str, list[float]]:
    with _LOCK:
        return {key: list(values) for key, values in _SAMPLES.items() if values}


def _publish_snapshot(snapshot: dict[str, list[float]]) -> None:
    if not snapshot:
        return
    ttl = max(600, int(os.getenv("ML_DRIFT_LIVE_SAMPLE_TTL_SECONDS", "7200") or 7200))
    state.set_sync(_KEY, json.dumps(snapshot, separators=(",", ":")), ex=ttl)


def record_live_feature_vector(features: Mapping[str, Any] | None) -> None:
    """Record one inference feature vector without blocking signal evaluation."""
    global _COUNT, _LAST_PUBLISH_MONO
    if not features:
        return
    try:
        with _LOCK:
            for key, value in features.items():
                number = _finite(value)
                if number is not None:
                    _SAMPLES[str(key)].append(number)
            _COUNT += 1
            count = _COUNT
            last_publish = _LAST_PUBLISH_MONO
        now = time.monotonic()
        publish_every = max(10, int(os.getenv("ML_DRIFT_LIVE_PUBLISH_EVERY", "50") or 50))
        publish_seconds = max(15.0, float(os.getenv("ML_DRIFT_LIVE_PUBLISH_SECONDS", "60") or 60))
        if count % publish_every and now - last_publish < publish_seconds:
            return
        snapshot = snapshot_feature_samples()
        _publish_snapshot(snapshot)
        with _LOCK:
            _LAST_PUBLISH_MONO = now
    except Exception:
        # Drift telemetry can never break signal inference.
        return


def load_live_feature_samples() -> dict[str, list[float]]:
    raw = state.get_sync(_KEY)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, list[float]] = {}
    for key, values in parsed.items():
        if not isinstance(values, list):
            continue
        clean = [number for item in values if (number := _finite(item)) is not None]
        if clean:
            result[str(key)] = clean
    return result


async def load_durable_feature_baseline() -> dict[str, list[float]]:
    """Read the active champion's training baseline from the durable registry."""
    try:
        from sqlalchemy import text
        from db.session import get_session

        async with get_session(
            priority="analytics",
            label="ml_drift.baseline",
            timeout_seconds=max(5.0, float(os.getenv("ML_TRAINING_DB_TIMEOUT_SECONDS", "30") or 30)),
            drop_if_busy=False,
        ) as session:
            result = await asyncio.wait_for(
                session.execute(
                    text(
                        """
                        SELECT payload
                        FROM ml_model_artifacts
                        WHERE model_name='primary' AND is_active IS TRUE
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    )
                ),
                timeout=max(5.0, float(os.getenv("ML_TRAIN_QUERY_TIMEOUT_SECONDS", "20") or 20)),
            )
            row = result.mappings().first()
            await session.rollback()
        payload = dict((row or {}).get("payload") or {})
        baseline = dict((payload.get("training_meta") or {}).get("feature_baseline") or {})
        result: dict[str, list[float]] = {}
        for key, values in baseline.items():
            if not isinstance(values, list):
                continue
            clean = [number for item in values if (number := _finite(item)) is not None]
            if clean:
                result[str(key)] = clean
        return result
    except Exception:
        return {}


__all__ = [
    "load_durable_feature_baseline",
    "load_live_feature_samples",
    "record_live_feature_vector",
    "snapshot_feature_samples",
]
