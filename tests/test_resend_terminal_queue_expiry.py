from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")


def test_queue_expiry_is_persisted_as_delivery_terminal_runtime_state() -> None:
    source = _source()
    assert 'delivery_terminal_signal_ids: set[str] = set()' in source
    assert '_resend_terminal_prefix = "resend_terminal:"' in source
    assert 'RuntimeState.key.in_(_resend_terminal_keys)' in source
    assert 'RuntimeState.expires_at > _resend_now_utc_naive()' in source
    assert '"[resend] suppressed delivery-terminal signals=%s"' in source

    queue_block = source[
        source.index("queue_result = evaluate_time_to_telegraph(payload)"):
        source.index("fresh_ranked.append(signal_row)"),
    ]
    assert '"state": "EXPIRED_IN_QUEUE"' in queue_block
    assert '"source": "telegram_resend_freshness"' in queue_block
    assert '_pg_insert(_RuntimeState.__table__)' in queue_block
    assert '.on_conflict_do_update(' in queue_block
    assert 'RESEND_TERMINAL_TTL_SECONDS' in queue_block


def test_queue_expiry_does_not_mutate_analytical_signal_or_lifecycle() -> None:
    source = _source()
    queue_block = source[
        source.index("queue_result = evaluate_time_to_telegraph(payload)"):
        source.index("fresh_ranked.append(signal_row)"),
    ]

    assert "expire_signal" not in queue_block
    assert "SignalLifecycle" not in queue_block
    assert ".status =" not in queue_block
    assert "monitoring/outcome tracking remains intact" in queue_block


def test_queue_expiry_remains_fail_closed_if_marker_persistence_fails() -> None:
    source = _source()
    queue_block = source[
        source.index("queue_result = evaluate_time_to_telegraph(payload)"):
        source.index("fresh_ranked.append(signal_row)"),
    ]
    assert "delivery-terminal marker persist failed" in queue_block
    # The signal is still skipped for the current run even when the
    # housekeeping persistence write fails.
    assert queue_block.rstrip().endswith("continue")
