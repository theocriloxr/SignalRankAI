from __future__ import annotations

import ast
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

_PRICE_KEYS = ("price", "tp", "target", "value", "level")


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def parse_price_levels(raw: Any, *, max_levels: int = 10) -> list[float]:
    """Normalize legacy/JSON/string/dict TP payloads into positive float levels.

    This intentionally refuses to iterate an unparsed string. The previous TP
    notification path treated a JSON string such as ``"[73.7, 73.8, 73.9]"``
    as an iterable and emitted one TP per character.
    """
    if raw is None:
        return []

    if isinstance(raw, Mapping):
        for key in ("targets", "take_profit", "tp_levels", "take_profits"):
            if key in raw:
                return parse_price_levels(raw.get(key), max_levels=max_levels)
        for key in _PRICE_KEYS:
            if key in raw:
                value = _positive_float(raw.get(key))
                return [value] if value is not None else []
        # Deterministic support for {"tp1": ..., "tp2": ...} payloads.
        ordered: list[tuple[int, Any]] = []
        for key, value in raw.items():
            match = re.fullmatch(r"(?:tp|target)[_ -]?(\d+)", str(key).strip().lower())
            if match:
                ordered.append((int(match.group(1)), value))
        if ordered:
            return parse_price_levels([value for _, value in sorted(ordered)], max_levels=max_levels)
        return []

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        parsed: Any = None
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(text)
                break
            except Exception:
                continue
        if parsed is not None and parsed is not raw and parsed != text:
            return parse_price_levels(parsed, max_levels=max_levels)
        # Final compatibility path for comma/pipe/semicolon-separated numbers.
        tokens = [part.strip() for part in re.split(r"[,;|]", text.strip("[](){}"))]
        values = [_positive_float(token) for token in tokens if token]
        return [value for value in values if value is not None][: max(1, int(max_levels))]

    if isinstance(raw, (int, float)):
        value = _positive_float(raw)
        return [value] if value is not None else []

    if isinstance(raw, Iterable) and not isinstance(raw, (bytes, bytearray)):
        result: list[float] = []
        for item in raw:
            for value in parse_price_levels(item, max_levels=max_levels):
                if value not in result:
                    result.append(value)
                if len(result) >= max(1, int(max_levels)):
                    return result
        return result

    return []


def format_price_level(value: Any) -> str:
    number = _positive_float(value)
    if number is None:
        return "N/A"
    if number >= 1000:
        return f"{number:,.2f}"
    if number >= 1:
        return f"{number:.4f}".rstrip("0").rstrip(".")
    return f"{number:.8f}".rstrip("0").rstrip(".")
