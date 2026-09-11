from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from services.continuous_improvement.recommendation_schema import Recommendation, RecommendationKind
from services.continuous_improvement.refactor_agent import apply_patch_proposal, generate_reviewed_patch


def _load_recommendation(report_path: Path, recommendation_id: str) -> Recommendation:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for item in report.get("recommendations") or []:
        if str(item.get("recommendation_id")) != recommendation_id:
            continue
        return Recommendation(
            recommendation_id=str(item["recommendation_id"]),
            kind=RecommendationKind(str(item["kind"])),
            title=str(item["title"]),
            rationale=str(item["rationale"]),
            evidence=tuple(str(value) for value in item.get("evidence") or []),
            proposed_change=dict(item.get("proposed_change") or {}),
            risk=str(item.get("risk") or "high"),
            provider=str(item.get("provider") or "unknown"),
            acceptance_tests=tuple(str(value) for value in item.get("acceptance_tests") or []),
        )
    raise ValueError(f"recommendation_not_found:{recommendation_id}")


async def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    recommendation = _load_recommendation(Path(args.report), args.recommendation_id)
    if recommendation.kind != RecommendationKind.CODE:
        raise ValueError("only_code_recommendations_can_generate_refactors")
    proposal, decision = await generate_reviewed_patch(root, recommendation)
    result = {
        "recommendation_id": recommendation.recommendation_id,
        "proposal": proposal.as_dict(),
        "decision": decision.as_dict(),
        "applied": False,
        "changed_paths": [],
        "production_mutation": False,
    }
    if args.apply:
        if not decision.approved:
            raise RuntimeError("refactor_not_approved:" + ";".join(decision.reasons))
        result["changed_paths"] = apply_patch_proposal(root, proposal)
        result["applied"] = True
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "approved": decision.approved,
        "applied": result["applied"],
        "changed_paths": result["changed_paths"],
        "artifact": str(output),
        "draft_pr_required": True,
    }, indent=2))
    return 0 if decision.approved else 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a dual-reviewed, bounded SignalRankAI refactor")
    parser.add_argument("--report", required=True)
    parser.add_argument("--recommendation-id", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="artifacts/continuous-improvement/refactor-result.json")
    parser.add_argument("--apply", action="store_true", help="Apply only with CONTINUOUS_REFACTOR_WRITE_ENABLED=1")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
