from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_governance_ignores_runtime_only_output_directories() -> None:
    source = (ROOT / "scripts" / "build_v7_governance.py").read_text(encoding="utf-8")
    assert '".pytest-tmp"' in source
    assert '".diagnostics"' in source
