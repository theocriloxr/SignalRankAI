"""One source for plan prices in naira (owner pricing, 11 Nov 2026).

Each price can be overridden by its environment variable. A value that is
plainly kobo (over 1,000,000 for a plan; production had PREMIUM_PRICE_NGN set
to 2,400,000 for a 24,000 plan, so Telegram showed Premium at ₦2,400,000) is
read as kobo and divided by 100, with a warning.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULTS_NGN = {
    "PREMIUM_WEEKLY": 9000,
    "PREMIUM_MONTHLY": 29000,
    "PREMIUM_QUARTERLY": 78000,
    "PREMIUM_YEARLY": 278000,
    "VIP_WEEKLY": 19000,
    "VIP_MONTHLY": 59000,
}
_ENV_NAMES = {
    "PREMIUM_WEEKLY": ("PREMIUM_WEEKLY_PRICE_NGN",),
    "PREMIUM_MONTHLY": ("PREMIUM_MONTHLY_PRICE_NGN",),
    "PREMIUM_QUARTERLY": ("PREMIUM_QUARTERLY_PRICE_NGN",),
    "PREMIUM_YEARLY": ("PREMIUM_YEARLY_PRICE_NGN",),
    "VIP_WEEKLY": ("VIP_WEEKLY_PRICE_NGN",),
    "VIP_MONTHLY": ("VIP_MONTHLY_PRICE_NGN",),
}
# The older names held the previous schedule (production: PREMIUM_PRICE_NGN=2,400,000
# and VIP_PRICE_NGN=40,000). The owner raised prices on 11 Nov 2026, so they apply only
# with PRICE_SCHEDULE=legacy; the per-period names above always override.
_LEGACY_ENV_NAMES = {"PREMIUM_MONTHLY": ("PREMIUM_PRICE_NGN",), "VIP_MONTHLY": ("VIP_PRICE_NGN",)}
_KOBO_SUSPECT_NGN = 1_000_000
_warned: set[str] = set()


def price_ngn(plan: str) -> int:
    plan = str(plan or "").upper()
    default = DEFAULTS_NGN.get(plan, 0)
    names = _ENV_NAMES.get(plan, ())
    if str(os.getenv("PRICE_SCHEDULE") or "").strip().lower() == "legacy":
        names = names + _LEGACY_ENV_NAMES.get(plan, ())
    for name in names:
        raw = str(os.getenv(name) or "").strip()
        if not raw:
            continue
        try:
            value = int(float(raw))
        except ValueError:
            continue
        if (value > _KOBO_SUSPECT_NGN and plan != "PREMIUM_YEARLY") or value > 10 * _KOBO_SUSPECT_NGN:
            if name not in _warned:
                _warned.add(name)
                logger.warning("[plan_prices] %s=%s looks like kobo; using %s naira", name, value, value // 100)
            value //= 100
        if value > 0:
            return value
    return default
