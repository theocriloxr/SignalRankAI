"""Production /readyz reported `health_probe_failed:ValueError` on 2026-10-24.

Root cause: the probe parsed an absent `engine:last_cycle` heartbeat with
`datetime.fromisoformat("")`. The real condition — no engine cycle has run —
must be reported as such, with an operator action, not as a parser crash.
"""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "railway_main.py").read_text(encoding="utf-8")


def _probe_block() -> str:
    start = SOURCE.index('raw_cycle = state.get_sync("engine:last_cycle")')
    return SOURCE[start:SOURCE.index("# Admin pulse stays visible", start)]


def test_missing_heartbeat_is_reported_explicitly_not_as_a_parse_error():
    block = _probe_block()
    assert "if not stamp_raw:" in block
    assert block.index("if not stamp_raw:") < block.index("datetime.fromisoformat(")
    assert '"engine_heartbeat_missing"' in block and '"engine_heartbeat_unstamped"' in block
    assert "except _EngineHeartbeatMissing as missing:" in block
    assert '"action":' in block
    assert "class _EngineHeartbeatMissing(Exception):" in SOURCE


def test_probe_decodes_bytes_and_rejects_non_object_payloads():
    block = _probe_block()
    assert "raw_cycle.decode(" in block
    assert "if not isinstance(cycle, dict):" in block


def test_probe_still_fails_closed_for_unexpected_errors():
    block = _probe_block()
    assert 'f"health_probe_failed:{type(exc).__name__}"' in block
    assert block.count('"ok": False') >= 2
