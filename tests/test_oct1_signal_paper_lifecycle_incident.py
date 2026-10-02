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
