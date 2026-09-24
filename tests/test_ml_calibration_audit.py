from pathlib import Path

from scripts.ml_calibration_audit import ML_PAST_SQL, REJECTED_SQL, PAPER_SQL, UNIQUE_IDS_SQL


def test_calibration_audit_queries_are_quoted_and_read_only() -> None:
    source = Path("scripts/ml_calibration_audit.py").read_text(encoding="utf-8")
    assert 'SET TRANSACTION READ ONLY' in source
    assert "await session.rollback()" in source
    assert "session.commit" not in source
    assert "COALESCE(outcome_status, '')" in str(ML_PAST_SQL)
    assert "COALESCE(actual_outcome, '')" in str(REJECTED_SQL)
    assert "COALESCE(actual_outcome, '')" in str(UNIQUE_IDS_SQL)
    assert "FROM paper_positions" in str(PAPER_SQL)
    assert "COALESCE(outcome_status,)" not in source
    assert "WHEOERE" not in source


def test_calibration_audit_uses_bounded_parameterized_lookback() -> None:
    source = Path("scripts/ml_calibration_audit.py").read_text(encoding="utf-8")
    assert "make_interval(days => :days)" in source
    assert "days = max(1, min(3650, int(days)))" in source
    assert 'priority="analytics"' in source
    assert 'drop_if_busy=False' in source
