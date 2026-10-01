#!/usr/bin/env python3
"""Replay the 2026-10-01 paper/delivery integrity incident against staging.

This is a staging-only certification mutation. It writes uniquely identified
diagnostic rows to the isolated staging PostgreSQL database, exercises the
canonical confirmed-delivery -> paper-open -> active-signal path, and verifies
missed-entry outcome accounting. It never sends Telegram messages and never
submits broker orders.

The retained rows are deliberate certification evidence for
scripts/staging_runtime_proof.py.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


EXPECTED_STAGING_PROJECT = "8d21a09b-8e45-4c10-87dd-e3568441153f"
LIVE_FLAGS = (
    "REAL_EXECUTION_ENABLED",
    "AUTO_EXECUTION_ENABLED",
    "AUTO_TRADE_ENABLED",
    "COPY_TRADE_ENABLED",
    "PROP_EXECUTION_ENABLED",
    "BYBIT_EXECUTION_ENABLED",
    "HYPERLIQUID_MAINNET_EXECUTION_ENABLED",
    "MT5_ALLOW_LIVE_ACCOUNTS",
    "REAL_PAYOUTS_ENABLED",
    "AUTOMATIC_PAYOUTS_ENABLED",
    "PAYSTACK_TRANSFERS_ENABLED",
    "PAYMENTS_PUBLIC_ENABLED",
)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _guard() -> dict[str, Any]:
    from core.env import runtime_environment_name

    env = runtime_environment_name("")
    actual_project = str(os.getenv("RAILWAY_PROJECT_ID") or "").strip()
    pinned_project = str(os.getenv("STAGING_CERTIFICATION_PROJECT_ID") or "").strip()
    profile = str(os.getenv("SIGNALRANK_ENV_PROFILE") or "").strip().lower()
    kill_switch = _truthy(os.getenv("GLOBAL_EXECUTION_KILL_SWITCH", "1"))
    unsafe = [name for name in LIVE_FLAGS if _truthy(os.getenv(name, "0"))]

    errors: list[str] = []
    if env != "staging":
        errors.append(f"environment={env or 'missing'}")
    if actual_project != EXPECTED_STAGING_PROJECT:
        errors.append("unexpected_railway_project")
    if pinned_project != EXPECTED_STAGING_PROJECT:
        errors.append("staging_project_pin_mismatch")
    if profile != "staging-certification":
        errors.append(f"profile={profile or 'missing'}")
    if not kill_switch:
        errors.append("global_execution_kill_switch_off")
    if unsafe:
        errors.append("unsafe_live_flags=" + ",".join(unsafe))
    if errors:
        raise RuntimeError("OCT1_REPLAY_BLOCKED " + ";".join(errors))
    return {
        "environment": env,
        "project_id": actual_project,
        "profile": profile,
        "kill_switch": kill_switch,
        "live_flags_off": list(LIVE_FLAGS),
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _noop_notification(**_kwargs: Any) -> None:
    """Replay never sends external Telegram/web notifications."""
    return None


async def run() -> dict[str, Any]:
    guard = _guard()

    from sqlalchemy import func, select

    from core.paper_trading_service import paper_trading_service
    from db.models import (
        Outcome,
        PaperAccount,
        PaperPosition,
        PaperTradeAttempt,
        Signal,
        SignalDelivery,
        SignalLifecycle,
        User,
    )
    from db.pg_features import list_delivered_signals_for_user
    from db.session import get_session
    from engine.realtime_outcome_tracker import _persist_outcome
    from services.user_intelligence import (
        UserTradingPreferences,
        set_platform_user_trading_preferences,
        signal_matches_preferences,
    )

    now = _utcnow()
    run_id = uuid4().hex[:10]
    telegram_user_id = 9_910_000_000_000 + int(run_id[:6], 16)
    user_name = f"oct1-cert-{run_id}"
    us30_id = str(uuid4())
    missed_id = str(uuid4())
    us30_display = f"OCT1U{run_id[:8].upper()}"[:20]
    missed_display = f"OCT1M{run_id[:8].upper()}"[:20]

    # These are the exact levels from the user's delivered US30 message.
    snapshot_entry = 50686.17
    snapshot_stop = 50877.72
    snapshot_targets = [50134.51, 49582.84, 49031.18]
    snapshot_generated_at = now - timedelta(seconds=30)
    snapshot_expires_at = now + timedelta(minutes=90)

    # Deliberately wrong/stale mutable row values reproduce the old failure:
    # paper must use the immutable delivery receipt instead.
    mutable_entry = 51321.24
    mutable_stop = 51484.80
    mutable_targets = [50850.19, 50379.14, 49908.10]
    mutable_created_at = now - timedelta(hours=4)
    mutable_expires_at = now - timedelta(hours=2)

    async with get_session(
        priority="critical",
        label="certification.oct1.seed",
        timeout_seconds=15.0,
        drop_if_busy=False,
    ) as session:
        user = User(
            telegram_user_id=telegram_user_id,
            username=user_name,
            display_name="Oct 1 staging certification",
            tier="vip",
            premium_until=now + timedelta(days=30),
            accepted_terms=True,
            account_status="active",
            onboarding_status="complete",
            execution_mode="manual",
            telegram_reachable=False,
            notification_suppressed=True,
            public_user_id=str(uuid4()),
            updated_at=now,
        )
        session.add(user)
        await session.flush()

        # Intentionally reject index/US30 under ordinary profile matching.
        prefs = UserTradingPreferences(
            trade_profile="all",
            risk_profile="balanced",
            asset_classes=("crypto",),
            preferred_assets=("BTCUSDT",),
            preferred_timeframes=("1h",),
            preferred_strategies=("mean reversion",),
            sessions=("auto",),
            trading_mode="paper",
            execution_mode="manual",
            min_signal_score=95.0,
            max_daily_trades=10,
            max_concurrent_positions=3,
            max_daily_loss_pct=5.0,
        )
        await set_platform_user_trading_preferences(session, int(user.id), prefs)

        account = PaperAccount(
            user_id=int(user.id),
            starting_balance=100000.0,
            cash_balance=100000.0,
            realized_pnl=0.0,
            currency="USD",
            auto_trade_enabled=True,
            risk_pct=0.5,
            max_open_positions=5,
            min_signal_score=0.0,
            spread_bps=0.0,
            slippage_bps=0.0,
            fee_bps=0.0,
            target_mode="TP1",
            allowed_directions="both",
            allowed_asset_classes=["index"],
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(account)

        us30 = Signal(
            signal_id=us30_id,
            display_id=us30_display,
            asset="US30",
            asset_class="index",
            timeframe="15m",
            direction="SELL",
            entry=mutable_entry,
            stop_loss=mutable_stop,
            take_profit=json.dumps(mutable_targets),
            rr_estimate=2.88,
            score=78.3,
            regime="TRENDING",
            status="issued",
            strategy_name="EMA Trend",
            strategy_group="trend",
            strength=0.85,
            created_at=mutable_created_at,
            expires_at=mutable_expires_at,
            expired=True,
            archived=True,
            ml_probability_raw=0.477,
            ml_probability_calibrated=0.61,
            ml_calibration_validated=False,
            ml_recovery_mode=True,
            ml_recovery_reason="staging_oct1_incident_replay",
            quality_gate_passed=True,
            quality_gate_version="oct1-cert",
            trade_profile="all",
        )
        session.add(us30)

        snapshot = {
            "signal_id": us30_id,
            "display_id": us30_display,
            "asset": "US30",
            "asset_class": "index",
            "timeframe": "15m",
            "direction": "SELL",
            "entry": snapshot_entry,
            "stop_loss": snapshot_stop,
            "take_profits": snapshot_targets,
            "score": 85.2,
            "generated_at": snapshot_generated_at.replace(tzinfo=timezone.utc).isoformat(),
            "expires_at": snapshot_expires_at.replace(tzinfo=timezone.utc).isoformat(),
            "strategy_name": "EMA Trend",
            "regime": "TRENDING",
            "certification_run_id": run_id,
        }
        delivery = SignalDelivery(
            user_id=int(user.id),
            signal_id=us30_id,
            tier_at_send="vip",
            delivered_at=now,
            sent_ok=True,
            delivery_state="confirmed",
            attempt_count=1,
            dispatch_started_at=now,
            telegram_send_started_at=now,
            delivery_confirmed_at=now,
            telegram_chat_id=telegram_user_id,
            telegram_message_id=990001,
            telegram_api_result={
                "ok": True,
                "signal_snapshot": snapshot,
                "certification": "oct1_incident_replay",
            },
            generated_at_utc=snapshot_generated_at,
            delivered_at_utc=now,
            display_timezone="Africa/Lagos",
            delivery_latency_seconds=1,
            signal_age_at_delivery_seconds=30,
            last_attempt_at=now,
        )
        session.add(delivery)
        session.add(
            SignalLifecycle(
                signal_id=us30_id,
                state="ACTIVE_TRADE",
                generated_at=snapshot_generated_at,
                watch_started_at=snapshot_generated_at,
                entry_touched_at=now,
                last_price=snapshot_entry,
                last_checked_at=now,
                max_price_seen=snapshot_entry,
                min_price_seen=snapshot_entry,
                updated_at=now,
            )
        )

        # Second signal reproduces the BAC "entry never triggered" accounting path.
        missed = Signal(
            signal_id=missed_id,
            display_id=missed_display,
            asset="BAC",
            asset_class="stock",
            timeframe="1m",
            direction="SELL",
            entry=53.09,
            stop_loss=53.2214,
            take_profit=json.dumps([52.7115, 52.3331, 51.9546]),
            rr_estimate=2.88,
            score=80.7,
            regime="TRENDING",
            status="issued",
            strategy_name="EMA Trend",
            strategy_group="trend",
            strength=0.80,
            created_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(minutes=85),
            expired=False,
            archived=False,
            quality_gate_passed=True,
            quality_gate_version="oct1-cert",
            trade_profile="all",
        )
        session.add(missed)
        session.add(
            SignalDelivery(
                user_id=int(user.id),
                signal_id=missed_id,
                tier_at_send="vip",
                delivered_at=now,
                sent_ok=True,
                delivery_state="confirmed",
                attempt_count=1,
                delivery_confirmed_at=now,
                telegram_chat_id=telegram_user_id,
                telegram_message_id=990002,
                telegram_api_result={
                    "ok": True,
                    "signal_snapshot": {
                        "signal_id": missed_id,
                        "display_id": missed_display,
                        "asset": "BAC",
                        "asset_class": "stock",
                        "timeframe": "1m",
                        "direction": "SELL",
                        "entry": 53.09,
                        "stop_loss": 53.2214,
                        "take_profits": [52.7115, 52.3331, 51.9546],
                        "score": 80.7,
                        "generated_at": (now - timedelta(minutes=5)).replace(tzinfo=timezone.utc).isoformat(),
                        "expires_at": (now + timedelta(minutes=85)).replace(tzinfo=timezone.utc).isoformat(),
                        "certification_run_id": run_id,
                    },
                    "certification": "oct1_incident_replay",
                },
                generated_at_utc=now - timedelta(minutes=5),
                delivered_at_utc=now,
                display_timezone="Africa/Lagos",
                delivery_latency_seconds=1,
                signal_age_at_delivery_seconds=300,
                last_attempt_at=now,
            )
        )
        session.add(
            SignalLifecycle(
                signal_id=missed_id,
                state="MISSED_ENTRY",
                generated_at=now - timedelta(minutes=5),
                watch_started_at=now - timedelta(minutes=5),
                expired_at=now,
                closed_at=now,
                terminal_event_type="missed_entry",
                terminal_price=53.575,
                terminal_evidence={
                    "observation_provider": "staging_oct1_replay",
                    "observation_high": 53.575,
                    "observation_low": 53.09,
                },
                last_price=53.575,
                last_checked_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        user_id = int(user.id)
        delivery_id = int(delivery.id)

    # Candidate discovery must reconstruct the delivered receipt, not mutable row.
    candidates = await paper_trading_service._telegram_delivery_candidates(200)
    candidate = next((row for row in candidates if row.get("signal_id") == us30_id), None)
    if candidate is None:
        raise RuntimeError("OCT1_REPLAY_FAIL delivery candidate missing")

    prefs_ok, prefs_reason = signal_matches_preferences(candidate, prefs)
    assertions: dict[str, bool] = {
        "delivery_proven": candidate.get("delivery_proven") is True,
        "ordinary_profile_would_reject": prefs_ok is False,
        "snapshot_entry_restored": abs(float(candidate.get("entry") or 0) - snapshot_entry) < 1e-9,
        "snapshot_stop_restored": abs(float(candidate.get("stop_loss") or 0) - snapshot_stop) < 1e-9,
        "snapshot_targets_restored": [float(v) for v in candidate.get("take_profits") or []] == snapshot_targets,
        "snapshot_generated_at_restored": candidate.get("generated_at") == snapshot_generated_at,
        "snapshot_expiry_restored": candidate.get("expires_at") == snapshot_expires_at,
        "mutable_row_not_reused": abs(float(candidate.get("entry") or 0) - mutable_entry) > 1.0,
    }

    # No external notification is emitted by this replay process.
    original_notify = paper_trading_service._notify_paper_decision
    paper_trading_service._notify_paper_decision = _noop_notification  # type: ignore[method-assign]
    try:
        first_status = await paper_trading_service._open_candidate(candidate, snapshot_entry)
        second_status = await paper_trading_service._open_candidate(candidate, snapshot_entry)
    finally:
        paper_trading_service._notify_paper_decision = original_notify  # type: ignore[method-assign]

    async with get_session(
        priority="critical",
        label="certification.oct1.verify",
        timeout_seconds=15.0,
        drop_if_busy=False,
    ) as session:
        positions = (
            await session.execute(
                select(PaperPosition).where(
                    PaperPosition.user_id == user_id,
                    PaperPosition.signal_id == us30_id,
                )
            )
        ).scalars().all()
        attempts = (
            await session.execute(
                select(PaperTradeAttempt).where(
                    PaperTradeAttempt.user_id == user_id,
                    PaperTradeAttempt.signal_id == us30_id,
                )
            )
        ).scalars().all()

        active = await list_delivered_signals_for_user(
            session,
            telegram_user_id,
            lookback_days=7,
            status_filter="active",
            limit=20,
        )
        active_ids = {str(row.signal_id) for row in active}
        await session.rollback()

    if len(positions) != 1:
        raise RuntimeError(f"OCT1_REPLAY_FAIL expected one paper position, found {len(positions)}")
    position = positions[0]
    assertions.update(
        {
            "paper_first_opened": first_status == "opened",
            "duplicate_open_prevented": second_status == "skipped" and len(positions) == 1,
            "position_uses_snapshot_entry": abs(float(position.signal_entry) - snapshot_entry) < 1e-9,
            "position_uses_snapshot_stop": abs(float(position.stop_loss) - snapshot_stop) < 1e-9,
            "position_uses_snapshot_targets": [float(v) for v in position.take_profits] == snapshot_targets,
            "signals_command_projection_contains_active_signal": us30_id in active_ids,
            "no_profile_mismatch_attempt": not any(
                str(row.reason) == "profile_preference_mismatch" for row in attempts
            ),
            "no_signal_stale_attempt": not any(str(row.reason) == "signal_stale" for row in attempts),
        }
    )

    # Use the real outcome tracker for a never-entered signal. The observed
    # excursion may be retained, but realized R/P&L must remain NULL.
    await _persist_outcome(missed_id, "missed_entry", 53.09, 53.575)

    async with get_session(
        priority="critical",
        label="certification.oct1.outcome_verify",
        timeout_seconds=15.0,
        drop_if_busy=False,
    ) as session:
        outcome = (
            await session.execute(select(Outcome).where(Outcome.signal_id == missed_id))
        ).scalar_one_or_none()
        missed_positions = int(
            (
                await session.execute(
                    select(func.count(PaperPosition.position_id)).where(
                        PaperPosition.signal_id == missed_id
                    )
                )
            ).scalar_one()
            or 0
        )
        await session.rollback()

    if outcome is None:
        raise RuntimeError("OCT1_REPLAY_FAIL missed-entry outcome missing")
    outcome_meta = dict(outcome.meta or {})
    assertions.update(
        {
            "missed_entry_has_no_position": missed_positions == 0,
            "missed_entry_realized_r_null": outcome.r_multiple is None,
            "missed_entry_percent_null": outcome.percent is None,
            "missed_entry_pnl_pct_null": outcome.pnl_pct is None,
            "missed_entry_marks_no_realized_position": outcome_meta.get("realized_position_opened") is False,
            "missed_entry_counterfactual_retained": outcome_meta.get("missed_entry_observed_r") is not None,
        }
    )

    failed = sorted(name for name, passed in assertions.items() if not passed)
    report = {
        "evidence_type": "oct1_signal_paper_incident_replay",
        "status": "PASS" if not failed else "FAILED",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guard": guard,
        "certification_run_id": run_id,
        "user_id": user_id,
        "telegram_user_id": telegram_user_id,
        "signal_ids": {"paper_open": us30_id, "missed_entry": missed_id},
        "delivery_id": delivery_id,
        "profile_mismatch_reason": prefs_reason,
        "paper_open_status": first_status,
        "duplicate_open_status": second_status,
        "position_id": str(position.position_id),
        "active_signal_ids": sorted(active_ids),
        "assertions": assertions,
        "failed_assertions": failed,
        "retained_evidence": True,
        "external_notifications_sent": False,
        "broker_orders_submitted": False,
    }
    if failed:
        raise RuntimeError("OCT1_REPLAY_FAIL " + ",".join(failed))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    try:
        report = asyncio.run(run())
        code = 0
    except Exception as exc:
        report = {
            "evidence_type": "oct1_signal_paper_incident_replay",
            "status": "FAILED",
            "error": type(exc).__name__,
            "detail": str(exc)[:500],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        code = 1
    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(payload)
    if args.output:
        path = Path(args.output)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
