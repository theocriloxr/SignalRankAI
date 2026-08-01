from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.delivery_state import has_durable_delivery_proof, is_confirmed_delivery_state
from core.paper_sizing import calculate_paper_position_size
from services.performance_ledger import calculate_performance_metrics


ROOT = Path(__file__).resolve().parents[1]


def test_fee_aware_sizing_never_overdraws_at_one_hundred_percent_cap():
    result = calculate_paper_position_size(
        cash="100", risk_pct="100", risk_per_unit="1", fill="1",
        max_notional_pct="100", fee_bps="5",
    )
    assert result.total_required <= Decimal("100.00000001")
    assert result.notional < Decimal("100")
    assert result.entry_fee > 0


def test_default_ninety_five_percent_cap_reserves_fee_and_cash():
    result = calculate_paper_position_size(
        cash="10000", risk_pct="100", risk_per_unit="1", fill="1",
        max_notional_pct="95", fee_bps="5",
    )
    assert result.notional == Decimal("9500.00000000")
    assert result.total_required == Decimal("9504.75000000")


def test_risk_cap_can_be_tighter_than_cash_cap():
    result = calculate_paper_position_size(
        cash="10000", risk_pct="1", risk_per_unit="10", fill="100",
        max_notional_pct="95", fee_bps="5",
    )
    assert result.quantity == Decimal("10.000000000000")
    assert result.notional == Decimal("1000.00000000")


@pytest.mark.parametrize("risk_distance", ["0", "0.000000001", "-1"])
def test_invalid_stop_geometry_is_rejected(risk_distance: str):
    with pytest.raises(ValueError, match="invalid_risk_distance"):
        calculate_paper_position_size(
            cash="100", risk_pct="1", risk_per_unit=risk_distance, fill="1",
            max_notional_pct="95", fee_bps="5",
        )


def test_canonical_r_formulas_are_exact_and_stable():
    first = calculate_performance_metrics([Decimal("2"), Decimal("-1"), Decimal("0.5")])
    second = calculate_performance_metrics([Decimal("2"), Decimal("-1"), Decimal("0.5")])
    assert first == second
    assert first.net_r == Decimal("1.5")
    assert first.average_r == Decimal("0.50000000")
    assert first.median_r == Decimal("0.50000000")
    assert first.standardized_simple_return_pct == Decimal("1.50000000")
    assert first.average_standardized_return_pct == Decimal("0.50000000")
    assert first.standardized_compounded_return_pct == Decimal("1.48490000")


def test_delivery_proof_requires_all_durable_telegram_fields():
    assert is_confirmed_delivery_state("confirmed")
    assert has_durable_delivery_proof(SimpleNamespace(
        sent_ok=True, delivery_state="confirmed", delivery_confirmed_at=object(),
        telegram_chat_id=123, telegram_message_id=456,
    ))
    assert not has_durable_delivery_proof(SimpleNamespace(
        sent_ok=True, delivery_state="confirmed", delivery_confirmed_at=object(),
        telegram_chat_id=123, telegram_message_id=None,
    ))

def test_migration_0031_contains_ledger_attempt_and_immutability_guards():
    text = (ROOT / "db/migrations/versions/0031_performance_paper_reliability.py").read_text("utf-8")
    assert 'down_revision = "0030_signal_monitor_reliability"' in text
    assert "paper_trade_attempts" in text
    assert "performance_ledger_entries" in text
    assert "uq_paper_actual_position_user_signal" in text
    assert "WHERE LOWER(status) IN ('open', 'closed')" in text
    assert "trg_performance_ledger_finality" in text
    assert "ml_past_training_data" in text


def test_paper_service_uses_attempts_retries_and_fee_adjusted_sizing():
    source = (ROOT / "core/paper_trading_service.py").read_text("utf-8")
    assert "calculate_paper_position_size" in source
    assert "PaperTradeAttempt" in source
    assert 'decision="RETRY_PENDING"' in source
    assert "PAPER_CASH_TOLERANCE" in source
    assert "[paper_worker_cycle]" in source
    assert '_env_bool("PAPER_AUTO_TRADE_DEFAULT_ENABLED", False)' in source


def test_ml_tracker_never_logs_success_when_persistence_returns_false():
    source = (ROOT / "engine/realtime_outcome_tracker.py").read_text("utf-8")
    assert "_ml_saved = await log_ml_training_data" in source
    assert "if _ml_saved:" in source
    assert "ML training persistence returned false; retry required" in source


def test_repair_tool_is_dry_run_by_default_and_never_opens_a_trade():
    source = (ROOT / "scripts/repair_paper_fee_sizing_skips.py").read_text("utf-8")
    assert 'parser.add_argument("--apply", action="store_true"' in source
    assert '"opens_trade": False' in source
    assert "PaperPosition(" not in source
    assert 'decision="RETRY_PENDING"' in source


def test_performance_command_has_no_unverified_aggregate_fallback():
    source = (ROOT / "signalrank_telegram/commands.py").read_text("utf-8")
    start = source.index("async def performance_command")
    end = source.index("async def quality_command", start)
    handler = source[start:end]
    assert "get_user_performance_report" in handler
    assert "No estimated or unverified fallback was shown" in handler
    assert "SUM(o.r_multiple)" not in handler
    assert "Standardized compounded return (1% risk)" in handler
