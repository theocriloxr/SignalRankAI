"""A dedup-suppressed signal is expected behaviour, not a storage error (1 Nov 2026)."""
import logging

import pytest

import db.pg_compat as pg_compat
from db.pg_features import SignalDedupBlocked


def test_dedup_block_is_not_logged_as_error(monkeypatch, caplog):
    def _raise(coro, timeout=None):
        coro.close()
        raise SignalDedupBlocked("min_interval")

    monkeypatch.setattr(pg_compat, "_run", _raise)
    monkeypatch.setattr(pg_compat, "postgres_enabled", lambda: True)
    caplog.set_level(logging.INFO, logger=pg_compat.logger.name)
    with pytest.raises(SignalDedupBlocked):
        pg_compat.store_signal_compat({"asset": "BCHUSDT", "direction": "short", "timeframe": "5m"})
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("dedup_suppressed" in r.getMessage() for r in caplog.records)
