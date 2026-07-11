"""Validate required living governance documents.

Run from the repository root:

    python scripts/validate_governance_docs.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS: Dict[str, List[str]] = {
    "docs/GOVERNANCE_INDEX.md": ["# Engineering Governance Index", "Living Registers", "Definition Of Done"],
    "docs/LIVING_TECHNICAL_DEBT_REGISTER.md": ["# Living Technical Debt Register", "## Schema", "LTD-"],
    "docs/LIVING_FEATURE_REGISTER.md": ["# Living Feature Register", "Feature", "Known Limitations"],
    "docs/LIVING_BUG_REGISTER.md": ["# Living Bug Register", "Root Cause", "Regression Prevention"],
    "docs/LIVING_IMPROVEMENT_REGISTER.md": ["# Living Improvement Register", "Opportunity", "Priority"],
    "docs/LIVING_RISK_REGISTER.md": ["# Living Risk Register", "Probability", "Contingency Plan"],
    "docs/LIVING_ADR.md": ["# Living Architecture Decision Record", "Problem", "Decision"],
    "docs/LIVING_TESTING_REGISTER.md": ["# Living Testing Register", "Missing Coverage", "Commands"],
    "docs/LIVING_PERFORMANCE_REGISTER.md": ["# Living Performance Register", "Metric", "Target"],
    "docs/LIVING_AI_ML_REGISTER.md": ["# Living AI And ML Register", "Calibration/Drift", "Prompt/Model Version"],
    "docs/LIVING_UX_REGISTER.md": ["# Living User Experience Register", "Clarity", "Professionalism"],
    "docs/LIVING_TRADING_INTELLIGENCE_REGISTER.md": ["# Living Trading Intelligence Register", "Reason", "Planned Improvements"],
    "docs/LIVING_DEPLOYMENT_REGISTER.md": ["# Living Deployment Register", "Rollback", "Health Checks"],
    "docs/SHADOW_INTELLIGENCE_GOVERNANCE.md": ["# Shadow Intelligence Governance", "Promotion Gate", "Required Capabilities"],
    "docs/KNOWLEDGE_GRAPH.md": ["# Knowledge Graph", "Core Graph", "Test Mapping"],
    "docs/PRODUCTION_READINESS_SCORECARD.md": ["# Production Readiness Scorecard", "Overall Assessment", "Highest-Impact Next Actions"],
    "docs/PRODUCTION_LAUNCH_RUNBOOK.md": ["# Production Launch Runbook", "Pre-Launch Gates", "Rollback"],
}


def validate_governance_docs(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for rel_path, required_markers in REQUIRED_DOCS.items():
        path = root / rel_path
        if not path.exists():
            errors.append(f"missing:{rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        if len(text.strip()) < 100:
            errors.append(f"too_short:{rel_path}")
        for marker in required_markers:
            if marker not in text:
                errors.append(f"missing_marker:{rel_path}:{marker}")
    return errors


def main() -> int:
    errors = validate_governance_docs()
    if errors:
        print("Governance validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Governance validation passed: {len(REQUIRED_DOCS)} documents checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
