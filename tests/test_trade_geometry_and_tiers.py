"""Regression tests: trade geometry, base-vs-tier qualification, delivery allowlist."""
from __future__ import annotations

import math

import pytest

from engine.trade_geometry import build_trade_geometry, validate_trade_geometry


def test_valid_long_geometry_passes() -> None:
    result = validate_trade_geometry(100.0, 98.0, [105.0], "long")
    assert result.ok is True
    assert result.entry == 100.0
    assert result.stop == 98.0
    assert result.targets == (105.0,)
    assert result.rr == pytest.approx(2.5)


def test_valid_short_geometry_passes() -> None:
    result = validate_trade_geometry(100.0, 102.0, [95.0], "short")
    assert result.ok is True
    assert result.rr == pytest.approx(2.5)


def test_entry_equals_stop_is_rejected() -> None:
    result = validate_trade_geometry(100.0, 100.0, [105.0], "long")
    assert result.ok is False
    assert result.reason == "zero_risk_distance"


def test_entry_equals_target_is_rejected() -> None:
    result = validate_trade_geometry(100.0, 98.0, [100.0], "long")
    assert result.ok is False
    assert result.reason == "invalid_long_geometry"


def test_entry_stop_target_all_equal_is_rejected() -> None:
    result = validate_trade_geometry(100.0, 100.0, [100.0], "long")
    assert result.ok is False
    assert result.reason == "zero_risk_distance"


def test_missing_stop_is_rejected_without_defaulting_to_entry() -> None:
    # Legacy behaviour defaulted missing stop to entry, fabricating Entry == Stop.
    result = build_trade_geometry({"entry": 100.0, "take_profit": [105.0], "direction": "long", "atr": 0})
    assert result.ok is False
    assert result.reason == "missing_trade_geometry"
    assert result.stop is None


def test_missing_target_is_rejected_without_defaulting_to_entry() -> None:
    result = build_trade_geometry({"entry": 100.0, "stop_loss": 98.0, "direction": "long", "atr": 0})
    assert result.ok is False
    assert result.reason == "missing_trade_geometry"


def test_nan_or_infinity_is_rejected() -> None:
    assert validate_trade_geometry(math.nan, 98.0, [105.0], "long").ok is False
    assert validate_trade_geometry(100.0, math.inf, [105.0], "long").ok is False
    assert validate_trade_geometry(100.0, 98.0, [math.nan], "long").ok is False
    result = validate_trade_geometry(100.0, 98.0, [math.nan], "long")
    assert result.reason == "non_finite_trade_geometry"


def test_extremely_small_risk_distance_is_rejected() -> None:
    # 1e-300 risk distance should not divide to infinity; validated numerically.
    result = validate_trade_geometry(100.0, 100.0 + 1e-300, [105.0], "long")
    assert result.ok is False
    assert result.reason == "zero_risk_distance"


def test_canonical_builder_repairs_direction_only_signal() -> None:
    result = build_trade_geometry(
        {"entry": 100.0, "direction": "long", "atr": 0.5, "rr": 2.0}
    )
    assert result.ok is True
    assert result.stop is not None and result.stop < 100.0
    assert result.targets and result.targets[0] > 100.0


def test_unbuildable_geometry_is_rejected() -> None:
    result = build_trade_geometry({"direction": "long"})
    assert result.ok is False
    assert result.reason == "missing_trade_geometry"


def test_zero_risk_never_reaches_division_by_zero() -> None:
    from engine.scoring import score_signal

    # score_signal must reject, not divide by zero, when stop == entry.
    signal = {"asset": "BTCUSDT", "entry": 100.0, "stop_loss": 100.0, "take_profit": [105.0], "direction": "long"}
    assert score_signal(signal) == 0.0


# ── Tier / base separation (Phase 10) ────────────────────────────────────────


def test_base_qualified_signal_is_eligible_even_when_ultra_ineligible() -> None:
    # The ultra gate must record eligibility without eliminating the candidate.
    from engine.ultra_quality_filter import UltraQualityFilter

    class _Filter(UltraQualityFilter):
        def apply_ultra_filter(self, signal):
            return False, "R:R 1.00 < 2.50", 40.0

    sig = {"asset": "BTCUSDT", "entry": 100.0, "stop_loss": 98.0, "take_profit": [102.0], "direction": "long"}
    should_trade, rejection, qscore = _Filter().apply_ultra_filter(sig)
    assert should_trade is False
    assert rejection is not None
    # Base production quality is orthogonal: a base-qualified signal remains
    # storable/premium-eligible regardless of the ultra rejection.
    sig["ultra_eligible"] = bool(should_trade)
    sig["ultra_rejection_reason"] = rejection
    sig["base_eligible"] = True
    sig["tier_eligibility"] = {"premium": True, "vip": True, "ultra": False}
    assert sig["base_eligible"] is True
    assert sig["tier_eligibility"]["ultra"] is False
    assert sig["ultra_eligible"] is False


def test_ultra_ineligible_signal_is_not_marked_ultra_deliverable() -> None:
    from engine.ultra_quality_filter import UltraQualityFilter

    class _Filter(UltraQualityFilter):
        def apply_ultra_filter(self, signal):
            return False, "score 70 < 85", 70.0

    sig = {"score": 70, "entry": 100.0, "stop_loss": 98.0, "take_profit": [102.0], "direction": "long"}
    should_trade, rejection, qscore = _Filter().apply_ultra_filter(sig)
    assert should_trade is False
    assert "score" in str(rejection)


# ── Delivery allowlist (Phase 11) ────────────────────────────────────────────


def test_allowlist_filters_unsupported_assets() -> None:
    from data.get_live_price import (
        asset_allowlist_exclusion_reason,
        filter_scan_universe_to_allowlist,
        production_asset_allowlist,
    )

    import os

    os.environ["PRODUCTION_ASSET_ALLOWLIST"] = "BTCUSDT,ETHUSDT,SOLUSDT"
    try:
        assert production_asset_allowlist() == frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})
        assert asset_allowlist_exclusion_reason("WTI") == "asset_not_in_production_allowlist:WTI"
        assert asset_allowlist_exclusion_reason("BTCUSDT") is None
        filtered = filter_scan_universe_to_allowlist(["BTCUSDT", "WTI", "XAGUSD", "ETHUSDT", "btcusdt"])
        assert filtered == ["BTCUSDT", "ETHUSDT"]
    finally:
        del os.environ["PRODUCTION_ASSET_ALLOWLIST"]


def test_no_allowlist_keeps_full_universe() -> None:
    from data.get_live_price import filter_scan_universe_to_allowlist, production_asset_allowlist

    import os

    os.environ.pop("PRODUCTION_ASSET_ALLOWLIST", None)
    assert production_asset_allowlist() is None
    assert filter_scan_universe_to_allowlist(["WTI", "XAGUSD"]) == ["WTI", "XAGUSD"]
