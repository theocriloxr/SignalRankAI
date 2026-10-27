from __future__ import annotations

import pytest

from scripts.semgrep_gate import _validate_report, _validate_probe, _build_command


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


def probe_report():
    return {"results": [
        {"check_id": "python.boto3.security.hardcoded-token.hardcoded-token", "path": "unsafe_sample.py"},
        {"check_id": "python.flask.security.injection.user-eval.eval-injection", "path": "unsafe_sample.py"},
        {"check_id": "javascript.lang.security.detect-eval-with-expression.detect-eval-with-expression", "path": "unsafe_sample.ts"},
    ], "errors": [], "paths": {"scanned": ["unsafe_sample.py", "unsafe_sample.ts", "safe_sample.py"]}}


def test_probe_requires_known_python_and_typescript_detections():
    _validate_probe(probe_report(), 1)


@pytest.mark.parametrize("fault", ["missing_detection", "safe_false_positive", "parse_error", "timeout", "no_scan"])
def test_probe_rejects_analysis_regressions(fault):
    report = probe_report()
    if fault == "missing_detection":
        report["results"].pop()
    elif fault == "safe_false_positive":
        report["results"].append({"check_id": "bad", "path": "safe_sample.py"})
    elif fault == "parse_error":
        report["errors"] = [{"type": "Parse error"}]
    elif fault == "timeout":
        report["time"] = {"fixpoint_timeouts": ["unsafe_sample.py"]}
    else:
        report["paths"] = {"scanned": []}
    with pytest.raises(RuntimeError):
        _validate_probe(report, 1)


@pytest.mark.parametrize("exit_code", [0, 2, 7, -1])
def test_probe_cannot_pass_without_findings_exit_code(exit_code):
    with pytest.raises(RuntimeError):
        _validate_probe(probe_report(), exit_code)


def test_engine_selection_preserves_rules_targets_and_strictness(monkeypatch, tmp_path):
    from scripts import install_opengrep
    monkeypatch.setattr("scripts.semgrep_gate.shutil.which", lambda engine: engine)
    verified = []
    monkeypatch.setattr(install_opengrep, "verify_binary", verified.append)
    semgrep = _build_command(tmp_path / "report.json", ["core", "web"])
    opengrep = _build_command(tmp_path / "report.json", ["core", "web"], "opengrep")
    assert semgrep[1:] == opengrep[1:2] + ["--metrics", "off"] + opengrep[2:]
    assert str(verified[0]) == "opengrep"
    for argument in ["--strict", "--error", "p/default", "p/security-audit", "core", "web"]:
        assert argument in opengrep
