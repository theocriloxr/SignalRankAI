"""Rebuild the source-index portion of the September blueprint evidence ledger.

This is a requirements/documentation utility, not an implementation certification.
Source sections and fragments are retained verbatim. Existing manually supplied
evidence/status fields survive regeneration; lexical domain suggestions do not
prove coverage. Run from the repository root with Python 3.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "requirements/blueprint_requirements.json"
SPECS = "docs/specs/2026-09-25/"
SOURCES = [
    ("BP", "Master Blueprint (DOCX transcription)", "docs/SignalRank_Master_Blueprint_2026.md"),
    ("ROAD", "Platform improvement roadmap", SPECS + "01-platform-roadmap.txt"),
    ("HAND", "Historical staging handoff", SPECS + "02-historical-staging-handoff.txt"),
    ("MASTER", "Master implementation directive", SPECS + "03-master-implementation-directive.txt"),
    ("MULTI", "Multi-user and multi-account addendum", SPECS + "04-multi-user-account-addendum.txt"),
    ("HARD", "Final hardening directive", SPECS + "05-final-hardening-directive.txt"),
]
MASTER_HEADINGS = {
    "WORKING BRANCH", "PRIMARY SPECIFICATION", "OBJECTIVE", "PRE-IMPLEMENTATION AUDIT",
    "TRACEABILITY", "CORE ENGINEERING RULES", "MULTI-ASSET REQUIREMENT", "SIGNAL PIPELINE",
    "LEARNING SYSTEM", "EXECUTION SAFETY", "PAPER, DEMO, PROP AND LIVE", "WEB AND TELEGRAM",
    "OPENAI AND GEMINI", "OBSERVABILITY", "SECURITY", "TESTING", "FINANCIAL CORRECTNESS",
    "PROVENANCE", "CERTIFICATION", "WORKING STYLE", "FINAL DEFINITION OF DONE",
}
MULTI_HEADINGS = {
    "MULTI-USER PLATFORM", "TENANT AND USER ISOLATION", "MULTIPLE BROKER ACCOUNTS PER USER",
    "NORMAL LIVE ACCOUNT + PROP ACCOUNT", "ACCOUNT MODES", "MULTIPLE PROP ACCOUNTS",
    "PROP RULE ENGINE", "OWNER ACCOUNT IS NOT SPECIAL INSIDE EXECUTION",
    "PER-ACCOUNT EXECUTION SETTINGS", "ACCOUNT SELECTION", "MULTI-USER SIGNAL DELIVERY",
    "SCALE", "SUBSCRIPTIONS AND ENTITLEMENTS", "SIGNAL HISTORY", "PERFORMANCE ANALYTICS",
    "PER-ACCOUNT TRADE LEDGER", "REQUIREMENTS TRACEABILITY MATRIX", "COMPLETION EVIDENCE LEDGER",
    "DIVERGENT BRANCH RECONCILIATION", "ENVIRONMENT ISOLATION", "LLM ISOLATION FROM EXECUTION",
    "FINANCIAL ARITHMETIC", "COMPLETE DECISION SNAPSHOT", "DETERMINISTIC TRADE REPLAY",
    "CANARY EXECUTION ACCOUNT", "EXECUTION DISCREPANCY INVARIANT", "IMMUTABLE HARD RISK CEILINGS",
    "STRATEGY/MODEL PROMOTION GOVERNANCE", "SURVIVORSHIP AND LEAKAGE TEST SUITE", "COST-AWARE EDGE",
    "DISASTER-STATE TESTING", "SUPPLY-CHAIN SECURITY", "EVIDENCE-BASED CERTIFICATION",
    "DEMO-TO-LIVE GATES", "FINAL ACCOUNT SAFETY PRINCIPLE",
}

# These are navigation anchors inspected in the current repository. A section
# can span many domains; this deliberately does not assert complete coverage.
DOMAINS = {
    "account": {
        "modules": ["db/models.py", "services/broker_connections.py", "services/platform/identity.py", "execution/service.py"],
        "tests": ["tests/test_unified_platform_identity.py", "tests/test_canonical_broker_entrypoints.py"],
        "migrations": ["db/migrations/versions/0036_unified_platform_identity.py", "db/migrations/versions/0041_broker_connection_registry.py"],
        "legacy": ["SR-BROKER-001", "SR-SEC-001"],
    },
    "execution": {
        "modules": ["execution/service.py", "services/mt5_signal_router.py", "services/bybit_signal_router.py", "services/bybit_reconciler.py"],
        "tests": ["tests/test_broker_execution_p0.py", "tests/test_execution_safety.py", "tests/test_tiered_execution_canonical_routing.py"],
        "migrations": ["db/migrations/versions/0041_broker_connection_registry.py"],
        "legacy": ["SR-BROKER-001", "SR-BROKER-002", "SR-RISK-001"],
    },
    "risk": {
        "modules": ["core/risk_authority.py", "engine/risk_sizer.py", "core/financial_activation.py", "execution/service.py"],
        "tests": ["tests/test_v20_risk_authority.py", "tests/test_risk_dynamic.py", "tests/test_broker_execution_p0.py"],
        "migrations": [], "legacy": ["SR-RISK-001"],
    },
    "market_data": {
        "modules": ["data/provider_catalog.py", "data/market_data.py", "data/fetcher_router.py", "data/canonical_instruments.py", "data/market_hours.py", "core/asset_registry.py"],
        "tests": ["tests/test_market_data_quality_firewall.py", "tests/test_provider_and_asset_registry_hardening.py", "tests/test_v21_multi_asset_expansion.py"],
        "migrations": [], "legacy": ["SR-ASSET-001", "SR-PROV-001", "SR-PROV-002"],
    },
    "research": {
        "modules": ["ml/model_registry.py", "ml/signal_calibrator.py", "engine/adaptive/dataset.py", "engine/adaptive/walk_forward.py", "engine/adaptive/promotion.py", "services/continuous_improvement/promotion_gate.py"],
        "tests": ["tests/test_ml_registry.py", "tests/test_adaptive_dataset_and_wfo.py", "tests/test_ml_calibration_audit.py"],
        "migrations": ["db/migrations/versions/0025_adaptive_strategy.py"],
        "legacy": ["SR-ML-001", "SR-ML-002", "SR-CI-003"],
    },
    "strategy": {
        "modules": ["engine/strategy_orchestrator.py", "engine/strategy_selector.py", "engine/regime.py", "engine/backtest.py", "ml/features.py"],
        "tests": ["tests/test_adaptive_dataset_and_wfo.py", "tests/test_ml_feature_contract.py"],
        "migrations": ["db/migrations/versions/0025_adaptive_strategy.py"], "legacy": ["SR-STRAT-001"],
    },
    "signals": {
        "modules": ["core/signal_lifecycle.py", "engine/signal_lifecycle.py", "services/decision_intelligence.py", "engine/realtime_outcome_tracker.py", "services/platform/signal_delivery.py"],
        "tests": ["tests/test_signal_visibility_and_proof_quality.py", "tests/test_phase4_pass4_outcome_tracker_redesign.py"],
        "migrations": ["db/migrations/versions/0018_signal_lifecycle_events.py", "db/migrations/versions/0040_cross_channel_paper_receipts.py"],
        "legacy": ["SR-SIG-001", "SR-OUT-001", "SR-DEL-001"],
    },
    "paper": {
        "modules": ["core/paper_trading_service.py", "core/paper_ledger.py", "core/paper_sizing.py", "engine/shadow_outcome_worker.py"],
        "tests": ["tests/test_realistic_paper_execution.py", "tests/test_phase12_performance_paper_reliability.py"],
        "migrations": ["db/migrations/versions/0031_performance_paper_reliability.py", "db/migrations/versions/0040_cross_channel_paper_receipts.py"],
        "legacy": ["SR-SIG-001", "SR-OUT-001"],
    },
    "ai": {
        "modules": ["services/ai_review_router.py", "services/openai_ai.py", "services/gemini_ml.py", "services/continuous_improvement/promotion_gate.py"],
        "tests": ["tests/test_openai_ai_provider.py"], "migrations": [], "legacy": ["SR-CI-002", "SR-CI-003"],
    },
    "security": {
        "modules": ["core/security.py", "services/security.py", "services/platform/identity.py", "web/platform_api.py"],
        "tests": ["tests/test_phase4_pass6_security_api_payments.py", "tests/test_unified_platform_identity.py"],
        "migrations": ["db/migrations/versions/0019_user_timezone_privacy.py", "db/migrations/versions/0038_account_security_product_completion.py"],
        "legacy": ["SR-SEC-001"],
    },
    "billing": {
        "modules": ["core/tier_policy.py", "services/tier_policy.py", "services/platform/email_delivery.py", "web/platform_api.py"],
        "tests": ["tests/test_unified_canonical_billing_v151.py"], "migrations": [], "legacy": ["SR-PAY-001", "SR-TIER-001"],
    },
    "product": {
        "modules": ["web/platform_api.py", "web/app.py", "signalrank_telegram/bot.py", "services/trade_profiles.py", "services/platform/webhooks.py"],
        "tests": ["tests/test_callback_feature_completion.py", "tests/test_unified_platform_completion_v150.py", "tests/test_unified_platform_webhooks.py"],
        "migrations": [], "legacy": ["SR-TG-001", "SR-PROF-001"],
    },
    "database": {
        "modules": ["db/models.py", "db/session.py", "db/priority.py", "core/redis_state.py"],
        "tests": ["tests/test_db_session_labels.py", "tests/test_phase4_pass2_db_priority_and_command_speed.py"],
        "migrations": [], "legacy": ["SR-DB-001", "SR-REDIS-001", "SRA-DB-001"],
    },
    "operations": {
        "modules": ["core/slo_registry.py", "core/telemetry.py", "core/resource_governor.py", "core/job_leases.py", "services/dead_letter_queue.py"],
        "tests": ["tests/test_v20_slo_registry.py", "tests/test_delivery_fanout_planner.py", "tests/test_telemetry.py"],
        "migrations": [], "legacy": ["SR-OBS-001", "SR-DEL-003"],
    },
    "release": {
        "modules": ["tools/staging_certification.py", "core/release_guard.py", "scripts/assert_release_source.py", "scripts/schema_audit.py"],
        "tests": ["tests/test_release_source_and_domain_bridge.py", "tests/test_staged_release_contracts.py"],
        "migrations": [], "legacy": ["SR-REL-001", "SR-TEST-001", "SRA-CI-001"],
    },
    "governance": {
        "modules": [], "tests": [], "migrations": [], "legacy": ["SRA-GOV-001"],
    },
}

PATTERNS = [
    ("account", r"multi.user|multi.account|multiple.*account|account (mode|selection|recovery|safety)|ownership|tenant|identity|normal live account|prop"),
    ("execution", r"execution|broker|order|partial.fill|oco|reconcil|manual action|position ownership|precision"),
    ("risk", r"risk|kill switch|portfolio|sizing|currency|drawdown|heat|loss buffer|hard.*ceiling"),
    ("market_data", r"asset|market.data|provider|symbol|freshness|calendar|session|corporate action|futures|data quality|liquidity|halt|news event clock|divergence"),
    ("research", r"model|learning|calibrat|counterfactual|walk.forward|drift|experiment|research|statistic|confidence|leakage|dataset|survivorship|overfitting"),
    ("strategy", r"strategy|ensemble|regime|feature engineering|backtest|monte carlo|scenario|expected value|cost.aware"),
    ("paper", r"paper|shadow"),
    ("ai", r"\bai\b|\bllm\b|openai|gemini|hallucination|sentiment|natural.language|copilot"),
    ("security", r"security|auth|consent|privacy|pii|legal|licens|secret|credential|sanitiz|abuse|permission|deletion|supply.chain|software bill"),
    ("billing", r"billing|entitle|subscription|commercial|monetiz|referral|revenue|business finance"),
    ("product", r"website|web |web$|telegram|frontend|chart|dashboard|user profile|personaliz|mobile|pwa|native app|notification|watchlist|onboard|accessibility|ui |ux |public api|api version|webhook|journal|trust"),
    ("database", r"database|redis|schema|data.lifecycle|storage|warehouse|migration|backup|restore"),
    ("operations", r"observab|metric|slo|capacity|load |scale|scalab|performance|queue|schedul|trace|logging|logs|latency|cost control|incident|disaster|runbook|chaos|failure|retry|retries|dead.letter|job|clock|notification"),
    ("release", r"release|certif|clean.room|environment|deployment|branch|fingerprint|ci/cd|rollout|canary|rollback|gate|testing|regression|configuration|pre.implementation"),
]


def domain_for(title: str) -> str:
    for domain, pattern in PATTERNS:
        if re.search(pattern, title.lower()):
            return domain
    return "governance"


def boundaries(kind: str, lines: list[str]) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    if kind == "BP":
        starts = [i for i, line in enumerate(lines) if line == "1. Executive Summary"]
        start = starts[-1]
    else:
        start = 0
    for i, line in enumerate(lines):
        if i < start:
            continue
        if kind in {"ROAD", "HAND", "HARD", "BP"}:
            match = re.match(r"^(\d{1,3})\. (.+)$", line)
            if match and (kind != "HARD" or (i > 0 and lines[i-1].startswith("===="))):
                number = int(match[1])
                if kind == "BP" and number > 50:
                    continue
                found.append((i, f"{number:03d}", match[2]))
            elif kind == "BP" and re.match(r"^Appendix [ABC]\. ", line):
                found.append((i, "APP-" + line[9], line))
            elif kind == "HARD" and line == "FINAL IMPLEMENTATION PRIORITY":
                found.append((i, "PRIORITY", line))
        elif line in (MASTER_HEADINGS if kind == "MASTER" else MULTI_HEADINGS):
            found.append((i, f"{len(found)+1:03d}", line))
    return found


def main() -> None:
    old = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    prior = {r["id"]: r for r in old.get("requirements", [])}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    requirements = []
    sources = []
    for kind, name, relative in SOURCES:
        raw = (ROOT / relative).read_bytes()
        lines = raw.decode("utf-8").splitlines()
        sections = boundaries(kind, lines)
        assert sections, relative
        assert len({key for _, key, _ in sections}) == len(sections), relative
        sources.append({"id": kind, "name": name, "path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "line_count": len(lines), "section_count": len(sections), "preamble_line_end": sections[0][0], "authority": "user-supplied requirements context; not independent permission for external actions"})
        for n, (start, suffix, title) in enumerate(sections):
            end = sections[n+1][0] if n+1 < len(sections) else len(lines)
            req_id = f"SR-{kind}-{suffix}"
            domain = domain_for(title)
            mapping = DOMAINS[domain]
            fragments = []
            for i in range(start, end):
                text = lines[i].strip()
                if not text or re.fullmatch(r"[=\-─]+", text):
                    continue
                fragments.append({"id": f"{req_id}-C{len(fragments)+1:03d}", "line": i+1, "text": text, "status": "NOT_STARTED", "verification_evidence": []})
            requirement = {
                "id": req_id, "title": title, "domain": domain,
                "source": {"id": kind, "path": relative, "line_start": start+1, "line_end": end},
                "status": "IN_PROGRESS" if mapping["modules"] else "NOT_STARTED",
                "mapping_basis": "navigation anchors only; presence of code/test files does not prove this entire source section",
                "implementation_files": mapping["modules"], "test_files": mapping["tests"], "migration_files": mapping["migrations"],
                "related_existing_requirement_ids": mapping["legacy"],
                "reviewed_repository_sha": head, "implementation_commit": None,
                "verification_evidence": [],
                "remaining_acceptance": "Review every source fragment against active call paths; attach requirement-specific tests and current deployment evidence. No section is certified by lexical mapping.",
                "blockers": [], "source_fragments": fragments,
            }
            if kind == "HAND":
                requirement["remaining_acceptance"] = "Reassess this historical task against current SHA/schema/runtime. Its 42-commit gap and target c61ef387/0041 are superseded; see current staging evidence in implementation status report."
            if kind == "BP" and suffix == "APP-C":
                requirement.update(status="NOT_APPLICABLE", disposition_reason="Glossary and closing principles are explanatory context, not a separately executable feature.")
            if req_id in prior:
                for key in ("status", "implementation_files", "test_files", "migration_files", "implementation_commit", "verification_evidence", "remaining_acceptance", "blockers", "disposition_reason"):
                    if key in prior[req_id]:
                        requirement[key] = prior[req_id][key]
                prior_fragments = {f["id"]: f for f in prior[req_id].get("source_fragments", [])}
                for fragment in fragments:
                    existing = prior_fragments.get(fragment["id"], {})
                    if existing.get("text") == fragment["text"]:
                        for key in ("status", "verification_evidence"):
                            fragment[key] = existing.get(key, fragment[key])
            requirements.append(requirement)
    for requirement in requirements:
        for key in ("implementation_files", "test_files", "migration_files"):
            for path in requirement[key]:
                assert (ROOT / path).exists(), (requirement["id"], path)
    output = {
        "schema_version": 1, "snapshot_date": "2026-09-25", "reviewed_repository_sha": head, "reviewed_branch": branch,
        "kind": "additive_blueprint_source_and_evidence_ledger",
        "existing_canonical_registers": ["docs/UNIVERSAL_REQUIREMENT_REGISTER.md", "requirements/requirements.yaml"],
        "scope": "All six supplied source documents indexed at section and source-fragment level. This is exhaustive source capture, not exhaustive implementation validation or a claim that every fragment is an independent atomic requirement.",
        "identity_policy": "Section IDs use immutable source namespaces and source section numbers. Fragment IDs belong to the frozen source checksum; retain IDs and evidence on updates, do not renumber published requirements.",
        "status_vocabulary": ["NOT_STARTED", "IN_PROGRESS", "IMPLEMENTED", "VERIFIED", "BLOCKED_EXTERNAL", "DEFERRED_WITH_REASON", "NOT_APPLICABLE"],
        "status_policy": "Only VERIFIED with behavior-specific evidence closes functional work. File presence, lexical mapping, historical claims, fixtures, and local tests do not certify live integrations. NOT_STARTED on a fragment means granular review/evidence has not begun, not a proven absence of implementation.",
        "source_precedence": "Specific multi-account/final-hardening constraints refine broad blueprint statements. Historical staging SHAs are evidence context, not deployment targets. No source instruction authorizes live trading or production publication.",
        "summary": {"source_count": len(sources), "section_count": len(requirements), "fragment_count": sum(len(r["source_fragments"]) for r in requirements), "section_status_counts": dict(Counter(r["status"] for r in requirements))},
        "sources": sources, "requirements": requirements,
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"]))


if __name__ == "__main__":
    main()
