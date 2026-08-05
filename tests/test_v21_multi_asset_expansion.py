"""Regression tests for the multi-asset expansion pass.

Covers:
- Phase 3: canonical post-geometry R:R (LONG/SHORT, rejection reasons, formatter
  consistency, no bare generic R:R in explanations).
- Phase 4: paper requested-vs-actual risk separation and reporting.
- Phase 19: active-thesis dedup classification (never store_failed).
- Phase 9: Hyperliquid market-data connector (fail-closed, normalization).
- Phase 5: asset-class certification framework.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.geometry_calculation import (
    calculate_trade_geometry,
    enrich_signal_geometry,
    geometry_from_signal,
    parse_targets,
)
from core.paper_sizing import (
    PaperPositionSize,
    calculate_paper_position_size,
    paper_risk_report_text,
)
from core.asset_certification import (
    ReadinessState,
    evaluate_certification,
    readiness_label,
)


# ---------------------------------------------------------------------------
# Phase 3 — canonical geometry / R:R
# ---------------------------------------------------------------------------

def test_long_geometry_rr_values() -> None:
    """LONG: stop < entry < target, direction-aware R:R per target."""
    result = calculate_trade_geometry(10, 9.5, [10.6, 11.0, 11.4], "long")
    assert result.ok is True
    assert result.reason == ""
    assert result.risk_distance == Decimal("0.5")
    assert result.rr_tp1 == Decimal("1.2")
    assert result.rr_tp2 == Decimal("2.0")
    assert result.rr_tp3 == Decimal("2.8")
    assert result.rr_selected_target == Decimal("2.8")
    assert result.reward_distance_tp1 == Decimal("0.6")
    assert result.reward_distance_tp3 == Decimal("1.4")


def test_short_geometry_rr_values() -> None:
    """SHORT: target < entry < stop."""
    result = calculate_trade_geometry(10, 10.5, [9.4, 8.6], "short")
    assert result.ok is True
    assert result.risk_distance == Decimal("0.5")
    assert result.rr_tp1 == Decimal("1.2")
    assert result.rr_tp2 == Decimal("2.8")  # reward 1.4 / risk 0.5


def test_geometry_rejections() -> None:
    assert calculate_trade_geometry(None, 9.5, [10.6], "long").reason == "missing_trade_geometry"
    assert calculate_trade_geometry(10, None, [10.6], "long").reason == "missing_trade_geometry"
    assert calculate_trade_geometry(10, 9.5, [], "long").reason == "missing_trade_geometry"
    assert calculate_trade_geometry(10, 9.5, [10.6], "sideways").reason == "unsupported_direction"
    # Entry == stop -> zero risk
    assert calculate_trade_geometry(10, 10, [10.6], "long").reason == "zero_risk_distance"
    # Entry == stop == target
    assert calculate_trade_geometry(10, 10, [10], "long").reason == "zero_risk_distance"
    # Entry == target violates strict long inequality
    assert calculate_trade_geometry(10, 9.5, [10], "long").reason == "invalid_long_geometry"
    # Short with target above entry violates short geometry
    assert calculate_trade_geometry(10, 10.5, [10.6], "short").reason == "invalid_short_geometry"
    # Non-positive prices
    assert calculate_trade_geometry(0, 9.5, [10.6], "long").reason == "non_finite_trade_geometry"
    assert calculate_trade_geometry(10, -1, [10.6], "long").reason == "non_finite_trade_geometry"


def test_parse_targets_normalization() -> None:
    assert parse_targets([{"price": 10.6}, 11.0, "11.4"]) == (
        Decimal("10.6"), Decimal("11.0"), Decimal("11.4"),
    )
    assert parse_targets("10.6") == (Decimal("10.6"),)
    assert parse_targets({"tp1": 10.6, "tp3": 11.4}) == (Decimal("10.6"), Decimal("11.4"))
    assert parse_targets(None) == ()


def test_enrich_signal_geometry_persists_canonical_fields() -> None:
    signal = {
        "asset": "DOTUSDT", "direction": "long", "timeframe": "1h",
        "entry": 10, "stop_loss": 9.5, "take_profit": [10.6, 11.0, 11.4],
    }
    enriched = enrich_signal_geometry(signal)
    assert enriched["geometry_reason"] == ""
    assert enriched["risk_distance"] == Decimal("0.5")
    assert enriched["rr_tp1"] == Decimal("1.2")
    assert enriched["rr_tp3"] == Decimal("2.8")
    assert enriched["rr_ratio"] == Decimal("2.8")
    assert enriched["rr_selected_target"] == Decimal("2.8")


def test_rounded_display_consistency() -> None:
    """Displayed 1:1.2 / 1:2.8 values derive from the same canonical geometry."""
    result = calculate_trade_geometry(10, 9.5, [10.6, 11.4], "long")
    line = result.rr_display_line()
    assert "TP1 1:1.20" in line
    assert "TP2 1:2.80" in line


# ---------------------------------------------------------------------------
# Phase 3 — formatter consistency (no bare generic R:R)
# ---------------------------------------------------------------------------

def test_vip_formatter_never_shows_bare_generic_rr() -> None:
    from signalrank_telegram.tier_signal_formatter import format_vip_signal

    signal = {
        "asset": "DOTUSDT", "direction": "long", "timeframe": "1h",
        "entry": 10, "stop_loss": 9.5, "take_profit": [10.6, 11.0, 11.4],
        # A stale/strategy-derived generic R:R must not survive into the message.
        "technical_reason": "EMA trend alignment R:R=3.74",
        "score": 91, "rr_estimate": 3.74,
    }
    text = format_vip_signal(signal)
    assert "R:R=3.74" not in text
    assert "3.74" not in text
    # Canonical TP-identified values appear in the Why line and the R/R line.
    assert "TP1 R:R 1:1.20" in text
    assert "TP3 R:R 1:2.80" in text
    assert "R/R: TP1 1:1.2" in text


def test_vip_formatter_matches_persisted_canonical_values() -> None:
    """Displayed R:R equals the canonical values persisted with the signal
    when the ladder is the signal's own (no fallback extrapolation)."""
    from signalrank_telegram.tier_signal_formatter import format_vip_signal

    signal = {
        "asset": "BTCUSDT", "direction": "long", "timeframe": "4h",
        "entry": 60000, "stop_loss": 59000, "take_profit": [61200, 62400, 63600],
        "rr_tp1": 1.2, "rr_tp3": 3.6,  # persisted canonical values
        "score": 90,
    }
    enriched = enrich_signal_geometry(signal)
    assert enriched["rr_tp1"] == Decimal("1.2")
    assert enriched["rr_tp3"] == Decimal("3.6")
    text = format_vip_signal(signal)
    assert "R/R: TP1 1:1.2" in text
    assert "TP3 1:3.6" in text
    assert "TP3 R:R 1:3.60" in text


def test_message_values_match_paper_target_selection() -> None:
    """The paper service selects one of the displayed TP levels by target_mode."""
    from core.paper_trading_service import parse_targets as paper_parse_targets

    targets = paper_parse_targets([10.6, 11.0, 11.4])
    target_idx = {"TP1": 0, "TP2": 1, "TP3": 2}["TP2"]
    selected = targets[min(target_idx, len(targets) - 1)]
    assert selected == 11.0  # a displayed level with a canonical R:R of 2.0
    geometry = calculate_trade_geometry(10, 9.5, targets, "long")
    assert geometry.rr_for_index(target_idx) == Decimal("2.0")


# ---------------------------------------------------------------------------
# Phase 4 — paper requested-vs-actual risk
# ---------------------------------------------------------------------------

def _size(**kwargs) -> PaperPositionSize:
    defaults = dict(
        cash=10_000, risk_pct=1.0, risk_per_unit=0.5, fill=100.0,
        max_notional_pct=100.0, fee_bps=5.0,
    )
    defaults.update(kwargs)
    return calculate_paper_position_size(**defaults)


def test_cash_capped_position_reports_actual_below_requested() -> None:
    sizing = _size(cash=10_000, risk_per_unit=0.5, fill=100.0, max_notional_pct=100.0)
    assert float(sizing.requested_risk_pct) == 1.0
    assert float(sizing.risk_amount) == 100.0  # requested $100
    assert sizing.size_cap_applied is True
    assert sizing.size_cap_reason == "available_virtual_cash"
    # Actual stop risk = risk_per_unit x executed quantity (~$50 on ~$10k).
    assert 0 < float(sizing.actual_risk_amount) < float(sizing.risk_amount)
    assert 0 < float(sizing.actual_risk_pct) < 1.0
    assert float(sizing.uncapped_quantity) > float(sizing.quantity)


def test_no_cap_actual_equals_requested() -> None:
    sizing = _size(cash=10_000, risk_per_unit=5.0, fill=100.0, max_notional_pct=100.0)
    assert sizing.size_cap_applied is False
    assert sizing.size_cap_reason == "none"
    assert float(sizing.actual_risk_amount) == pytest.approx(100.0, abs=0.01)
    assert float(sizing.actual_risk_pct) == pytest.approx(1.0, abs=0.01)


def test_configured_notional_cap_reason() -> None:
    sizing = _size(cash=10_000, risk_per_unit=0.5, fill=100.0, max_notional_pct=20.0)
    assert sizing.size_cap_applied is True
    assert sizing.size_cap_reason == "configured_notional_cap"
    assert float(sizing.executed_notional) == pytest.approx(2000.0, abs=0.01)


def test_fee_aware_cash_after_and_required() -> None:
    sizing = _size(cash=10_000, risk_per_unit=5.0, fill=100.0, fee_bps=5.0)
    assert float(sizing.entry_fee) > 0
    assert float(sizing.total_required) == pytest.approx(
        float(sizing.notional) + float(sizing.entry_fee), abs=0.01
    )
    assert float(sizing.available_cash_after) == pytest.approx(
        float(sizing.available_cash_before) - float(sizing.total_required), abs=0.01
    )
    # $2,000 notional on $10,000 equity -> 0.2x leverage for cash spot.
    assert float(sizing.leverage) == pytest.approx(0.2, abs=0.001)
    assert float(sizing.margin_required) == float(sizing.notional)


def test_insufficient_virtual_cash_raises() -> None:
    with pytest.raises(ValueError, match="insufficient_virtual_cash"):
        calculate_paper_position_size(
            cash=1, risk_pct=1.0, risk_per_unit=1.0, fill=1e15,
            max_notional_pct=100.0, fee_bps=0.0,
        )


def test_zero_risk_distance_raises() -> None:
    with pytest.raises(ValueError, match="invalid_risk_distance"):
        calculate_paper_position_size(
            cash=10_000, risk_pct=1.0, risk_per_unit=0.0, fill=100.0,
            max_notional_pct=20.0, fee_bps=5.0,
        )


def test_short_position_uses_absolute_risk_distance() -> None:
    # Short: entry 10, stop 10.5 -> same risk distance math via the paper service.
    risk_per_unit = abs(10.0 - 10.5)
    sizing = _size(cash=10_000, risk_per_unit=risk_per_unit, fill=10.0, max_notional_pct=20.0)
    assert float(sizing.risk_per_unit) == 0.5


def test_paper_risk_report_text_three_lines() -> None:
    sizing = _size(cash=10_000, risk_per_unit=0.5, fill=100.0, max_notional_pct=100.0)
    report = paper_risk_report_text(sizing)
    assert "Requested risk budget: 1.00%" in report
    assert "Actual stop risk: $" in report
    assert "Position-size cap: available virtual cash" in report

    uncapped = _size(cash=10_000, risk_per_unit=5.0, fill=100.0, max_notional_pct=100.0)
    report2 = paper_risk_report_text(uncapped)
    assert "Position-size cap: none" in report2


# ---------------------------------------------------------------------------
# Phase 19 — active-thesis dedup classification
# ---------------------------------------------------------------------------

def test_classify_signal_store_error_dedup_block() -> None:
    from engine.core import classify_signal_store_error
    from db.pg_features import SignalDedupBlocked

    assert classify_signal_store_error(SignalDedupBlocked("active_thesis", "sig-1")) == "signal_reused"


def test_classify_signal_store_error_unique_violation() -> None:
    from engine.core import classify_signal_store_error
    from sqlalchemy.exc import IntegrityError

    exc = IntegrityError("stmt", {}, Exception("duplicate key value violates unique constraint"))
    assert classify_signal_store_error(exc) == "signal_duplicate_blocked"


def test_classify_signal_store_error_unexpected() -> None:
    from engine.core import classify_signal_store_error

    assert classify_signal_store_error(RuntimeError("db down")) == "signal_storage_unexpected_failure"


# ---------------------------------------------------------------------------
# Phase 9 — Hyperliquid connector (fail-closed)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_hyperliquid_caches(monkeypatch):
    from data.connectors import hyperliquid_adapter as hl

    hl._META_CTX_CACHE.clear()
    hl._UNSUPPORTED_CACHE.clear()
    yield
    hl._META_CTX_CACHE.clear()
    hl._UNSUPPORTED_CACHE.clear()


class _FakeResp:
    def __init__(self, status_code, data):
        self._code = status_code
        self._data = data

    @property
    def status_code(self):
        return self._code

    def json(self):
        return self._data


class _FakeClient:
    """Records payloads and dispatches canned responses by payload type."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url, json=None, timeout=None):
        self.calls.append((url, json or {}))
        return _FakeResp(200, self.handler((json or {}).get("type"), json or {}))


def _install_fake_hyperliquid(monkeypatch, handler):
    import utils.httpx_client as hc
    from data.connectors import hyperliquid_adapter as hl

    client = _FakeClient(handler)

    async def _no_retry(fn, retries=3, backoff=1.0):
        return await fn()

    monkeypatch.setattr(hc, "get_client", lambda provider: client)
    monkeypatch.setattr(hc, "retry_async", _no_retry)
    return client


def test_hyperliquid_disabled_does_zero_network_calls(monkeypatch):
    from data.connectors import hyperliquid_adapter as hl

    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("network call while disabled")

    monkeypatch.setattr(hl.httpx_client, "get_client", _boom)
    monkeypatch.setenv("HYPERLIQUID_MARKET_DATA_ENABLED", "0")
    assert hl.get_candles("BTCUSDT", "1h") == []
    assert hl.get_funding("BTCUSDT") is None
    assert called["n"] == 0


def test_hyperliquid_candles_normalization(monkeypatch):
    from data.connectors import hyperliquid_adapter as hl

    monkeypatch.setenv("HYPERLIQUID_MARKET_DATA_ENABLED", "1")
    now_ms = 1_700_000_000_000

    def handler(payload_type, payload):
        assert payload_type == "candlesSnapshot"
        req = payload.get("req", {})
        assert req.get("coin") == "BTC"
        assert req.get("interval") == "1h"
        return [{"t": now_ms - 3600_000, "o": "100", "h": "101", "l": "99", "c": "100.5", "v": "12.3"},
                {"t": now_ms, "o": "100.5", "h": "102", "l": "100", "c": "101.5", "v": "9.1"}]

    client = _install_fake_hyperliquid(monkeypatch, handler)
    candles = hl.get_candles("BTCUSDT", "1h", limit=2)
    assert len(candles) == 2
    assert candles[-1]["timestamp"] == now_ms
    assert candles[-1]["close"] == 101.5
    assert client.calls[0][1]["req"]["coin"] == "BTC"


def test_hyperliquid_funding_and_mark_price(monkeypatch):
    from data.connectors import hyperliquid_adapter as hl

    monkeypatch.setenv("HYPERLIQUID_MARKET_DATA_ENABLED", "1")

    def handler(payload_type, payload):
        if payload_type == "metaAndAssetCtxs":
            return [{"coin": "ETH", "markPx": "3500.0", "oraclePx": "3498.0",
                     "funding": "0.0001", "openInterest": "120.5", "prevDayPx": "3400.0"}]
        return []

    _install_fake_hyperliquid(monkeypatch, handler)
    assert hl.get_mark_price("ETHUSDT") == 3500.0
    assert hl.get_funding("ETHUSDT") == 0.0001
    # Second read is cache-served (no additional network call).
    assert hl.get_mark_price("ETHUSDT") == 3500.0


def test_hyperliquid_unsupported_symbol_cached(monkeypatch):
    from data.connectors import hyperliquid_adapter as hl

    monkeypatch.setenv("HYPERLIQUID_MARKET_DATA_ENABLED", "1")

    def handler(payload_type, payload):
        return []  # no market -> unsupported

    client = _install_fake_hyperliquid(monkeypatch, handler)
    assert hl.get_candles("NOTAREALCOINUSDT", "1h") == []
    assert hl.get_candles("NOTAREALCOINUSDT", "1h") == []
    assert len(client.calls) == 1  # second attempt served from the unsupported cache


def test_hyperliquid_testnet_url_separation(monkeypatch):
    from data.connectors import hyperliquid_adapter as hl

    monkeypatch.setenv("HYPERLIQUID_MARKET_DATA_ENABLED", "1")
    monkeypatch.setenv("HYPERLIQUID_TESTNET", "1")
    assert hl.api_url() == hl.TESTNET_API_URL
    monkeypatch.setenv("HYPERLIQUID_TESTNET", "0")
    assert hl.api_url() == hl.MAINNET_API_URL
    health = hl.health()
    assert health["state"] == "configured"
    assert health["network"] in {"mainnet", "testnet"}


def test_hyperliquid_registry_opt_in(monkeypatch):
    from data.connector_registry import get_async_providers_for_asset

    monkeypatch.setenv("HYPERLIQUID_MARKET_DATA_ENABLED", "0")
    names = [name for name, _ in get_async_providers_for_asset("crypto")]
    assert "hyperliquid_connector" not in names
    monkeypatch.setenv("HYPERLIQUID_MARKET_DATA_ENABLED", "1")
    names = [name for name, _ in get_async_providers_for_asset("crypto")]
    assert "hyperliquid_connector" in names


# ---------------------------------------------------------------------------
# Phase 5 — asset-class certification framework
# ---------------------------------------------------------------------------

def _full_evidence() -> dict:
    return {step: True for step in (
        "symbol_discovery", "canonical_mapping", "historical_candles", "live_bid_ask",
        "fresh_timestamp", "signal_generation", "valid_geometry", "signal_persistence",
        "telegram_delivery", "delivery_proof", "paper_open", "outcome_monitoring",
        "position_close", "performance_projection", "provider_failover", "market_hours",
        "production_diagnostics",
    )}


def test_certification_unsupported_class() -> None:
    result = evaluate_certification("hyperliquid", _full_evidence())
    assert result.readiness is ReadinessState.UNSUPPORTED
    assert result.coverage_pct == 0.0


def test_certification_crypto_spot_paper_ready() -> None:
    result = evaluate_certification("crypto", _full_evidence())
    assert result.readiness is ReadinessState.PAPER_READY
    assert result.coverage_pct == 100.0


def test_certification_market_data_partial_when_no_live_quote() -> None:
    evidence = _full_evidence()
    evidence["live_bid_ask"] = False
    result = evaluate_certification("commodity", evidence)
    assert result.readiness is ReadinessState.MARKET_DATA_PARTIAL


def test_certification_degraded_when_provider_failing() -> None:
    evidence = _full_evidence()
    evidence["live_bid_ask"] = False
    evidence["provider_status"] = "failing"  # XAGUSD-style: candles ok, live quote down
    result = evaluate_certification("commodity", evidence)
    assert result.readiness is ReadinessState.DEGRADED


def test_certification_analysis_ready_before_delivery() -> None:
    evidence = _full_evidence()
    for step in ("signal_generation", "valid_geometry", "signal_persistence",
                 "telegram_delivery", "delivery_proof"):
        evidence[step] = False
    result = evaluate_certification("stock", evidence)
    assert result.readiness is ReadinessState.ANALYSIS_READY


def test_certification_testnet_and_live_guarded() -> None:
    result = evaluate_certification("crypto_perpetual", _full_evidence(), testnet_ready=True)
    assert result.readiness is ReadinessState.TESTNET_READY
    result = evaluate_certification("crypto_perpetual", _full_evidence(), live_guarded=True)
    assert result.readiness is ReadinessState.LIVE_GUARDED
    assert "safe-mode-ready" in readiness_label(ReadinessState.LIVE_GUARDED)


def test_certification_blocked() -> None:
    result = evaluate_certification("index", _full_evidence(), blocked_reason="no_tradable_venue")
    assert result.readiness is ReadinessState.BLOCKED
    assert result.blocked_reason == "no_tradable_venue"


def test_certification_contextual_macro_not_deliverable() -> None:
    evidence = _full_evidence()
    evidence["canonical_mapping"] = False
    result = evaluate_certification("macro", evidence)
    assert result.readiness is ReadinessState.CONFIGURED
