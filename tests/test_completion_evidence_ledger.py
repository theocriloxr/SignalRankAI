from __future__ import annotations

from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parents[1]
RTM = ROOT / "docs" / "architecture" / "REQUIREMENTS_TRACEABILITY_MATRIX.md"
LEDGER = ROOT / "docs" / "architecture" / "COMPLETION_EVIDENCE_LEDGER.md"
CANDIDATE_LEDGER = ROOT / "certification" / "evidence_ledger.yaml"
CURRENT_RELEASE = ROOT / "CURRENT_RELEASE.md"

_ALLOWED = {
    "IMPLEMENTED",
    "VERIFIED",
    "BLOCKED_EXTERNAL",
    "DEFERRED_WITH_REASON",
    "NOT_APPLICABLE",
}


def _rows(path: Path) -> list[list[str]]:
    result: list[list[str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.startswith("| SR-"):
            continue
        parts = [part.strip() for part in raw.split("|")[1:-1]]
        result.append(parts)
    return result


def test_every_traceability_requirement_has_exactly_one_completion_ledger_row() -> None:
    rtm_rows = _rows(RTM)
    ledger_rows = _rows(LEDGER)
    rtm_ids = [row[0] for row in rtm_rows]
    ledger_ids = [row[0] for row in ledger_rows]
    assert len(rtm_ids) == len(set(rtm_ids)), "duplicate requirement ID in traceability matrix"
    assert len(ledger_ids) == len(set(ledger_ids)), "duplicate requirement ID in completion ledger"
    assert set(ledger_ids) == set(rtm_ids)


def test_completion_ledger_uses_only_allowed_status_vocabulary() -> None:
    rows = _rows(LEDGER)
    assert rows
    statuses = {row[1] for row in rows}
    assert statuses.issubset(_ALLOWED)
    assert not {"MOSTLY_COMPLETE", "PARTIAL", "SHOULD_WORK", "PENDING", "TODO"}.intersection(statuses)


def test_verified_rows_keep_traceability_verification_level() -> None:
    rtm = {row[0]: row for row in _rows(RTM)}
    ledger = {row[0]: row for row in _rows(LEDGER)}
    for req_id, ledger_row in ledger.items():
        if ledger_row[1] != "VERIFIED":
            continue
        source_status = rtm[req_id][2]
        assert source_status in {"UNIT_VERIFIED", "INTEGRATION_VERIFIED"}
        verification_level = ledger_row[2]
        if source_status == "INTEGRATION_VERIFIED":
            assert verification_level == "STAGING / INTEGRATION"
        else:
            assert verification_level == "REPOSITORY / UNIT-CONTRACT"


def test_blocked_external_rows_are_explicitly_fail_closed() -> None:
    ledger_text = LEDGER.read_text(encoding="utf-8")
    rows = [row for row in _rows(LEDGER) if row[1] == "BLOCKED_EXTERNAL"]
    assert rows, "expected at least one externally blocked scope"
    assert "intentionally fail-closed" in ledger_text
    assert "does **not** activate" in ledger_text
    blocked_ids = {row[0] for row in rows}
    assert blocked_ids == {
        "SR-PROVIDER-008",
        "SR-SCALE-003",
        "SR-MARKETPLACE-001",
        "SR-DEMO-010",
    }


def test_current_release_candidate_uses_truthful_machine_readable_statuses() -> None:
    candidate = json.loads(CANDIDATE_LEDGER.read_text(encoding="utf-8"))
    entries = {row["id"]: row for row in candidate["entries"]}
    release = CURRENT_RELEASE.read_text(encoding="utf-8")

    assert "Repository Alembic head: 0051_strategy_health_baselines" in release
    assert "NOT YET LIVE-CERTIFIED" in release
    assert entries["SR-LIVE-001"]["status"] == "FAILED"
    assert entries["SR-SOAK-001"]["status"] == "PARTIAL"
    assert entries["SR-STORAGE-001"]["status"] == "FAILED"
    assert entries["SR-GITHUB-001"]["status"] == "IMPLEMENTED_UNVERIFIED"
    assert entries["SR-CI-BILLING-001"]["status"] == "BLOCKED_EXTERNAL"
    assert entries["SR-JS-SECURITY-001"]["status"] == "FAILED"
    assert set(candidate["statuses"]) >= {
        "IMPLEMENTED_VERIFIED",
        "IMPLEMENTED_UNVERIFIED",
        "PARTIAL",
        "BLOCKED_EXTERNAL",
        "FAILED",
    }

