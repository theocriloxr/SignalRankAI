from __future__ import annotations

from pathlib import Path

import pytest

from core.signal_identity import make_display_signal_id, public_signal_id, signal_id_line
from core.signal_lifecycle import (
    SAME_CANDLE_AMBIGUITY_POLICY,
    TP3_HIT,
    is_terminal_outcome,
    is_terminal_signal_state,
    lifecycle_transition_allowed,
)
from engine.realtime_outcome_tracker import _build_outcome_message, _outcome_monitoring_keyboard
from engine.signal_lifecycle import evaluate_observation


ROOT = Path(__file__).resolve().parents[1]


def test_public_signal_identity_is_stable_and_exact() -> None:
    signal_id = "801c174c-f10a-4abc-8def-0123456789ab"
    assert make_display_signal_id(signal_id) == "801c174c-f10"
    assert public_signal_id({"signal_id": signal_id}) == "801c174c-f10"
    assert public_signal_id({"signal_id": signal_id, "display_id": "stable-ref"}) == "stable-ref"
    assert signal_id_line({"signal_id": signal_id}) == "📌 Signal ID: 801c174c-f10"


@pytest.mark.parametrize("status", ["tp1", "tp2", "tp3", "sl", "expired"])
def test_every_outcome_message_includes_exact_signal_id_label(status: str) -> None:
    body = _build_outcome_message(
        signal_id="1ac75341-412a-4abc-8def-0123456789ab",
        asset="BTCUSDT",
        direction="LONG",
        entry=100.0,
        price=110.0 if status.startswith("tp") else 90.0,
        status=status,
        pnl_pct=10.0 if status.startswith("tp") else -10.0,
        tier_at_send="vip",
    )
    assert "📌 Signal ID: <code>1ac75341-412</code>" in body


def test_tp_controls_are_compact_and_never_appear_for_terminal_events() -> None:
    signal_id = "10767f59-270a-4abc-8def-0123456789ab"
    tp1 = _outcome_monitoring_keyboard(signal_id, "tp1")
    tp2 = _outcome_monitoring_keyboard(signal_id, "tp2")
    assert tp1 is not None and tp2 is not None
    tp1_data = [button.callback_data for row in tp1.inline_keyboard for button in row]
    assert any(value.startswith("sigmon_continue_1_") for value in tp1_data)
    assert any(value.startswith("sigmon_stop_1_") for value in tp1_data)
    assert all(len(value.encode("utf-8")) <= 64 for value in tp1_data)
    assert _outcome_monitoring_keyboard(signal_id, "tp3") is None
    assert _outcome_monitoring_keyboard(signal_id, "sl") is None


def test_same_candle_ambiguity_is_conservative_and_recorded() -> None:
    assert SAME_CANDLE_AMBIGUITY_POLICY == "stop_loss_first_conservative"
    events = evaluate_observation(
        state="WATCHING_FOR_ENTRY",
        direction="long",
        entry=100.0,
        stop_loss=95.0,
        tp_levels=[105.0, 110.0, 115.0],
        current_price=101.0,
        high=106.0,
        low=94.0,
    )
    assert events == ["entry_touched", "sl_hit"]


def test_terminal_lifecycle_is_irreversible_and_shared() -> None:
    assert is_terminal_signal_state(TP3_HIT)
    assert is_terminal_outcome("sl")
    assert not lifecycle_transition_allowed("TP3_HIT", "SL_HIT")
    assert not lifecycle_transition_allowed("SL_HIT", "TP1_HIT")


def test_models_define_unique_recipient_monitoring_and_callback_action() -> None:
    from db.models import User, UserSignalMonitoring, UserSignalMonitoringAction

    assert hasattr(User, "is_blocked") and hasattr(User, "is_suspended")
    monitor_constraints = {constraint.name for constraint in UserSignalMonitoring.__table__.constraints}
    action_constraints = {constraint.name for constraint in UserSignalMonitoringAction.__table__.constraints}
    assert "uq_user_signal_monitoring_user_signal" in monitor_constraints
    assert "uq_user_signal_monitoring_action_key" in action_constraints


def test_migration_backfills_proof_only_and_quarantines_stale_free_rows() -> None:
    source = (ROOT / "db/migrations/versions/0030_signal_monitoring_reliability.py").read_text(encoding="utf-8")
    assert "sd.sent_ok IS TRUE" in source
    assert "sd.telegram_chat_id IS NOT NULL" in source
    assert "sd.telegram_message_id IS NOT NULL" in source
    assert "ON CONFLICT (user_id, signal_id) DO NOTHING" in source
    assert "SET status = 'quarantined'" in source
    assert "ux_signals_display_id" in source


def test_shared_resolver_rejects_ambiguous_prefixes_and_supports_message_links() -> None:
    source = (ROOT / "db/signal_reference.py").read_text(encoding="utf-8")
    assert "raise AmbiguousSignalReference" in source
    assert "_TME_LINK" in source and "_TG_LINK" in source
    assert "Signal.display_id == ref" in source
    assert "SignalDelivery.telegram_message_id" in source


def test_callbacks_ack_authorize_and_use_idempotency_ledger() -> None:
    bot = (ROOT / "signalrank_telegram/bot.py").read_text(encoding="utf-8")
    service = (ROOT / "services/user_signal_monitoring.py").read_text(encoding="utf-8")
    assert 'await query.answer("Saving monitoring choice..."' in bot
    assert "require_delivery_proof=True" in bot
    assert 'pattern=r"^sigmon_(?:continue|stop)_[12]_"' in bot
    assert "UserSignalMonitoringAction.idempotency_key == key" in service
    assert "with_for_update()" in service


def test_outboxes_claim_before_io_recover_stale_and_suppress_stopped_users() -> None:
    lifecycle = (ROOT / "engine/signal_lifecycle.py").read_text(encoding="utf-8")
    outcome = (ROOT / "engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert "claim_event_notification" in lifecycle
    assert 'delivery_state="sending"' in lifecycle
    assert "LIFECYCLE_NOTIFICATION_CLAIM_STALE_SECONDS" in lifecycle
    assert "claim_outcome_notification_for_delivery" in outcome
    assert 'row.delivery_state = "suppressed"' in outcome
    assert "monitoring_allows_event" in outcome


def test_user_performance_is_proof_backed_and_counts_stopped_tp_r() -> None:
    source = (ROOT / "db/pg_features.py").read_text(encoding="utf-8")
    block = source[source.index("async def get_user_performance_30d"):source.index("async def get_due_free_signal_summaries")]
    assert "sd.telegram_chat_id IS NOT NULL" in block
    assert "sd.telegram_message_id IS NOT NULL" in block
    assert "usm.realized_r" in block
    assert "d.monitoring_status = 'stopped'" in block
    assert "SUM(net_r)" in block


def test_production_audience_allowlist_is_not_a_normal_recipient_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.delivery_authorization import _restricted_audience

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DELIVERY_AUDIENCE_ALLOWLIST", "1,2,3")
    monkeypatch.setenv("DELIVERY_AUDIENCE_RESTRICTION_MODE", "0")
    assert _restricted_audience() == set()


def test_engine_pulse_has_one_scheduler_owner_and_fail_closed_production_lock() -> None:
    callers = []
    for path in ROOT.rglob("*.py"):
        if "/tests/" in f"/{path.as_posix()}" or path.as_posix().endswith("engine/admin_pulse.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "start_pulse_loop" in text:
            callers.append(path.relative_to(ROOT).as_posix())
    assert callers == ["worker/worker.py"]
    pulse = (ROOT / "engine/admin_pulse.py").read_text(encoding="utf-8")
    assert "ENGINE_PULSE_REQUIRE_DISTRIBUTED_LOCK" in pulse
    assert "return not require_lock" in pulse
    assert "Scope: global" in pulse


def test_current_profiles_expose_all_new_non_secret_controls() -> None:
    expected = {
        "DELIVERY_AUDIENCE_RESTRICTION_MODE",
        "LIFECYCLE_NOTIFICATION_CLAIM_STALE_SECONDS",
        "ENGINE_PULSE_REQUIRE_DISTRIBUTED_LOCK",
    }
    for name in (
        "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example",
        "SignalRankAI_v1.3.2_Railway_Live_Financial_Activation.env.example",
        "SignalRankAI_v1.3.2_Railway_Full_System_Live_Paystack_Staging.env.example",
    ):
        keys = {
            line.split("=", 1)[0]
            for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        }
        assert expected <= keys
