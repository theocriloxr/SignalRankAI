from pathlib import Path

from scripts.validate_governance_docs import REQUIRED_DOCS, validate_governance_docs


ROOT = Path(__file__).resolve().parents[1]


def test_required_governance_documents_are_present_and_valid():
    assert validate_governance_docs(ROOT) == []


def test_governance_index_links_every_required_document():
    index = (ROOT / "docs" / "GOVERNANCE_INDEX.md").read_text(encoding="utf-8")

    for rel_path in REQUIRED_DOCS:
        if rel_path == "docs/GOVERNANCE_INDEX.md":
            continue
        assert rel_path in index


def test_technical_debt_register_uses_phase16_schema():
    text = (ROOT / "docs" / "LIVING_TECHNICAL_DEBT_REGISTER.md").read_text(encoding="utf-8").lower()

    for field in (
        "root cause",
        "likelihood",
        "dependencies",
        "regression risk",
        "verification evidence",
        "owner",
    ):
        assert field in text
