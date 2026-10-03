from __future__ import annotations

import pytest

from scripts.semgrep_gate import _validate_report


def test_semgrep_gate_accepts_complete_zero_finding_report() -> None:
    report = {
        "results": [],
        "errors": [],
        "paths": {"scanned": [f"file-{index}.py" for index in range(480)]},
    }
    assert _validate_report(report, minimum_scanned=400) == {
        "findings": 0,
        "errors": 0,
        "scanned": 480,
    }


def test_semgrep_gate_rejects_findings() -> None:
    report = {
        "results": [{"check_id": "rule", "path": "web/app.py", "start": {"line": 1}}],
        "errors": [],
        "paths": {"scanned": [f"file-{index}.py" for index in range(480)]},
    }
    with pytest.raises(RuntimeError, match="semgrep_findings"):
        _validate_report(report, minimum_scanned=400)


def test_semgrep_gate_rejects_scan_errors() -> None:
    report = {
        "results": [],
        "errors": [{"type": "Parse error", "path": "broken.py"}],
        "paths": {"scanned": [f"file-{index}.py" for index in range(480)]},
    }
    with pytest.raises(RuntimeError, match="semgrep_scan_errors"):
        _validate_report(report, minimum_scanned=400)


def test_semgrep_gate_rejects_implausibly_small_scan_surface() -> None:
    report = {"results": [], "errors": [], "paths": {"scanned": ["one.py"]}}
    with pytest.raises(RuntimeError, match="semgrep_scan_surface_too_small"):
        _validate_report(report, minimum_scanned=400)


def test_semgrep_gate_rejects_incomplete_taint_analysis() -> None:
    report = {"results": [], "errors": [], "paths": {"scanned": ["one.py"]},
              "time": {"fixpoint_timeouts": [{"path": "one.py"}]}}
    with pytest.raises(RuntimeError, match="incomplete_taint_analysis"):
        _validate_report(report, minimum_scanned=1)


@pytest.mark.parametrize("exit_code", [1, 2, 3, 7, -1])
def test_semgrep_gate_never_converts_tool_failure_into_pass(exit_code: int) -> None:
    report = {"results": [], "errors": [], "paths": {"scanned": ["one.py"]}}
    with pytest.raises(RuntimeError, match="nonzero_exit"):
        _validate_report(report, minimum_scanned=1, raw_exit=exit_code)
