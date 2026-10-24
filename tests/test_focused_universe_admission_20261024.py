"""One new-entry admission check guards every exposure-creating path.

The focused universe stays an isolated, opt-in boundary: disabled it changes
nothing; enabled outside staging it fails closed; enabled in staging it only
admits shortlist members, so alternate paths cannot reintroduce other assets.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from core.focused_universe import focused_admission, focused_shortlist

ROOT = Path(__file__).resolve().parents[1]
STAGING = {"FOCUSED_UNIVERSE_ENABLED": "1", "APP_ENV": "staging"}


def test_disabled_focus_admits_everything_and_changes_no_behaviour():
    assert focused_admission("DOGEIDR", {}) == (True, "focused_universe_disabled")
    assert focused_admission("BTCUSDT", {"FOCUSED_UNIVERSE_ENABLED": "0"}) == (True, "focused_universe_disabled")


def test_enabled_focus_admits_only_classified_shortlist_members():
    assert focused_admission("BTCUSDT", STAGING) == (True, "focused_shortlist_member")
    assert focused_admission("EURUSD", STAGING)[0] is True
    assert focused_admission("XAUUSD", STAGING)[0] is True
    # Unknown, analysis-only and non-shortlisted instruments are refused.
    for asset in ("DOGEIDR", "VIX", "DXY", "PEPEUSDT"):
        assert focused_admission(asset, STAGING) == (False, "focused_universe_excluded"), asset
    for blank in ("", "   ", None, 42):
        assert focused_admission(blank, STAGING) == (False, "focused_universe_missing_asset")


def test_shortlist_never_exceeds_fifteen_per_class_or_seventy_five_total():
    shortlist = focused_shortlist()
    assert 0 < len(shortlist) <= 75


def test_production_or_ambiguous_flags_fail_closed_instead_of_falling_back():
    blocked = focused_admission("BTCUSDT", {"FOCUSED_UNIVERSE_ENABLED": "1", "APP_ENV": "production"})
    assert blocked == (False, "focused_universe_requires_staging_certification")
    unlabeled = focused_admission("BTCUSDT", {"FOCUSED_UNIVERSE_ENABLED": "1"})
    assert unlabeled[0] is False
    masked = focused_admission(
        "BTCUSDT",
        {"FOCUSED_UNIVERSE_ENABLED": "1", "APP_ENV": "test", "RAILWAY_ENVIRONMENT_NAME": "production"},
    )
    assert masked[0] is False
    assert focused_admission("BTCUSDT", {"FOCUSED_UNIVERSE_ENABLED": "maybe", "APP_ENV": "staging"})[0] is False


def test_every_new_entry_chokepoint_calls_the_shared_admission_check():
    chokepoints = {
        "db/pg_features.py": "raise SignalDedupBlocked(admission_reason)",
        "db/repository.py": 'if not focused_admission(signal_data.get("asset"))[0]:',
        "services/mt5_signal_router.py": "admitted, admission_reason = focused_admission(",
        "services/bybit_signal_router.py": "admitted, admission_reason = focused_admission(",
    }
    for path, marker in chokepoints.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        assert "from core.focused_universe import focused_admission" in source, path
        assert marker in source, path


def test_signal_store_suppresses_excluded_assets_before_any_database_write(monkeypatch):
    from db import pg_features

    monkeypatch.setenv("FOCUSED_UNIVERSE_ENABLED", "1")
    monkeypatch.setenv("APP_ENV", "staging")
    for key in ("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT", "ENVIRONMENT"):
        monkeypatch.delenv(key, raising=False)

    class ExplodingSession:
        def __getattr__(self, name):  # any DB access would be a test failure
            raise AssertionError(f"database touched via {name}")

    signal = {"asset": "DOGEIDR", "timeframe": "1h", "direction": "long", "entry": 1.0}
    try:
        asyncio.run(pg_features.get_or_create_signal_impl(ExplodingSession(), signal, 24))
    except pg_features.SignalDedupBlocked as exc:
        assert exc.reason == "focused_universe_excluded"
    else:  # pragma: no cover - the excluded asset must never be stored
        raise AssertionError("excluded asset was not suppressed")


def test_broker_routers_refuse_new_entries_outside_the_focus(monkeypatch):
    from services import bybit_signal_router, mt5_signal_router

    monkeypatch.setenv("FOCUSED_UNIVERSE_ENABLED", "1")
    monkeypatch.setenv("APP_ENV", "staging")
    for key in ("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT", "ENVIRONMENT"):
        monkeypatch.delenv(key, raising=False)

    bybit = asyncio.run(bybit_signal_router.route_platform_signal_to_bybit(
        {"signal_id": "s1", "asset": "PEPEUSDT", "direction": "long", "entry": 1, "stop_loss": 0.9, "tp1": 1.2},
        1,
    ))
    assert bybit.success is False
    assert bybit.error == "focused_universe_excluded"

    router = mt5_signal_router.MT5SignalRouter()
    monkeypatch.setattr(router, "_validate_signal", lambda signal: (True, "ok"))
    result = asyncio.run(router.route_signal(
        {"signal_id": "s2", "asset": "DOGEIDR", "direction": "long", "entry": 1, "stop_loss": 0.9, "take_profit": 1.2},
        1,
        "manual_confirmed",
    ))
    assert result.success is False
    assert result.error == "focused_universe_excluded"
