from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "requirements"
REQUIRED = {
    "requirements.yaml",
    "decisions.yaml",
    "conflicts.yaml",
    "incidents.yaml",
    "blockers.yaml",
    "feature_flags.yaml",
    "environment_registry.yaml",
    "command_registry.yaml",
    "callback_registry.yaml",
    "provider_registry.yaml",
    "release_gates.yaml",
    "evidence_catalogue.yaml",
    "legacy_disposition.json",
}


def _load(name: str):
    return json.loads((REGISTRY_DIR / name).read_text(encoding="utf-8"))


def test_all_v7_machine_readable_registries_exist_and_parse():
    assert REQUIRED <= {path.name for path in REGISTRY_DIR.iterdir() if path.is_file()}
    for name in REQUIRED:
        payload = _load(name)
        assert payload["schema_version"] == 1
        assert payload["kind"]
        assert payload["generator"] == "scripts/build_v7_governance.py"


def test_v7_prompt_is_materialised_and_hashed_exactly():
    prompt = ROOT / "docs/specs/SIGNALRANKAI_V7_MASTER_BUILD_PROMPT_2026-07-27.md"
    assert prompt.exists()
    digest = hashlib.sha256(prompt.read_bytes()).hexdigest()
    assert digest == "9159ab260d78fe3c4884380104592dd882a20e3a1adc68dce3565c0cd3fef111"
    assert _load("requirements.yaml")["source_prompt"]["sha256"] == digest


def test_command_registry_has_no_active_duplicate_and_records_fail_closed_filter_fallback():
    registry = _load("command_registry.yaml")
    assert registry["count"] >= 140
    assert registry["duplicates"] == []
    names = [item["canonical_name"] for item in registry["commands"]]
    assert len(names) == len(set(names))
    filter_item = next(item for item in registry["commands"] if item["canonical_name"] == "filter")
    assert filter_item["handler"] == "filter_command"
    assert "_filter_unavailable" in filter_item["fallback_handlers"]
    assert filter_item["status"] == "IMPLEMENTED_WITH_FAIL_CLOSED_FALLBACK"


def test_callback_registry_contains_completed_chart_and_gemini_routes():
    registry = _load("callback_registry.yaml")
    patterns = {item["pattern"] for item in registry["callbacks"]}
    assert r"^signal_chart_(.+)$" in patterns
    assert r"^ask_gemini_(.+)$" in patterns
    assert all("placeholder" not in item["status"].lower() for item in registry["callbacks"])


def test_all_dangerous_production_flags_fail_closed():
    flags = [item for item in _load("feature_flags.yaml")["flags"] if item["dangerous"]]
    assert flags
    assert all(item["required_safe_default"] == "0" for item in flags)
    assert all(item["safe_default_satisfied"] is True for item in flags)


def test_provider_registry_distinguishes_implementation_from_live_proof():
    registry = _load("provider_registry.yaml")
    assert registry["count"] >= 20
    assert all(item["certification_status"] == "IMPLEMENTED_NOT_LIVE_VERIFIED" for item in registry["providers"])


def test_legacy_disposition_has_no_unknown_files():
    manifest = _load("legacy_disposition.json")
    assert manifest["file_count"] > 700
    assert "UNKNOWN_REQUIRES_REVIEW" not in manifest["summary"]
    assert all(item["disposition"] != "UNKNOWN_REQUIRES_REVIEW" for item in manifest["files"])


def test_release_gates_do_not_overclaim_live_readiness():
    gates = {item["gate"]: item for item in _load("release_gates.yaml")["gates"]}
    assert gates["D"]["status"] == "BLOCKED_EXTERNAL"
    assert gates["E"]["status"] == "BLOCKED_EXTERNAL"
    assert gates["H"]["status"] == "DISABLED_BY_POLICY"
    assert gates["I"]["status"] == "DISABLED_BY_POLICY"


def test_requirements_have_explicit_disposition_and_rollback():
    payload = _load("requirements.yaml")
    assert payload["requirements"]
    for item in payload["requirements"]:
        assert item["id"].startswith("SRA-")
        assert item["status"] != "UNASSESSED"
        assert item["acceptance_criteria"]
        assert item["rollback_deactivation"]


def test_generated_v7_governance_is_current():
    result = subprocess.run(
        [sys.executable, "scripts/build_v7_governance.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_disposition_is_scoped_to_git_tracked_files():
    source = (ROOT / "scripts" / "build_v7_governance.py").read_text(encoding="utf-8")
    assert '["git", "ls-files", "-z"]' in source
    assert "for relative in sorted(item for item in tracked if item)" in source
