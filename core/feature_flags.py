"""Release-state feature flags with a fail-closed public default.

The registry is intentionally small and dependency-free.  A feature can be
promoted by configuration, but callers must still satisfy the command/tier and
deterministic safety gates before performing any action.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class FeatureState(StrEnum):
    HIDDEN = "HIDDEN"
    OWNER_ONLY = "OWNER_ONLY"
    INTERNAL_TEST = "INTERNAL_TEST"
    PUBLIC_TEST = "PUBLIC_TEST"
    PAID_BETA = "PAID_BETA"
    PUBLIC_RELEASED = "PUBLIC_RELEASED"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class FeatureFlag:
    name: str
    state: FeatureState = FeatureState.HIDDEN
    description: str = ""


DEFAULT_FEATURES: dict[str, FeatureFlag] = {
    "rich_messages": FeatureFlag("rich_messages", FeatureState.HIDDEN, "Telegram rich-message canary"),
    "paper_trading": FeatureFlag("paper_trading", FeatureState.INTERNAL_TEST, "Virtual, isolated paper ledger"),
    "payments": FeatureFlag("payments", FeatureState.HIDDEN, "Paystack public payment surface"),
    "copy_trading": FeatureFlag("copy_trading", FeatureState.DISABLED, "Disabled until separately approved"),
    "auto_trading": FeatureFlag("auto_trading", FeatureState.DISABLED, "Disabled until separately approved"),
}


def _configured_state(name: str, default: FeatureState) -> FeatureState:
    raw = os.getenv(f"FEATURE_{name.upper()}_STATE", default.value).strip().upper()
    try:
        return FeatureState(raw)
    except ValueError:
        return FeatureState.HIDDEN


def get_feature(name: str) -> FeatureFlag:
    key = str(name or "").strip().lower()
    baseline = DEFAULT_FEATURES.get(key, FeatureFlag(key))
    return FeatureFlag(baseline.name, _configured_state(key, baseline.state), baseline.description)


def is_available(name: str, *, public: bool = False) -> bool:
    state = get_feature(name).state
    if state in {FeatureState.DISABLED, FeatureState.HIDDEN}:
        return False
    if public:
        return state in {FeatureState.PUBLIC_TEST, FeatureState.PAID_BETA, FeatureState.PUBLIC_RELEASED}
    return True


__all__ = ["DEFAULT_FEATURES", "FeatureFlag", "FeatureState", "get_feature", "is_available"]
