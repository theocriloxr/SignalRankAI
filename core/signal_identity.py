"""Canonical public identity helpers for SignalRankAI signals.

The database UUID remains authoritative.  ``display_id`` is the immutable,
user-visible reference persisted with the signal and used consistently by
formatters, commands, callbacks, and diagnostics.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


DISPLAY_SIGNAL_ID_LENGTH = 12
SIGNAL_ID_LABEL = "📌 Signal ID:"
_SAFE_REF = re.compile(r"^[A-Za-z0-9-]{8,36}$")


def make_display_signal_id(signal_id: object) -> str:
    """Derive the stable default display reference from a full UUID."""
    value = str(signal_id or "").strip().lower()
    if not value:
        return ""
    return value[:DISPLAY_SIGNAL_ID_LENGTH]


def public_signal_id(signal: Mapping[str, Any] | object) -> str:
    """Return a persisted display ID when available, otherwise a safe legacy derivation."""
    if isinstance(signal, Mapping):
        display_id = signal.get("display_id") or signal.get("signal_ref")
        full_id = signal.get("signal_id") or signal.get("id")
    else:
        display_id = getattr(signal, "display_id", None)
        full_id = getattr(signal, "signal_id", None) or signal
    value = str(display_id or "").strip().lower()
    return value or make_display_signal_id(full_id)


def signal_id_line(signal: Mapping[str, Any] | object, *, html_code: bool = False) -> str:
    ref = public_signal_id(signal)
    if html_code:
        return f"{SIGNAL_ID_LABEL} <code>{ref}</code>"
    return f"{SIGNAL_ID_LABEL} {ref}"


def normalize_signal_reference(value: object) -> str:
    """Normalize an untrusted command/callback reference without broad wildcard syntax."""
    ref = str(value or "").strip().lower()
    if not ref or not _SAFE_REF.fullmatch(ref):
        return ""
    return ref


__all__ = [
    "DISPLAY_SIGNAL_ID_LENGTH",
    "SIGNAL_ID_LABEL",
    "make_display_signal_id",
    "normalize_signal_reference",
    "public_signal_id",
    "signal_id_line",
]
