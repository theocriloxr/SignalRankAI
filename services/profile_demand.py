"""Aggregate active user profile demand for efficient market scanning.

SignalRankAI generates a shared canonical candidate universe, then personalizes
ranking and distribution for each user.  This module tells the engine which
asset classes, instruments and timeframes active profiles currently require so
it does not scan a hard-coded or irrelevant universe.
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from sqlalchemy import text

from services.asset_registry import classify_asset, normalize_symbol
from services.trade_profiles import TRADE_PROFILES
from services.user_intelligence import (
    UserTradingPreferences,
    merge_preference_payloads,
    preferences_from_payload,
)


@dataclass(frozen=True, slots=True)
class ProfileDemandSnapshot:
    active_profiles: int = 0
    asset_class_counts: dict[str, int] = field(default_factory=dict)
    timeframe_counts: dict[str, int] = field(default_factory=dict)
    asset_class_timeframe_counts: dict[str, int] = field(default_factory=dict)
    trade_profile_counts: dict[str, int] = field(default_factory=dict)
    preferred_asset_counts: dict[str, int] = field(default_factory=dict)
    session_counts: dict[str, int] = field(default_factory=dict)
    risk_profile_counts: dict[str, int] = field(default_factory=dict)
    execution_mode_counts: dict[str, int] = field(default_factory=dict)
    generated_at_epoch: float = 0.0
    source: str = "defaults"

    @property
    def asset_classes(self) -> tuple[str, ...]:
        ordered = ("crypto", "fx", "commodity", "index", "stock")
        return tuple(value for value in ordered if self.asset_class_counts.get(value, 0) > 0)

    @property
    def preferred_assets(self) -> tuple[str, ...]:
        return tuple(
            key for key, _ in sorted(
                self.preferred_asset_counts.items(),
                key=lambda item: (-int(item[1]), item[0]),
            )
        )

    @property
    def preferred_timeframes(self) -> tuple[str, ...]:
        order = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "1w")
        return tuple(value for value in order if self.timeframe_counts.get(value, 0) > 0)

    def accepts_asset(self, asset: str) -> bool:
        if self.active_profiles <= 0 or not self.asset_classes:
            return True
        return classify_asset(asset) in set(self.asset_classes)

    def asset_priority(self, asset: str) -> float:
        symbol = normalize_symbol(asset)
        asset_class = classify_asset(symbol)
        preferred = float(self.preferred_asset_counts.get(symbol, 0))
        class_demand = float(self.asset_class_counts.get(asset_class, 0))
        return preferred * 1000.0 + class_demand * 10.0

    def timeframes_for(
        self,
        defaults: Iterable[str],
        *,
        asset_class: str | None = None,
        allowed: Iterable[str] | None = None,
    ) -> list[str]:
        default_list = [str(value).strip().lower() for value in defaults if str(value).strip()]
        allowed_set = {str(value).strip().lower() for value in (allowed or []) if str(value).strip()}
        class_name = str(asset_class or "").strip().lower()
        class_demanded = [
            key.split(":", 1)[1]
            for key, count in self.asset_class_timeframe_counts.items()
            if count > 0 and key.startswith(f"{class_name}:")
        ] if class_name else []
        demanded = class_demanded or list(self.preferred_timeframes)
        if self.active_profiles <= 0 or not demanded:
            out = default_list
        else:
            out = demanded + [value for value in default_list if value not in demanded]
        if allowed_set:
            out = [value for value in out if value in allowed_set]
        deduped: list[str] = []
        for value in out:
            if value and value not in deduped:
                deduped.append(value)
        return deduped or [value for value in default_list if not allowed_set or value in allowed_set]

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_profiles": int(self.active_profiles),
            "asset_classes": list(self.asset_classes),
            "preferred_assets": list(self.preferred_assets),
            "preferred_timeframes": list(self.preferred_timeframes),
            "asset_class_timeframe_counts": dict(self.asset_class_timeframe_counts),
            "trade_profile_counts": dict(self.trade_profile_counts),
            "risk_profile_counts": dict(self.risk_profile_counts),
            "execution_mode_counts": dict(self.execution_mode_counts),
            "source": self.source,
            "generated_at_epoch": float(self.generated_at_epoch),
        }


_CACHE: ProfileDemandSnapshot | None = None
_CACHE_AT = 0.0


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except Exception:
            return {}
    return {}


def _profile_timeframes(prefs: UserTradingPreferences) -> tuple[str, ...]:
    if prefs.preferred_timeframes:
        return tuple(prefs.preferred_timeframes)
    if prefs.trade_profile in TRADE_PROFILES:
        return tuple(TRADE_PROFILES[prefs.trade_profile].timeframes)
    return ()


def aggregate_profile_demand(
    records: Mapping[int, Mapping[str, Any]],
    *,
    active_user_ids: set[int] | None = None,
) -> ProfileDemandSnapshot:
    class_counts: Counter[str] = Counter()
    timeframe_counts: Counter[str] = Counter()
    class_timeframe_counts: Counter[str] = Counter()
    profile_counts: Counter[str] = Counter()
    asset_counts: Counter[str] = Counter()
    session_counts: Counter[str] = Counter()
    risk_counts: Counter[str] = Counter()
    execution_counts: Counter[str] = Counter()
    profile_total = 0

    for user_id, sources in records.items():
        if active_user_ids is not None and int(user_id) not in active_user_ids:
            continue
        merged = merge_preference_payloads(
            _payload(sources.get("modern")),
            _payload(sources.get("legacy")),
            sources.get("profile"),
        )
        prefs = preferences_from_payload(merged)
        profile_total += 1
        class_counts.update(prefs.asset_classes)
        profile_tfs = _profile_timeframes(prefs)
        timeframe_counts.update(profile_tfs)
        for asset_class in prefs.asset_classes:
            class_timeframe_counts.update(f"{asset_class}:{tf}" for tf in profile_tfs)
        profile_counts.update([prefs.trade_profile])
        asset_counts.update(normalize_symbol(value) for value in prefs.preferred_assets if value)
        session_counts.update(prefs.sessions)
        risk_counts.update([prefs.risk_profile])
        execution_counts.update([prefs.execution_mode])

    return ProfileDemandSnapshot(
        active_profiles=profile_total,
        asset_class_counts=dict(class_counts),
        timeframe_counts=dict(timeframe_counts),
        asset_class_timeframe_counts=dict(class_timeframe_counts),
        trade_profile_counts=dict(profile_counts),
        preferred_asset_counts=dict(asset_counts),
        session_counts=dict(session_counts),
        risk_profile_counts=dict(risk_counts),
        execution_mode_counts=dict(execution_counts),
        generated_at_epoch=time.time(),
        source="runtime_state" if profile_total else "defaults",
    )


async def load_profile_demand(session) -> ProfileDemandSnapshot:
    records: dict[int, dict[str, Any]] = {}
    result = await session.execute(
        text(
            """
            SELECT key, value
            FROM runtime_state
            WHERE key LIKE 'trading_preferences:%'
               OR key LIKE 'user_prefs:%'
               OR key LIKE 'trade_profile:%'
            """
        )
    )
    try:
        rows = result.all()
    except Exception:
        rows = []
    for row in rows:
        try:
            key, value = str(row[0]), row[1]
        except Exception:
            mapping = getattr(row, "_mapping", row)
            key, value = str(mapping.get("key") or ""), mapping.get("value")
        prefix, _, suffix = key.partition(":")
        try:
            user_id = int(suffix)
        except Exception:
            continue
        label = {
            "trading_preferences": "modern",
            "user_prefs": "legacy",
            "trade_profile": "profile",
        }.get(prefix)
        if label:
            records.setdefault(user_id, {})[label] = value

    active_user_ids: set[int] | None = None
    try:
        active_result = await session.execute(
            text(
                """
                SELECT telegram_user_id
                FROM users
                WHERE COALESCE(is_blocked, FALSE) IS FALSE
                  AND COALESCE(is_suspended, FALSE) IS FALSE
                """
            )
        )
        active_user_ids = {int(row[0]) for row in active_result.all()}
        # Active users without an explicit preference record still require the
        # canonical default profile. Otherwise one highly customized user could
        # accidentally narrow the shared discovered universe for everybody else.
        for active_user_id in active_user_ids:
            records.setdefault(int(active_user_id), {})
    except Exception:
        active_user_ids = None
    return aggregate_profile_demand(records, active_user_ids=active_user_ids)


async def get_profile_demand(session, *, force: bool = False) -> ProfileDemandSnapshot:
    global _CACHE, _CACHE_AT
    ttl = max(5.0, float(os.getenv("PROFILE_DEMAND_CACHE_SECONDS", "120") or 120))
    now = time.monotonic()
    if not force and _CACHE is not None and now - _CACHE_AT < ttl:
        return _CACHE
    snapshot = await load_profile_demand(session)
    _CACHE = snapshot
    _CACHE_AT = now
    return snapshot


def clear_profile_demand_cache() -> None:
    global _CACHE, _CACHE_AT
    _CACHE = None
    _CACHE_AT = 0.0


__all__ = [
    "ProfileDemandSnapshot",
    "aggregate_profile_demand",
    "clear_profile_demand_cache",
    "get_profile_demand",
    "load_profile_demand",
]
