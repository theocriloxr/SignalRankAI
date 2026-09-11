from __future__ import annotations

import json
import math
from collections import deque
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def json_safe(value: Any) -> Any:
    """Recursively normalize values so PostgreSQL JSON/JSONB never receives NaN/Infinity.

    This function is intentionally conservative at the persistence boundary:
    non-finite numeric values become ``None``; datetime/date values become ISO
    strings; containers are normalized recursively; unknown objects fall back
    to ``str``.  The returned object is validated with ``allow_nan=False`` by
    ``strict_json_safe`` when callers need an explicit serialization check.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        try:
            numeric = float(value)
        except Exception:
            return str(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return [json_safe(item) for item in value]
    try:
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            return isoformat()
    except Exception:
        pass
    return str(value)


def strict_json_safe(value: Any) -> Any:
    """Return a JSON-safe value and assert strict RFC-compatible serialization."""
    safe = json_safe(value)
    json.dumps(safe, allow_nan=False, separators=(",", ":"), default=str)
    return safe
