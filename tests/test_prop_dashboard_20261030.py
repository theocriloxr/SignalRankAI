"""Prop dashboard: limit usage, trading days and target progress (CX-PROP-04, 30 Oct 2026).

The meters must show exactly what the execution gate enforces, missing data
must read as unavailable (never zero), and objectives must stay display-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from services import prop_dashboard as pdash

NOW = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)
POLICY = {"account_mode": "PROP", "prop_firm": "Example Firm", "prop_phase": "challenge", "currency": "USD",
          "reset_timezone": "UTC", "max_daily_loss_pct": "0.04", "external_max_daily_loss_pct": "0.05",
          "max_total_drawdown_pct": "0.08", "external_max_total_drawdown_pct": "0.10", "safety_buffer_pct": "0.01",
          "certified": False, "frozen": False}


def _snap(when: datetime, equity: str) -> dict:
    return {"entry_type": "equity_snapshot", "equity": Decimal(equity), "provider_timestamp": when, "created_at": when}


def test_meters_match_the_execution_gate():
    from core.account_policy import AccountRiskSnapshot, evaluate_account_policy, policy_from_mapping

    entries = [_snap(NOW - timedelta(days=2), "100000"), _snap(NOW - timedelta(days=1), "103000"),
               _snap(NOW - timedelta(hours=16), "102000"), _snap(NOW - timedelta(minutes=5), "99500")]
    out = pdash.summarize(POLICY, entries, {}, NOW)
    # day start = last snapshot before midnight UTC (102,000); peak 103,000; current 99,500
    assert Decimal(out["daily_loss"]["used_pct"]) == pytest.approx(Decimal("2500") / Decimal("102000"), abs=Decimal("1e-6"))
    assert Decimal(out["total_drawdown"]["used_pct"]) == pytest.approx(Decimal("3500") / Decimal("103000"), abs=Decimal("1e-6"))
    gate = evaluate_account_policy(
        policy_from_mapping({**POLICY, "connection_id": "c1", "user_id": 1, "execution_permission": "MANUAL"}),
        AccountRiskSnapshot(current_equity=Decimal("99500"), day_start_equity=Decimal("102000"),
                            peak_equity=Decimal("103000")), execution_mode="manual_confirmed")
    assert Decimal(out["daily_loss"]["limit_pct"]) == gate.effective_daily_loss_limit == Decimal("0.04")
    assert Decimal(out["total_drawdown"]["limit_pct"]) == gate.effective_drawdown_limit == Decimal("0.08")
    assert out["daily_loss"]["used_of_limit"] == "0.6127" and out["total_drawdown"]["used_of_limit"] == "0.4248"


def test_the_firm_limit_minus_buffer_wins_when_it_is_tighter():
    policy = {**POLICY, "max_daily_loss_pct": "0.10", "external_max_daily_loss_pct": "0.05", "safety_buffer_pct": "0.01"}
    out = pdash.summarize(policy, [_snap(NOW - timedelta(minutes=1), "100000")], {}, NOW)
    assert out["daily_loss"]["limit_pct"] == "0.040000"


def test_a_realized_loss_larger_than_the_equity_move_counts():
    entries = [_snap(NOW - timedelta(days=1), "100000"), _snap(NOW - timedelta(minutes=2), "99900"),
               {"entry_type": "realized_pnl", "realized_pnl": Decimal("-1500"), "provider_timestamp": NOW - timedelta(hours=1),
                "created_at": NOW - timedelta(hours=1)}]
    out = pdash.summarize(POLICY, entries, {}, NOW)
    assert out["daily_loss"]["used_pct"] == "0.015000"


def test_days_follow_the_accounts_reset_timezone():
    policy = {**POLICY, "reset_timezone": "America/New_York"}  # midnight NY = 04:00 UTC on 30 Oct (EDT)
    entries = [_snap(datetime(2026, 10, 30, 3, 30, tzinfo=timezone.utc), "100000"),  # 23:30 on the 29th in NY
               _snap(datetime(2026, 10, 30, 5, 0, tzinfo=timezone.utc), "101000"),
               _snap(NOW - timedelta(minutes=1), "100500")]
    for hour in (3, 5):  # fills at 23:00 on the 29th and 01:00 on the 30th, New York time
        when = datetime(2026, 10, 30, hour, 0, tzinfo=timezone.utc)
        entries.append({"entry_type": "fill", "provider_timestamp": when, "created_at": when})
    out = pdash.summarize(policy, entries, {"min_trading_days": 4}, NOW)
    assert out["equity"]["day_start"] == "100000.00"
    assert out["trading_days"] == {"count": 2, "minimum": 4, "last_trading_day": "2026-10-30"}


def test_missing_or_stale_data_is_unavailable_not_zero():
    empty = pdash.summarize(POLICY, [], {}, NOW)
    assert empty["unavailable"] == ["no_equity_snapshots"]
    assert empty["daily_loss"]["used_pct"] is None and empty["total_drawdown"]["used_of_limit"] is None
    assert empty["equity"]["current"] is None and empty["profit_target"]["progress_pct"] is None
    stale = pdash.summarize(POLICY, [_snap(NOW - timedelta(hours=2), "100000")], {}, NOW)
    assert "latest_snapshot_stale" in stale["unavailable"] and stale["evidence"]["stale"] is True


def test_profit_progress_uses_the_entered_starting_balance_and_target():
    entries = [_snap(NOW - timedelta(days=3), "100500"), _snap(NOW - timedelta(minutes=1), "104000")]
    out = pdash.summarize(POLICY, entries, {"starting_balance": "100000", "profit_target_pct": "0.08"}, NOW)
    assert out["equity"]["starting_source"] == "objective"
    assert out["profit_target"] == {"target_pct": "0.080000", "progress_pct": "0.040000", "progress_of_target": "0.5000"}
    no_target = pdash.summarize(POLICY, entries, {}, NOW)
    assert no_target["equity"]["starting_source"] == "first_snapshot" and no_target["profit_target"]["target_pct"] is None
    losing = pdash.summarize(POLICY, [_snap(NOW - timedelta(minutes=1), "99000")],
                             {"starting_balance": "100000", "profit_target_pct": "0.08"}, NOW)
    assert losing["profit_target"]["progress_of_target"] == "0.0000"


@pytest.mark.parametrize("raw, error", [({"bonus": 1}, "unknown_objective"), ({"profit_target_pct": "8"}, "invalid_profit_target_pct"),
                                        ({"min_trading_days": -1}, "invalid_min_trading_days"),
                                        ({"starting_balance": "0"}, "invalid_starting_balance")])
def test_objectives_are_validated(raw, error):
    with pytest.raises(ValueError, match=error):
        pdash.validate_objectives(raw)


# --- Real PostgreSQL -------------------------------------------------------------------------------

from tests.test_account_policy_reads_postgres_20261030 import _prop_account, isolated_postgres  # noqa: E402,F401


@pytest.mark.asyncio
async def test_dashboard_reads_the_ledger_and_objectives_leave_the_policy_alone(isolated_postgres):  # noqa: F811
    from services.account_policies import get_account_policy
    from services.trading_account_ledger import append_account_ledger_entry

    uid, connection_id = await _prop_account()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for i, (when, equity) in enumerate([(now - timedelta(days=2), "100000"), (now - timedelta(minutes=2), "101500")]):
        await append_account_ledger_entry(user_id=uid, connection_id=connection_id, provider="mt5",
                                          entry_type="equity_snapshot", source_event_id=f"snap-{i}",
                                          equity=equity, balance=equity, provider_timestamp=when)
    await append_account_ledger_entry(user_id=uid, connection_id=connection_id, provider="mt5", entry_type="fill",
                                      source_event_id="fill-1", amount="1", provider_timestamp=now - timedelta(hours=1))
    before = await get_account_policy(uid, connection_id)
    saved = await pdash.set_prop_objectives(uid, connection_id, {"starting_balance": "100000", "profit_target_pct": "0.08",
                                                                 "min_trading_days": 4})
    assert saved == {"starting_balance": "100000", "profit_target_pct": "0.08", "min_trading_days": 4}
    after = await get_account_policy(uid, connection_id)
    assert after["policy_version"] == before["policy_version"] and after["updated_at"] == before["updated_at"]

    board = await pdash.prop_dashboard(uid, connection_id)
    assert board["connection_id"] == connection_id and board["account_mode"] == "PROP"
    assert board["equity"]["current"] == "101500.00" and board["evidence"]["stale"] is False
    assert board["trading_days"]["count"] == 1 and board["trading_days"]["minimum"] == 4
    assert board["profit_target"]["progress_of_target"] == "0.1875"  # 1.5 % of an 8 % target
    assert board["daily_loss"]["limit_pct"] == "0.040000" and board["total_drawdown"]["limit_pct"] == "0.080000"


@pytest.mark.asyncio
async def test_another_account_cannot_read_or_write_it(isolated_postgres):  # noqa: F811
    _, connection_id = await _prop_account()
    intruder, _ = await _prop_account()
    with pytest.raises(LookupError):
        await pdash.prop_dashboard(intruder, connection_id)
    with pytest.raises(LookupError):
        await pdash.set_prop_objectives(intruder, connection_id, {"profit_target_pct": "0.1"})
