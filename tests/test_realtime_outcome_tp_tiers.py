import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.realtime_outcome_tracker import _build_outcome_message


def test_free_tp_message_contains_suggested_sl_guidance() -> None:
    msg = _build_outcome_message(
        signal_id="abcd1234efgh5678",
        asset="BTCUSDT",
        direction="LONG",
        entry=100.0,
        price=105.0,
        status="tp1",
        pnl_pct=5.0,
        tier_at_send="free",
    )
    assert "TP1" in msg.upper()
    assert "Suggested SL" in msg
    assert "break-even" in msg.lower()


def test_premium_tp2_message_contains_lock_gains_suggestion() -> None:
    msg = _build_outcome_message(
        signal_id="abcd1234efgh5678",
        asset="BTCUSDT",
        direction="LONG",
        entry=100.0,
        price=110.0,
        status="tp2",
        pnl_pct=10.0,
        tier_at_send="premium",
    )
    assert "TP2" in msg.upper()
    assert "Suggested SL" in msg
    assert "lock gains" in msg.lower()


def test_vip_tp3_message_contains_trail_tight_suggestion() -> None:
    msg = _build_outcome_message(
        signal_id="abcd1234efgh5678",
        asset="BTCUSDT",
        direction="LONG",
        entry=100.0,
        price=120.0,
        status="tp3",
        pnl_pct=20.0,
        tier_at_send="vip",
    )
    assert "TP3" in msg.upper()
    assert "Suggested SL" in msg
    assert "trail tight" in msg.lower()
