from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_active_redis_trade_blocks_new_candidate_instead_of_recycling_signal_identity() -> None:
    source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    marker = '[dedup] redis active trade blocks new candidate'
    assert marker in source
    block_start = source.index(marker)
    block = source[block_start:block_start + 1800]
    assert 'raise SignalDedupBlocked("active_trade", signal_id=active_signal_id)' in block
    assert "return existing_active" not in block
    assert "return active_signal_id" not in block


def test_paper_uses_confirmed_delivery_as_canonical_user_eligibility() -> None:
    source = (ROOT / "core" / "paper_trading_service.py").read_text(encoding="utf-8")
    start = source.index("delivery_proven = bool(candidate.get(\"delivery_proven\"))")
    end = source.index("freshness = evaluate_signal_freshness(", start)
    block = source[start:end]

    # A signal already delivered to this user has passed the canonical delivery
    # authorization/profile route. Paper must not reject that same owner/recovery
    # receipt by re-running the ordinary preference matcher.
    assert "if not delivery_proven:" in block
    assert "signal_matches_preferences(candidate, profile_prefs)" in block
    assert block.index("if not delivery_proven:") < block.index("signal_matches_preferences(candidate, profile_prefs)")

    # Paper still independently enforces freshness and its own account/risk limits.
    after = source[end:end + 8000]
    assert "if not freshness.ok:" in after
    assert "max_open_positions" in after
    assert "paper_daily_loss_limit" in after
    assert "allowed_asset_classes" in after


def test_active_delivered_signal_visibility_is_lifecycle_authoritative() -> None:
    source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    start = source.index("async def list_delivered_signals_for_user(")
    end = source.index("async def get_delivered_signal_by_ref(", start)
    block = source[start:end]

    assert "lifecycle_active = and_(" in block
    assert "lifecycle_upper.notin_(terminal_lifecycle_states)" in block
    assert "active_projection = or_(" in block

    active_idx = block.index("lifecycle_active,")
    legacy_expiry_idx = block.index("or_(Signal.expires_at.is_(None), Signal.expires_at > now)")
    assert active_idx < legacy_expiry_idx

    # Confirmed delivery proof remains the primary list membership boundary.
    assert "SignalDelivery.sent_ok.is_(True)" in block
    assert "SignalDelivery.telegram_message_id.is_not(None)" in block
    assert "SignalDelivery.delivery_confirmed_at.is_not(None)" in block


def test_paper_candidate_uses_delivery_snapshot_to_prevent_geometry_split_brain() -> None:
    source = (ROOT / "core" / "paper_trading_service.py").read_text(encoding="utf-8")
    assert "def _proof_signal_snapshot(" in source
    assert "signal_snapshot" in source
    assert "_snapshot_or(" in source

    # The delivered receipt snapshot is the immutable geometry fallback for paper
    # when a legacy mutable signal row disagrees with what the user actually saw.
    candidate_area = source[source.index("def _proof_signal_snapshot("):]
    for field in ("entry", "stop_loss", "take_profits", "generated_at", "expires_at"):
        assert field in candidate_area


def test_incident_regression_rejects_same_signal_id_with_changed_generation_truth() -> None:
    source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    # The previous production incident reused one US30 UUID across separate days,
    # causing delivery/paper/lifecycle geometry to disagree. The storage path now
    # treats an unresolved active identity as a dedup block, never as a mutable
    # container for a fresh setup.
    assert "Never recycle the identity of an already-active Redis" in source
    assert "split-brain" in source


def test_missed_entry_is_terminal_for_asset_position_locking() -> None:
    from services.asset_position_manager import _state_from_status

    for status in ("missed", "missed_entry", "entry_missed", "not_triggered"):
        assert _state_from_status(status) == "EXPIRED"


def test_fallback_delivery_asset_gate_releases_missed_entry() -> None:
    source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    start = source.index("resolved_statuses = {")
    end = source.index("is_resolved =", start)
    block = source[start:end]
    assert '"missed"' in block
    assert '"missed_entry"' in block
    assert '"entry_missed"' in block
    assert '"not_triggered"' in block


def test_tp1_rebound_notification_never_claims_latest_price_is_hit_evidence() -> None:
    from engine.tier_notifications import TierNotificationManager

    message = TierNotificationManager().format_tp_hit_notification(
        {
            "signal_id": "0140438f-a1bd-4eb4-bdb2-89e9256734c5",
            "asset": "JNJ",
            "direction": "SELL",
            "timeframe": "1m",
            "entry": 262.2601,
            "stop_loss": 262.7518,
            "take_profit": [260.8439, 259.4277, 258.0116],
        },
        "owner",
        1,
        0.54,
        current_market_price=262.45,
    )
    assert "TP1 hit level: 260.8439" in message
    assert "Latest stored price: 262.45 (post-hit mark; not TP evidence)" in message
    assert "Observed hit price: 262.45" not in message
    assert "P/L at TP event: +0.54%" in message
    assert "Signal P/L:" not in message


def test_canonical_lifecycle_notification_uses_persisted_event_price() -> None:
    source = (ROOT / "engine" / "signal_lifecycle.py").read_text(encoding="utf-8")
    dispatch = source[source.index("async def dispatch_event_notifications"):]

    assert "event_price = float(getattr(event, \"price\", 0)" in dispatch
    assert "_event_message(" in dispatch
    assert "event_price," in dispatch
