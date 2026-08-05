"""Regression tests: V2.0 portfolio risk authority."""
from __future__ import annotations

from decimal import Decimal

import pytest

from core.risk_authority import (
    PortfolioRiskAuthority,
    RiskLimits,
    TradeCandidate,
)


def _authority(equity: str = "1000") -> PortfolioRiskAuthority:
    return PortfolioRiskAuthority(
        limits=RiskLimits(
            max_positions_per_symbol=1,
            max_simultaneous_theses=2,
            max_account_exposure_pct=Decimal("0.20"),
            max_symbol_exposure_pct=Decimal("0.05"),
            max_daily_loss_pct=Decimal("0.05"),
            max_consecutive_losses=4,
            max_drawdown_pct=Decimal("0.15"),
        ),
        equity=Decimal(equity),
        kill_switch_global=False,
    )


def _candidate(symbol: str = "BTCUSDT", notional: str = "40") -> TradeCandidate:
    return TradeCandidate(
        symbol=symbol,
        direction="long",
        notional=notional,
        entry="100",
        stop="95",
    )


def test_kill_switch_blocks_everything() -> None:
    authority = _authority()
    authority.set_kill_switch(True)
    decision = authority.evaluate(_candidate())
    assert not decision.approved
    assert decision.reason == "global_execution_kill_switch"


def test_symbol_exposure_limit() -> None:
    authority = _authority()
    decision = authority.evaluate(_candidate(notional="100"))  # 10% of equity > 5% cap
    assert not decision.approved
    assert decision.reason == "symbol_exposure_limit"


def test_account_exposure_limit() -> None:
    # Symbol cap raised to 10% so a single symbol can carry enough notional to
    # trip the 20% account-exposure cap.
    authority = PortfolioRiskAuthority(
        limits=RiskLimits(
            max_positions_per_symbol=1,
            max_simultaneous_theses=2,
            max_account_exposure_pct=Decimal("0.20"),
            max_symbol_exposure_pct=Decimal("0.10"),
        ),
        equity=Decimal("1000"),
        kill_switch_global=False,
    )
    assert authority.reserve(_candidate(symbol="BTCUSDT", notional="80")).approved
    # 80 reserved; a 130 notional candidate pushes total exposure to 21% > 20%.
    decision = authority.evaluate(_candidate(symbol="ETHUSDT", notional="130"))
    assert not decision.approved
    assert decision.reason == "account_exposure_limit"


def test_max_positions_per_symbol() -> None:
    authority = _authority()
    assert authority.reserve(_candidate()).approved
    decision = authority.evaluate(_candidate())
    assert not decision.approved
    assert decision.reason == "max_positions_per_symbol"


def test_max_simultaneous_theses() -> None:
    authority = _authority()
    assert authority.reserve(_candidate(symbol="A")).approved
    assert authority.reserve(_candidate(symbol="B")).approved
    decision = authority.evaluate(_candidate(symbol="C"))
    assert not decision.approved
    assert decision.reason == "max_simultaneous_theses"


def test_daily_loss_breaker() -> None:
    authority = _authority()
    authority.record_pnl(Decimal("-60"))  # 6% loss exceeds the 5% daily cap
    decision = authority.evaluate(_candidate())
    assert not decision.approved
    assert decision.reason == "daily_loss_breaker"


def test_consecutive_loss_breaker() -> None:
    authority = _authority()
    for _ in range(4):
        authority.record_pnl(Decimal("-1"))
    decision = authority.evaluate(_candidate())
    assert not decision.approved
    assert decision.reason == "consecutive_loss_breaker"
    # A win resets the counter and reopens admission.
    authority.record_pnl(Decimal("5"))
    assert authority.evaluate(_candidate()).approved


def test_drawdown_breaker() -> None:
    authority = _authority()
    authority.record_pnl(Decimal("50"))  # peak 1050
    authority.record_pnl(Decimal("-250"))  # equity 800 -> drawdown 23.8% > 15%
    # A new day resets the intraday loss breaker; portfolio drawdown remains.
    authority.reset_daily(equity=Decimal("800"))
    decision = authority.evaluate(_candidate())
    assert not decision.approved
    assert decision.reason == "drawdown_breaker"


def test_spread_breaker() -> None:
    authority = _authority()
    decision = authority.evaluate(_candidate(symbol="X", notional="40"))
    assert decision.approved
    candidate = TradeCandidate(
        symbol="X", direction="long", notional="40", entry="100", stop="95",
        spread_bps="100",  # > 50 bps cap
    )
    decision = authority.evaluate(candidate)
    assert not decision.approved
    assert decision.reason == "spread_breaker"


def test_decimal_safe_arithmetic() -> None:
    authority = PortfolioRiskAuthority(
        limits=RiskLimits(max_simultaneous_theses=5),
        equity=Decimal("1000"),
        kill_switch_global=False,
    )
    for index in range(3):
        decision = authority.reserve(TradeCandidate(
            symbol=f"S{index}", direction="long", notional="0.1", entry="100", stop="95",
        ))
        assert decision.approved
    assert authority.total_notional == Decimal("0.3")
    authority.release("S0", "0.1")
    assert authority.total_notional == Decimal("0.2")


def test_rejects_zero_and_negative_notional() -> None:
    authority = _authority()
    decision = authority.evaluate(_candidate(notional="0"))
    assert not decision.approved
    assert decision.reason == "invalid_notional"
    decision = authority.evaluate(_candidate(notional="-5"))
    assert not decision.approved
    assert decision.reason == "invalid_notional"


def test_reserve_release_restores_state() -> None:
    authority = _authority()
    authority.reserve(_candidate())
    assert authority.open_positions == 1
    assert authority.positions_by_symbol["BTCUSDT"] == 1
    authority.release("BTCUSDT", "40")
    assert authority.open_positions == 0
    assert authority.positions_by_symbol["BTCUSDT"] == 0


def test_limits_from_env_reject_negative() -> None:
    with pytest.raises(ValueError):
        RiskLimits(max_account_exposure_pct=Decimal("-0.1"))
