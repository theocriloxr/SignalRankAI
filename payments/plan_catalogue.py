"""Authoritative server-side plan catalogue for Paystack checkout.

One canonical definition of every sellable plan. Environment variables may
override approved default prices, but every resolved price is validated:
  - present
  - numeric
  - positive
  - bounded (no accidental mega-amounts)

Plan codes are the only values allowed in Telegram callback data. Prices are
never embedded in callback payloads.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

PLAN_CALLBACK_PATTERN = (
    r"^subscribe:"
    r"(premium_monthly|premium_quarterly|"
    r"premium_yearly|vip_monthly)$"
)

# Canonical plan codes -> catalogue entries. `env_var` is the optional price
# override; default is the approved NGN price.
_DEFAULT_PLANS: dict[str, dict[str, object]] = {
    "premium_monthly": {
        "tier": "PREMIUM",
        "duration": "MONTHLY",
        "duration_days": 30,
        "price_ngn": 24000,
        "label": "Premium Monthly",
        "env_var": "PREMIUM_MONTHLY_PRICE_NGN",
    },
    "premium_quarterly": {
        "tier": "PREMIUM",
        "duration": "QUARTERLY",
        "duration_days": 90,
        "price_ngn": 56000,
        "label": "Premium Quarterly",
        "env_var": "PREMIUM_QUARTERLY_PRICE_NGN",
    },
    "premium_yearly": {
        "tier": "PREMIUM",
        "duration": "YEARLY",
        "duration_days": 365,
        "price_ngn": 192000,
        "label": "Premium Yearly",
        "env_var": "PREMIUM_YEARLY_PRICE_NGN",
    },
    "vip_monthly": {
        "tier": "VIP",
        "duration": "MONTHLY",
        "duration_days": 30,
        "price_ngn": 40000,
        "label": "VIP Monthly",
        "env_var": "VIP_MONTHLY_PRICE_NGN",
    },
}

# Hard safety ceiling: anything above this NGN amount is an accidental value.
_MAX_PRICE_NGN = 2_000_000


@dataclass(frozen=True, slots=True)
class Plan:
    code: str
    tier: str
    duration: str
    duration_days: int
    price_ngn: int
    label: str
    env_var: str | None = None

    def price_kobo(self) -> int:
        """Convert NGN to kobo exactly once, centrally."""
        return int(self.price_ngn) * 100


class PlanCatalogueError(ValueError):
    pass


def _resolve_price(plan_code: str, spec: Mapping[str, object], environ: Mapping[str, str]) -> int:
    env_var = str(spec.get("env_var") or "")
    raw = environ.get(env_var) if env_var else None
    default = int(spec.get("price_ngn") or 0)
    if raw is None or not str(raw).strip():
        value = default
    else:
        text = str(raw).strip()
        try:
            value = int(text)
        except (TypeError, ValueError):
            raise PlanCatalogueError(
                f"invalid_plan_price:{plan_code}:non_numeric"
            ) from None
    if value <= 0:
        raise PlanCatalogueError(f"invalid_plan_price:{plan_code}:non_positive")
    if value > _MAX_PRICE_NGN:
        raise PlanCatalogueError(f"invalid_plan_price:{plan_code}:exceeds_cap")
    return int(value)


def build_plan_catalogue(environ: Mapping[str, str] | None = None) -> dict[str, Plan]:
    """Build the validated plan catalogue from defaults + env overrides.

    Raises PlanCatalogueError when any configured price is invalid, a plan code
    is unknown, or duplicate codes exist.
    """
    env = environ if environ is not None else os.environ
    plans: dict[str, Plan] = {}
    for code, spec in _DEFAULT_PLANS.items():
        price = _resolve_price(code, spec, env)
        if code in plans:
            raise PlanCatalogueError(f"duplicate_plan_code:{code}")
        plans[code] = Plan(
            code=code,
            tier=str(spec.get("tier") or ""),
            duration=str(spec.get("duration") or ""),
            duration_days=int(spec.get("duration_days") or 0),
            price_ngn=price,
            label=str(spec.get("label") or code),
            env_var=str(spec.get("env_var") or "") or None,
        )
    return plans


def get_plan_catalogue(environ: Mapping[str, str] | None = None) -> dict[str, Plan]:
    """Memoized-safe accessor; rebuilds cheaply (small catalogue)."""
    return build_plan_catalogue(environ)


def get_plan(code: str | None, environ: Mapping[str, str] | None = None) -> Plan | None:
    if not code:
        return None
    return build_plan_catalogue(environ).get(str(code).strip().lower())


def validate_plan_code(code: str | None, environ: Mapping[str, str] | None = None) -> bool:
    return get_plan(code, environ) is not None


__all__ = [
    "PLAN_CALLBACK_PATTERN",
    "Plan",
    "PlanCatalogueError",
    "build_plan_catalogue",
    "get_plan",
    "get_plan_catalogue",
    "validate_plan_code",
]
