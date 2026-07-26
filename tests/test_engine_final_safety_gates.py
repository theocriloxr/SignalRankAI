from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "engine" / "core.py").read_text(encoding="utf-8")


def test_final_kill_switch_errors_block_candidate_batch():
    source = _source()
    block = source.split("# Global kill-switch gate:", 1)[1].split("# ── Batch DB cooldown check", 1)[0]
    assert "kill-switch final gate unavailable; blocking candidate batch" in block
    assert 'pipeline_stats["skipped_kill_switch_error"]' in block
    assert "continue" in block


def test_cooldown_preflight_defaults_fail_closed():
    source = _source()
    block = source.split("batch cooldown pre-check failed", 1)[1].split("stored_signals:", 1)[0]
    assert 'COOLDOWN_PREFLIGHT_FAIL_OPEN", False' in block
    assert 'skipped_cooldown_preflight_error' in block
    assert "continue" in block


def test_active_trade_state_failure_blocks_candidate():
    source = _source()
    block = source.split("duplicate trade check failed; blocking candidate", 1)[1].split("# ── Portfolio Exposure", 1)[0]
    assert "active_trade_state_unavailable" in block
    assert "continue" in block


def test_delivery_dedupe_failure_blocks_batch_instead_of_sending_everything():
    source = _source()
    block = source.split("async def filter_non_duplicate_signals", 1)[1].split("async def deliver_all", 1)[0]
    assert "duplicate evidence unavailable" in block
    assert "return []" in block
    assert "better to send duplicates" not in block
