from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_missed_entry_is_never_persisted_as_realized_trade_r() -> None:
    tracker = (ROOT / "engine" / "realtime_outcome_tracker.py").read_text(encoding="utf-8")
    block = tracker[
        tracker.index('if status_l in {"missed_entry", "expired"}:'):
        tracker.index("# Canonical protected-exit accounting")
    ]
    assert "missed_entry_observed_r = r_mult" in block
    assert "missed_entry_observed_pct = pct" in block
    assert "r_mult = None" in block
    assert "pct = None" in block


def test_reconciliation_keeps_missed_entry_excursion_only_as_metadata() -> None:
    source = (ROOT / "services" / "outcome_reconciliation.py").read_text(encoding="utf-8")
    block = source[
        source.index("missed_entry_observed_r = None"):
        source.index("partial = None")
    ]
    assert 'if status_l == "missed_entry"' in block
    assert "missed_entry_observed_r = r_multiple" in block
    assert "r_multiple = None" in block
    assert "percent = None" in block
    assert '"missed_entry_observed_r": missed_entry_observed_r' in source


def test_missed_entry_notification_explicitly_says_no_trade_and_na_r() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    formatter_start = source.index("def _format_non_price_terminal_message")
    formatter = source[
        formatter_start:
        source.index('if status in {"partial_win_be", "partial_win"}', formatter_start)
    ]
    assert "no_trade: bool = False" in formatter
    assert "Trade result: <b>No trade — entry never triggered</b>" in formatter
    assert "Realized R: <b>N/A</b>" in formatter

    missed_start = source.index('elif status in {"missed", "missed_entry"}:')
    missed = source[
        missed_start:
        source.index(
            'elif status in {"invalid", "invalidated", "cancel", "cancelled", "canceled"}:',
            missed_start,
        )
    ]
    assert "no_trade=True" in missed
