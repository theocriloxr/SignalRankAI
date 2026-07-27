from pathlib import Path


def test_engine_source_critical_fallbacks_fail_closed():
    source = Path("engine/core.py").read_text(encoding="utf-8")
    assert "return False, ['advanced_filter_unavailable']" in source
    assert "return False, 'ultra_quality_unavailable', 0" in source
    assert "return False, 'cooldown_manager_unavailable'" in source
    assert "return False, 'mtf_validator_unavailable'" in source
    assert 'PORTFOLIO_EXPOSURE_FAIL_CLOSED", True' in source
    assert 'MARKET_CIRCUIT_BREAKER_FAIL_CLOSED", True' in source


def test_signal_lock_failure_is_treated_as_locked():
    source = Path("engine/core.py").read_text(encoding="utf-8")
    assert "compatibility wrapper failed closed" in source
    assert "return True" in source[source.index("def _check_signal_lock"):source.index("def _release_signal_lock")]
