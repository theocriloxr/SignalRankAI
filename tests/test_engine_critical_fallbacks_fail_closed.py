from pathlib import Path
import ast


def test_engine_source_critical_fallbacks_fail_closed():
    source = Path("engine/core.py").read_text(encoding="utf-8")
    assert "return False, ['advanced_filter_unavailable']" in source
    tree = ast.parse(source)
    stub = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "_UltraStub")
    returns = [node.value for node in ast.walk(stub) if isinstance(node, ast.Return)]
    assert any(ast.literal_eval(value) == (False, "ultra_quality_unavailable", 0) for value in returns)
    literal_returns = [
        ast.literal_eval(node.value) for node in ast.walk(tree)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)
        and all(isinstance(item, ast.Constant) for item in node.value.elts)
    ]
    assert (False, "cooldown_manager_unavailable") in literal_returns
    assert (False, "mtf_validator_unavailable") in literal_returns
    assert 'PORTFOLIO_EXPOSURE_FAIL_CLOSED", True' in source
    assert 'MARKET_CIRCUIT_BREAKER_FAIL_CLOSED", True' in source


def test_signal_lock_failure_is_treated_as_locked():
    source = Path("engine/core.py").read_text(encoding="utf-8")
    assert "compatibility wrapper failed closed" in source
    assert "return True" in source[source.index("def _check_signal_lock"):source.index("def _release_signal_lock")]
