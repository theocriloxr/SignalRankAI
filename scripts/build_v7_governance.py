#!/usr/bin/env python3
"""Generate deterministic V7 governance, registry, and forensic artefacts.

The output is JSON encoded with ``.yaml`` extensions. JSON is valid YAML 1.2,
keeps the generator dependency-free, and allows CI to validate every artefact
with the Python standard library.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = ROOT / "requirements"
PROMPT_PATH = ROOT / "docs" / "specs" / "SIGNALRANKAI_V7_MASTER_BUILD_PROMPT_2026-07-27.md"
SCHEMA_VERSION = 1
GENERATED_AT = "2026-07-27T00:00:00Z"

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}
TEXT_EXTENSIONS = {
    ".py", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".txt", ".env", ".example", ".sql", ".sh", ".ps1", ".bat", ".xml",
    ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".csv",
}
SENSITIVE_TOKENS = ("SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY", "API_KEY", "DSN", "CREDENTIAL")
DANGEROUS_FLAGS = {
    "PAYMENTS_PUBLIC_ENABLED",
    "REAL_PAYOUTS_ENABLED",
    "AUTO_TRADE_ENABLED",
    "COPY_TRADE_ENABLED",
    "REAL_EXECUTION_ENABLED",
    "MT5_ALLOW_LIVE_ACCOUNTS",
    "TELEGRAM_ALLOW_PAID_BROADCAST",
    "WS_INGEST_ENABLED",
    "CRYPTO_WS_ENABLED",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def _write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _base(kind: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "generated_at": GENERATED_AT,
        "generator": "scripts/build_v7_governance.py",
        "repository_identity": "resolved_in_release_manifest",
        "source_prompt": {
            "path": str(PROMPT_PATH.relative_to(ROOT)),
            "sha256": _sha256(PROMPT_PATH) if PROMPT_PATH.exists() else None,
        },
    }


def _literal_assignment(path: Path, name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                value = node.value
                try:
                    return ast.literal_eval(value)
                except Exception:
                    return None
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _handler_name(node: ast.AST | None) -> str:
    if node is None:
        return "unknown"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        name = _call_name(node.func)
        if name == "_audit_handler" and len(node.args) >= 2:
            return _handler_name(node.args[1])
        return name or "callable"
    if isinstance(node, ast.Lambda):
        return "lambda"
    return type(node).__name__


def build_command_registry() -> dict[str, Any]:
    path = ROOT / "signalrank_telegram" / "bot.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    registrations: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node.func) != "add_handler" or not node.args:
            continue
        handler_call = node.args[0]
        if not isinstance(handler_call, ast.Call) or _call_name(handler_call.func) != "CommandHandler":
            continue
        if not handler_call.args:
            continue
        raw_name = handler_call.args[0]
        names: list[str] = []
        if isinstance(raw_name, ast.Constant) and isinstance(raw_name.value, str):
            names = [raw_name.value]
        elif isinstance(raw_name, (ast.List, ast.Tuple)):
            names = [str(item.value) for item in raw_name.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)]
        handler = _handler_name(handler_call.args[1] if len(handler_call.args) > 1 else None)
        for name in names:
            registrations.append({
                "canonical_name": name.strip().lower(),
                "handler": handler,
                "source": f"signalrank_telegram/bot.py:{node.lineno}",
                "registration": "runtime_static",
                "status": "IMPLEMENTED" if "unavailable" not in handler and "placeholder" not in handler else "DEGRADED_FAIL_CLOSED",
            })

    try:
        from core.tier_policy import COMMAND_MINIMUM_TIER
        minimum_tiers = {name: str(tier.value) for name, tier in COMMAND_MINIMUM_TIER.items()}
    except Exception:
        minimum_tiers = {}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in registrations:
        grouped[item["canonical_name"]].append(item)

    commands: list[dict[str, Any]] = []
    for name, variants in sorted(grouped.items()):
        implemented = [item for item in variants if item["status"] == "IMPLEMENTED"]
        primary = implemented[0] if implemented else variants[0]
        fallback_handlers = sorted({item["handler"] for item in variants if item is not primary})
        commands.append({
            "canonical_name": name,
            "handler": primary["handler"],
            "fallback_handlers": fallback_handlers,
            "sources": sorted(item["source"] for item in variants),
            "registration": "runtime_static",
            "status": "IMPLEMENTED_WITH_FAIL_CLOSED_FALLBACK" if fallback_handlers else primary["status"],
            "minimum_tier": minimum_tiers.get(name, "FREE"),
            "role_scope": minimum_tiers.get(name, "FREE"),
            "timeout_policy": "bounded_by_audit_handler",
            "audit_event": f"telegram.command.{name}",
        })

    by_handler: dict[str, list[str]] = defaultdict(list)
    for item in commands:
        by_handler[item["handler"]].append(item["canonical_name"])
    for item in commands:
        item["aliases_for_same_handler"] = sorted(
            alias for alias in by_handler[item["handler"]] if alias != item["canonical_name"]
        )

    duplicate_active_risks = sorted(
        name for name, variants in grouped.items()
        if len({item["handler"] for item in variants if item["status"] == "IMPLEMENTED"}) > 1
    )
    payload = _base("command_registry")
    payload.update({
        "source": "signalrank_telegram/bot.py",
        "count": len(commands),
        "registration_count": len(registrations),
        "duplicates": duplicate_active_risks,
        "commands": commands,
    })
    return payload


def build_callback_registry() -> dict[str, Any]:
    callbacks_path = ROOT / "signalrank_telegram" / "callback_handlers.py"
    patterns = _literal_assignment(callbacks_path, "CALLBACK_PATTERNS") or {}
    callbacks: list[dict[str, Any]] = []
    for name, pattern in sorted(patterns.items()):
        callbacks.append({
            "name": name,
            "pattern": pattern,
            "handler": f"_handle_{name}",
            "source": "signalrank_telegram/callback_handlers.py",
            "route_class": "global_fallback",
            "ack_policy": "immediate",
            "payload_trust": "untrusted",
            "status": "IMPLEMENTED_OR_EXPLICIT_DEGRADED",
        })

    bot_path = ROOT / "signalrank_telegram" / "bot.py"
    tree = ast.parse(bot_path.read_text(encoding="utf-8-sig"), filename=str(bot_path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node.func) != "add_handler" or not node.args:
            continue
        handler_call = node.args[0]
        if not isinstance(handler_call, ast.Call) or _call_name(handler_call.func) not in {"CallbackQueryHandler", "_CQH"}:
            continue
        pattern = None
        for keyword in handler_call.keywords:
            if keyword.arg == "pattern" and isinstance(keyword.value, ast.Constant):
                pattern = keyword.value.value
        if pattern is None:
            continue
        callbacks.append({
            "name": _handler_name(handler_call.args[0] if handler_call.args else None).lstrip("_"),
            "pattern": str(pattern),
            "handler": _handler_name(handler_call.args[0] if handler_call.args else None),
            "source": f"signalrank_telegram/bot.py:{node.lineno}",
            "route_class": "specific_before_catchall",
            "ack_policy": "handler_or_fast_ack_guard",
            "payload_trust": "untrusted",
            "status": "IMPLEMENTED",
        })

    payload = _base("callback_registry")
    payload.update({
        "count": len(callbacks),
        "callbacks": sorted(callbacks, key=lambda item: (item["pattern"], item["source"])),
        "invariants": [
            "specific routes register before the catch-all route",
            "callback data is untrusted and must be ownership/entitlement checked",
            "callbacks acknowledge before database or network work",
            "forged or expired callbacks fail closed with a user-visible response",
        ],
    })
    return payload


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            values[key] = value.strip()
    return values


def _production_python_files() -> Iterable[Path]:
    for folder in ("core", "data", "db", "engine", "payments", "services", "signalrank_telegram", "web", "worker"):
        base = ROOT / folder
        if base.exists():
            yield from base.rglob("*.py")
    for name in ("config.py", "railway_main.py"):
        path = ROOT / name
        if path.exists():
            yield path


def _scan_env_reads() -> dict[str, list[str]]:
    reads: dict[str, set[str]] = defaultdict(set)
    for path in _production_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = _call_name(node.func)
            if name not in {"getenv", "get"}:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", first.value):
                reads[first.value].add(f"{path.relative_to(ROOT)}:{node.lineno}")
    return {name: sorted(locations) for name, locations in reads.items()}


def build_environment_and_flags() -> tuple[dict[str, Any], dict[str, Any]]:
    env_paths = [ROOT / ".env.example", ROOT / "RAILWAY_ENV_UPDATED.env.example"]
    env_paths.extend(sorted((ROOT / "configs" / "env").glob("*.env.example")))
    env_paths.extend(sorted((ROOT / "deploy" / "railway_roles").glob("*.env")))
    files = {str(path.relative_to(ROOT)): _parse_env_file(path) for path in env_paths if path.exists()}
    reads = _scan_env_reads()
    names = sorted(set(reads) | {name for values in files.values() for name in values})
    prod_defaults = files.get("configs/env/production.env.example", {})

    variables = []
    for name in names:
        defaults = {path: values[name] for path, values in files.items() if name in values}
        variables.append({
            "name": name,
            "sensitive": any(token in name for token in SENSITIVE_TOKENS),
            "required_by_code": name in reads,
            "read_locations": reads.get(name, [])[:40],
            "declared_defaults": defaults,
            "production_example_default": prod_defaults.get(name),
        })

    environment = _base("environment_registry")
    environment.update({
        "environment_files": sorted(files),
        "variable_count": len(variables),
        "variables": variables,
        "rules": [
            "secrets are injected by the deployment platform and never committed",
            "staging and production use independent Postgres, Redis, Telegram bots, and credentials",
            "runtime uses PgBouncer while migrations prefer a direct database URL when available",
        ],
    })

    flag_names = sorted(
        name for name in names
        if name.endswith("_ENABLED") or name.startswith("RUN_") or name.startswith("ALLOW_") or name in DANGEROUS_FLAGS
    )
    flags = []
    for name in flag_names:
        default = prod_defaults.get(name)
        dangerous = name in DANGEROUS_FLAGS
        flags.append({
            "name": name,
            "production_example_default": default,
            "dangerous": dangerous,
            "required_safe_default": "0" if dangerous else None,
            "safe_default_satisfied": (default in {"0", "false", "False", "off", "OFF"}) if dangerous else None,
            "rollback": f"set {name}=0 and redeploy" if dangerous else "restore previous environment value and redeploy",
        })
    feature_flags = _base("feature_flags")
    feature_flags.update({"count": len(flags), "flags": flags})
    return environment, feature_flags


def build_provider_registry() -> dict[str, Any]:
    providers: list[dict[str, Any]] = []
    try:
        from data.provider_catalog import PROVIDER_SPECS
        for spec in PROVIDER_SPECS:
            item = spec.to_dict()
            item.update({
                "certification_status": "IMPLEMENTED_NOT_LIVE_VERIFIED",
                "evidence_required": "scripts/certify_providers.py output from the exact deployment environment",
                "release_policy": "disabled or best-effort until exact environment/plan certification passes",
            })
            providers.append(item)
    except Exception as exc:
        providers.append({"key": "registry_import_failed", "error": f"{type(exc).__name__}: {exc}"})
    payload = _base("provider_registry")
    payload.update({
        "count": len(providers),
        "providers": providers,
        "truth_policy": "Importability is implementation evidence, not live certification.",
    })
    return payload


def _requirement(
    req_id: str,
    title: str,
    statement: str,
    priority: str,
    phase: str,
    domain: str,
    status: str,
    modules: list[str],
    tests: list[str],
    evidence: str,
    acceptance: list[str],
    rollback: str,
    source_lines: str,
) -> dict[str, Any]:
    return {
        "id": req_id,
        "title": title,
        "statement": statement,
        "source_references": [f"docs/specs/SIGNALRANKAI_V7_MASTER_BUILD_PROMPT_2026-07-27.md:{source_lines}"],
        "priority": priority,
        "release_phase": phase,
        "owner_domain": domain,
        "safety_classification": "critical" if priority == "P0" else "controlled",
        "enabled_policy": "gated",
        "implementation_modules": modules,
        "migrations_data_impact": "none_or_documented_in_module_migrations",
        "test_ids": tests,
        "runtime_diagnostic_ids": [req_id.replace("SRA-", "DIAG-")],
        "evidence_type": evidence,
        "status": status,
        "acceptance_criteria": acceptance,
        "rollback_deactivation": rollback,
    }


def build_requirements() -> dict[str, Any]:
    requirements = [
        _requirement("SRA-GOV-001", "Machine-readable governance", "Version control requirement, decision, conflict, incident, blocker, flag, environment, command, callback, provider, release-gate, evidence, and legacy-disposition registries.", "P0", "A", "governance", "TESTED_LOCAL", ["requirements/", "scripts/build_v7_governance.py"], ["tests/test_v7_governance_contract.py"], "generated registry validation", ["all required registry files exist", "all registry files parse as JSON/YAML", "generated registries are deterministic"], "revert the governance commit", "103-158"),
        _requirement("SRA-WEB-001", "Canonical FastAPI security surface", "The Railway-mounted web application must remain the canonical FastAPI API and expose the broker-security contracts used by production routes.", "P0", "A", "web", "TESTED_LOCAL", ["web/app.py", "railway_main.py"], ["tests/test_web_app_regression_guard.py", "tests/test_web_api_tokens.py"], "focused local tests", ["web.app is FastAPI", "security routes exist", "token tests pass"], "revert commit 1c2ad0d", "188-216"),
        _requirement("SRA-CI-001", "Deterministic complete test partition", "The complete test-file inventory is split into exactly the requested number of non-empty isolated batches.", "P0", "A", "release", "TESTED_LOCAL", ["scripts/run_complete_system_test.py"], ["tests/test_complete_system_orchestrator_contract.py"], "20-batch local run", ["20 requested batches produce 20 batches", "every test file appears once", "all isolated batches complete"], "revert commit deeefed", "850-876"),
        _requirement("SRA-DB-001", "PgBouncer runtime contract", "Runtime database access uses one shared async engine per process, NullPool in transaction-pooling mode, bounded admission, and no session sharing.", "P0", "B", "database", "TESTED_LOCAL", ["db/session.py", "db/priority.py"], ["tests/test_phase4_pass2_db_priority_and_command_speed.py", "tests/test_storage_priority_hardening.py"], "local contract tests; staging proof pending", ["session priority lanes are enforced", "runtime engine contract is introspectable", "staging uses transaction-pooling-safe settings"], "set engine/worker flags off and rollback application", "308-383"),
        _requirement("SRA-DB-002", "Every session is labelled", "Every DB session holder records an explicit or generated non-empty caller label; unlabelled holders are impossible.", "P0", "B", "database", "TESTED_LOCAL", ["db/session.py"], ["tests/test_db_session_labels.py", "tests/test_railway_runtime_incident_fixes.py"], "39 focused local tests", ["blank and omitted labels become caller labels", "holder label is never unlabelled"], "revert commit ee07957", "329-349"),
        _requirement("SRA-TG-001", "Command and callback operability", "Core Telegram commands and visible callbacks acknowledge promptly and either complete real work or return an explicit degraded result.", "P0", "C", "telegram", "TESTED_LOCAL", ["signalrank_telegram/bot.py", "signalrank_telegram/callback_handlers.py"], ["tests/test_callback_feature_completion.py", "tests/test_callback_handler.py"], "17 focused local tests; live bot probe pending", ["chart callback renders a chart", "Gemini callback returns review or honest degradation", "no visible placeholder path remains", "forged signal callbacks are rejected"], "disable affected button emission and rollback callback commit", "387-485"),
        _requirement("SRA-TG-002", "Generated command and callback registries", "The source registration surface is inventoried into deterministic command and callback registries with duplicate detection.", "P1", "C", "telegram", "TESTED_LOCAL", ["scripts/build_v7_governance.py", "requirements/command_registry.yaml", "requirements/callback_registry.yaml"], ["tests/test_v7_governance_contract.py"], "static AST registry", ["all static command registrations are represented", "duplicates are explicit", "specific callback routes are represented"], "regenerate from source", "414-479"),
        _requirement("SRA-DEL-001", "Proof-backed delivery truth", "Only Telegram-successful persisted deliveries count as delivered and as the start of repeat protection.", "P0", "D", "delivery", "TESTED_LOCAL", ["db/models.py", "signalrank_telegram/bot.py", "services/asset_repeat_policy.py"], ["tests/test_outcome_delivery_contract.py", "tests/test_delivery_idempotency.py"], "local tests; exact live signal proof pending", ["sent_ok is required", "Telegram chat/message identifiers are persisted", "uncertain results are not counted as delivered"], "pause distribution and reconcile delivery rows", "594-617"),
        _requirement("SRA-DEDUP-001", "Four-hour same-user asset lock", "A same-user same-asset direction-agnostic repeat lock defaults to four hours and starts only after proof-backed delivery.", "P0", "D", "delivery", "TESTED_LOCAL", ["services/asset_repeat_policy.py", "signalrank_telegram/bot.py"], ["tests/test_asset_repeat_policy.py", "tests/test_outcome_delivery_contract.py"], "local tests; Railway restart proof pending", ["unsent reservations do not start lock", "lock is direction agnostic", "durable DB proof reconstructs after cache loss"], "set distribution flags off", "594-617"),
        _requirement("SRA-PROV-001", "Provider certification", "Provider implementation and live certification are separate; each provider is certified in the exact deployment environment and plan before production support.", "P0", "D/F", "market_data", "BLOCKED_EXTERNAL", ["data/provider_catalog.py", "scripts/certify_providers.py", "requirements/provider_registry.yaml"], ["tests/test_provider_catalog.py"], "provider certification report", ["representative symbols and timeframes pass", "freshness and failure taxonomy are evidenced", "credentials and regional access are proven"], "disable provider flag and route to certified alternatives", "526-553"),
        _requirement("SRA-MIG-001", "Migration graph and legacy upgrade", "Alembic has one head and clean, sequential, representative legacy, drifted, and rerun scenarios are evidenced on PostgreSQL.", "P0", "B", "database", "PROVEN_LOCAL_ONLY", ["db/migrations/", "scripts/schema_audit.py"], ["tests/test_payment_receipt_migration_idempotency.py", "tests/test_migration_chain.py"], "local static/fixture evidence; real PostgreSQL legacy rehearsal pending", ["one Alembic head", "no data deletion to satisfy constraints", "legacy upgrade report retained"], "forward-fix migration or application rollback compatible with schema", "368-383"),
        _requirement("SRA-PAY-001", "Paystack payment integrity", "Paystack processing verifies raw-body HMAC, transaction details, amount/currency/reference, idempotency, entitlement, and receipts; public payments remain gated.", "P0", "H", "payments", "DISABLED_BY_POLICY", ["payments/", "configs/env/production.env.example"], ["tests/test_phase4_pass6_security_api_payments.py"], "local contract tests; Paystack test-mode E2E pending", ["PAYMENTS_PUBLIC_ENABLED=0 by default", "test-mode E2E passes before beta", "wrong amount and replay are rejected"], "set PAYMENTS_PUBLIC_ENABLED=0", "633-654"),
        _requirement("SRA-EXEC-001", "Execution safety gates", "Real execution, copy trading, Smart DCA, and live accounts remain disabled until independent demo/live certification and owner approval.", "P0", "I", "execution", "DISABLED_BY_POLICY", ["services/mt5_signal_router.py", "configs/env/production.env.example"], ["tests/test_tiered_execution_canonical_routing.py", "tests/test_broker_permission_validation.py"], "local safety tests; MetaApi demo proof pending", ["REAL_EXECUTION_ENABLED=0", "COPY_TRADE_ENABLED=0", "no fallback lot/equity", "unknown orders reconcile before retry"], "activate kill switches and revoke broker credentials", "658-681"),
        _requirement("SRA-ML-001", "Optional Gemini advisory", "Gemini is optional, bounded, semantically validated, never sole execution authority, and degrades without stopping the deterministic core.", "P1", "D", "ml", "TESTED_LOCAL", ["services/gemini_ml.py", "signalrank_telegram/callback_handlers.py"], ["tests/test_callback_feature_completion.py", "tests/test_phase4_pass8_ml_lifecycle_governance.py"], "local mocked/contract tests; live quota proof pending", ["Gemini outage returns explicit degradation", "deterministic signal remains available", "no execution decision is delegated"], "disable Gemini feature flags", "685-706"),
        _requirement("SRA-SEC-001", "Security and supply-chain assurance", "Release runs secret, dependency, vulnerability, SBOM, container, authorization, webhook, and payment security checks.", "P0", "A-I", "security", "PARTIAL_LOCAL", ["scripts/secret_scan.py", "scripts/production_readiness_check.py"], ["tests/test_phase4_pass6_security_api_payments.py"], "local scans; external vulnerability/container evidence pending", ["no committed secrets", "critical/high findings block release", "SBOM and image scan are retained"], "disable public surfaces and rotate exposed credentials", "710-740"),
        _requirement("SRA-OBS-001", "Observability and SLO evidence", "Structured logs, metrics, traces, holder age, queue lag, webhook, command, delivery, provider, lifecycle, payment, and execution diagnostics are correlated.", "P1", "A-E", "operations", "PARTIAL_LOCAL", ["observability/", "db/session.py", "scripts/deployment_diagnostics.py"], ["tests/test_phase4_pass7_observability_reliability_performance.py"], "local diagnostics; production SLO baseline pending", ["critical IDs propagate", "high-cardinality IDs are not metric labels", "alerts include runbook references"], "disable noncritical telemetry exporters", "744-789"),
        _requirement("SRA-DR-001", "Disaster recovery drill", "PostgreSQL backup/restore, Redis loss, consumer recovery, rollback, and dependency outage procedures are tested in isolated staging.", "P0", "E", "reliability", "BLOCKED_EXTERNAL", ["docs/", "scripts/deployment_diagnostics.py"], [], "staging restore/chaos report", ["restore drill succeeds", "RPO/RTO are measured", "active signals survive restart"], "enter incident mode and restore last verified backup", "791-821"),
        _requirement("SRA-RAIL-001", "Railway staging certification", "A separate Railway staging environment proves migrations, readiness, webhook, queues, commands, callbacks, providers, restart, and rollback before production activation.", "P0", "A-E", "release", "BLOCKED_EXTERNAL", ["railway.toml", "deploy/railway_roles/", "scripts/deployment_diagnostics.py"], [], "Railway deployment and probe evidence", ["staging dependencies are independent", "safe command matrix passes", "pending Telegram updates return to zero"], "rollback deployment and keep engine/payment/execution flags off", "949-1054"),
        _requirement("SRA-SOAK-001", "Owner soak", "The owner-beta release soaks for 24–72 hours with stable queues, memory, CPU, connections, outcomes, webhook, and delivery behaviour.", "P0", "E", "release", "BLOCKED_EXTERNAL", ["requirements/release_gates.yaml"], [], "retained soak report", ["no DB leak", "no duplicate/stale delivery", "no unexplained webhook error", "restart recovery passes"], "disable engine and distribution and roll back", "1030-1038"),
    ]
    payload = _base("requirements")
    payload.update({
        "status_vocabulary": ["UNASSESSED", "DESIGNED", "IMPLEMENTED", "TESTED_LOCAL", "PROVEN_LOCAL_ONLY", "PROVEN_STAGING", "PROVEN_LIVE", "PARTIAL_LOCAL", "BLOCKED_EXTERNAL", "DISABLED_BY_POLICY", "RETIRED_APPROVED"],
        "requirements": requirements,
        "summary": dict(Counter(item["status"] for item in requirements)),
        "disclaimer": "This registry covers release-critical V7 slices discovered and dispositioned in this pass; it does not claim all 10,000+ prompt lines are live-proven.",
    })
    return payload


def build_decisions_conflicts_incidents_blockers() -> tuple[dict[str, Any], ...]:
    decisions = _base("decisions")
    decisions["decisions"] = [
        {"id": "SRA-DEC-001", "decision": "web.app FastAPI is the canonical Railway-mounted web surface; the legacy Flask dashboard is not a substitute.", "authority": "V7 modular/API contract and existing security tests", "status": "APPLIED", "commit": "1c2ad0d", "rollback": "revert only with an approved replacement that passes the same route/security tests"},
        {"id": "SRA-DEC-002", "decision": "Complete local pytest evidence uses deterministic isolated file batches because the monolithic process can hang during teardown after tests execute.", "authority": "V7 evidence accuracy and repository orchestrator design", "status": "APPLIED", "commit": "deeefed", "rollback": "return to monolithic only after teardown root cause is proven fixed"},
        {"id": "SRA-DEC-003", "decision": "Signal chart and Gemini callbacks require proof-backed user delivery before signal data is loaded.", "authority": "V7 callback ownership/IDOR contract", "status": "APPLIED", "commit": "a842802", "rollback": "remove button emission; never weaken ownership checks"},
        {"id": "SRA-DEC-004", "decision": "Missing DB session labels are derived from bounded caller inspection rather than stored as unlabelled.", "authority": "V7 PgBouncer/session diagnostics contract", "status": "APPLIED", "commit": "ee07957", "rollback": "require explicit labels at every caller before removing derivation"},
        {"id": "SRA-DEC-005", "decision": "Public payments, real payouts, auto trading, copy trading, real execution, live MT5 accounts, and WebSockets remain disabled by default.", "authority": "V7 release gates", "status": "BINDING", "rollback": "not applicable; activation requires a new approved decision and evidence"},
    ]

    conflicts = _base("conflicts")
    conflicts["conflicts"] = [
        {"id": "SRA-CON-001", "sources": ["web/app.py at input HEAD 8871315", "web security tests and Railway mount"], "old_interpretation": "a minimal Flask dashboard can replace the web module", "new_interpretation": "the production FastAPI security surface is canonical", "user_impact": "broker security/API routes disappeared", "data_migration_impact": "none", "security_financial_impact": "high", "decision": "restore FastAPI", "authority": "SRA-DEC-001", "compatibility_plan": "legacy Flask surface is not mounted", "tests": ["tests/test_web_app_regression_guard.py"]},
        {"id": "SRA-CON-002", "sources": ["scripts/run_complete_system_test.py before deeefed", "requested 20-batch CI topology"], "old_interpretation": "ceiling chunk size approximates requested batches", "new_interpretation": "requested batch count is exact", "user_impact": "CI coverage topology drifted silently", "data_migration_impact": "none", "security_financial_impact": "medium", "decision": "balanced divmod partition", "authority": "SRA-DEC-002", "compatibility_plan": "deterministic contiguous batches", "tests": ["tests/test_complete_system_orchestrator_contract.py"]},
        {"id": "SRA-CON-003", "sources": ["V7 public-payment product line", "unresolved owner pricing/legal approvals"], "old_interpretation": "payment routes imply payment readiness", "new_interpretation": "payments remain disabled until test-mode E2E and business approval", "user_impact": "prevents incorrect charging/entitlement", "data_migration_impact": "receipt ledger must be preserved", "security_financial_impact": "critical", "decision": "PAYMENTS_PUBLIC_ENABLED=0", "authority": "V7 Gate H", "compatibility_plan": "controlled paid beta after approval", "tests": ["tests/test_phase4_pass6_security_api_payments.py"]},
    ]

    incidents = _base("incidents")
    incidents["incidents"] = [
        {"id": "SRA-INC-001", "severity": "P0", "title": "Production web API replaced by legacy Flask dashboard", "detected_by": "source diff plus web contract tests", "root_cause": "latest archive commit overwrote web/app.py with an incompatible legacy surface", "containment": "restored last known FastAPI implementation", "fix_commit": "1c2ad0d", "regression_tests": ["tests/test_web_app_regression_guard.py"], "status": "RESOLVED_LOCAL"},
        {"id": "SRA-INC-002", "severity": "P1", "title": "Complete-suite orchestrator produced fewer batches than requested", "detected_by": "orchestrator contract test", "root_cause": "ceiling-sized slicing produced 18 chunks for a requested 20", "containment": "balanced exact partition", "fix_commit": "deeefed", "regression_tests": ["tests/test_complete_system_orchestrator_contract.py"], "status": "RESOLVED_LOCAL"},
        {"id": "SRA-INC-003", "severity": "P1", "title": "Visible chart/Gemini callback routes were placeholder acknowledgements", "detected_by": "callback source audit", "root_cause": "global catch-all advertised route names without completing work", "containment": "implemented user-scoped chart and Gemini handlers; fail-closed MT5 fallback", "fix_commit": "a842802", "regression_tests": ["tests/test_callback_feature_completion.py"], "status": "RESOLVED_LOCAL"},
        {"id": "SRA-INC-004", "severity": "P1", "title": "DB caller label resolver was present but unused", "detected_by": "session API forensic review", "root_cause": "get_session still defaulted to unlabelled", "containment": "wired bounded caller-derived labels", "fix_commit": "ee07957", "regression_tests": ["tests/test_db_session_labels.py"], "status": "RESOLVED_LOCAL"},
    ]

    blockers = _base("blockers")
    blockers["blockers"] = [
        {"id": "SRA-BLK-001", "type": "external_environment", "status": "BLOCKED_EXTERNAL", "blocking_gates": ["B", "C", "D", "E"], "needed": "Railway staging project with independent Postgres, PgBouncer/direct migration URL, RedisState, RedisDelivery, and test Telegram bot", "owner_action": "provision/connect staging resources and credentials", "safe_default": "engine and public distribution remain off"},
        {"id": "SRA-BLK-002", "type": "credential_entitlement", "status": "BLOCKED_EXTERNAL", "blocking_gates": ["D", "F"], "needed": "exact provider credentials/plans and regional Railway access for live certification", "owner_action": "supply approved keys in staging secrets", "safe_default": "provider remains uncertified/disabled or best-effort"},
        {"id": "SRA-BLK-003", "type": "business_legal", "status": "REQUIRES_OWNER_APPROVAL", "blocking_gates": ["G", "H", "I"], "needed": "approved prices, tier entitlements, terms/privacy, jurisdictional and financial/legal review", "owner_action": "approve versioned business/legal decisions", "safe_default": "public payments and real execution remain off"},
        {"id": "SRA-BLK-004", "type": "payment_sandbox", "status": "BLOCKED_EXTERNAL", "blocking_gates": ["H"], "needed": "Paystack test keys and webhook endpoint", "owner_action": "configure staging test credentials and permit controlled E2E", "safe_default": "PAYMENTS_PUBLIC_ENABLED=0"},
        {"id": "SRA-BLK-005", "type": "broker_demo", "status": "BLOCKED_EXTERNAL", "blocking_gates": ["I"], "needed": "dedicated MetaApi demo account and approved test window", "owner_action": "provide demo account only; no live account", "safe_default": "REAL_EXECUTION_ENABLED=0 and MT5_ALLOW_LIVE_ACCOUNTS=0"},
        {"id": "SRA-BLK-006", "type": "time_based_evidence", "status": "BLOCKED_EXTERNAL", "blocking_gates": ["E"], "needed": "24–72 hour Railway owner soak plus restart/Redis recovery evidence", "owner_action": "run after Gates A–D pass in staging", "safe_default": "do not claim production readiness"},
    ]
    return decisions, conflicts, incidents, blockers


def build_release_gates() -> dict[str, Any]:
    gates = [
        ("A", "code_integrity", "PARTIAL_PASS_LOCAL", ["clean dependency install", "all local batches pass", "no unknown P0/P1 requirement", "security scans meet threshold"]),
        ("B", "database_infrastructure", "PARTIAL_PASS_LOCAL", ["one Alembic head", "clean and legacy PostgreSQL migrations", "PgBouncer contract", "separate Redis services", "unique task ownership"]),
        ("C", "telegram_recovery", "PARTIAL_PASS_LOCAL", ["webhook acceptance", "registry equals runtime", "safe command probes", "all visible callbacks", "no cross-user access"]),
        ("D", "owner_crypto_advisory", "BLOCKED_EXTERNAL", ["crypto REST provider certified", "exact signal delivery/lifecycle/outcome proof", "four-hour repeat lock", "WebSockets off"]),
        ("E", "owner_soak", "BLOCKED_EXTERNAL", ["24–72 hour stability", "restart and Redis recovery", "stable queues and resources"]),
        ("F", "asset_expansion", "BLOCKED_EXTERNAL", ["one asset class at a time", "provider/calendar/instrument/strategy/lifecycle certification"]),
        ("G", "limited_users_subscriptions", "BLOCKED_EXTERNAL", ["internal tester matrix", "support runbook", "owner business approval"]),
        ("H", "payments", "DISABLED_BY_POLICY", ["Paystack test E2E", "replay/wrong amount/refund/reconciliation/receipt", "legal/pricing approval"]),
        ("I", "execution", "DISABLED_BY_POLICY", ["paper", "MetaApi demo", "controlled demo users", "separate real pilot approval"]),
    ]
    payload = _base("release_gates")
    payload["gates"] = [
        {"gate": gate, "name": name, "status": status, "acceptance": acceptance, "strongest_allowed_verdict": "local_repository_hardened" if gate in {"A", "B", "C"} else "not_activated"}
        for gate, name, status, acceptance in gates
    ]
    return payload


def build_evidence_catalogue() -> dict[str, Any]:
    payload = _base("evidence_catalogue")
    payload["evidence"] = [
        {"id": "EVD-WEB-001", "command": "pytest focused web security/regression tests", "expected_artifact": "evidence/web_app_regression_tests.txt", "scope": "local integration/contract", "live": False},
        {"id": "EVD-TG-001", "command": "pytest callback completion and signal hardening tests", "expected_artifact": "evidence/callback_completion_extended_tests.txt", "scope": "local mocked/contract", "live": False},
        {"id": "EVD-DB-001", "command": "pytest DB label/priority/Railway incident tests", "expected_artifact": "evidence/db_session_label_tests.txt", "scope": "local contract", "live": False},
        {"id": "EVD-CI-001", "command": "20 isolated pytest file batches", "expected_artifact": "evidence/pytest_batches/summary.json", "scope": "complete local test inventory", "live": False},
        {"id": "EVD-STATIC-001", "command": "compile/env/schema/architecture/session/governance/secret/readiness diagnostics", "expected_artifact": "evidence/diagnostics/summary.json", "scope": "local static and configuration", "live": False},
        {"id": "EVD-RAIL-001", "command": "deployment_diagnostics staging-live", "expected_artifact": None, "scope": "Railway staging", "live": True, "status": "BLOCKED_EXTERNAL"},
        {"id": "EVD-SOAK-001", "command": "owner soak 24-72h", "expected_artifact": None, "scope": "Railway staging/owner beta", "live": True, "status": "BLOCKED_EXTERNAL"},
    ]
    return payload


def _classify(path: Path) -> tuple[str, str]:
    rel = path.relative_to(ROOT)
    text = str(rel).replace("\\", "/")
    if text.startswith("tests/"):
        return "TEST_ONLY", "automated test evidence"
    if text.startswith((".diagnostics/", ".freebuff/", "artifacts/", "logs/")):
        return "DELETE_GENERATED_ONLY", "local runtime/generated state excluded from clean release package"
    if text.startswith("docs/") or path.suffix.lower() in {".md", ".rst"}:
        return "DOCUMENTATION_ONLY", "documentation/specification/evidence"
    if text.startswith("requirements/"):
        return "DOCUMENTATION_ONLY", "machine-readable governance"
    if text.startswith("db/migrations/"):
        return "PRESERVE_BEHAVIOUR", "database migration history"
    if path.suffix in {".patch", ".zip", ".pyc", ".log"} or path.name.endswith((".sqlite", ".db", ".db-shm", ".db-wal")):
        return "DELETE_GENERATED_ONLY", "generated/local artefact excluded from clean release package"
    if path.suffix == ".py" or path.name.startswith("Dockerfile") or path.name in {"Procfile", "railway.toml", "pyproject.toml", "requirements.txt", ".dockerignore", ".gitignore", ".python-version"}:
        return "PRESERVE_BEHAVIOUR", "production/build source"
    if ".env" in path.name or path.suffix in {".toml", ".yaml", ".yml", ".json", ".sql", ".sh", ".ps1", ".txt", ".cfg", ".ini", ".csv", ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".png", ".jpg", ".jpeg", ".svg", ".ico"}:
        return "PRESERVE_BEHAVIOUR", "configuration, data, or product asset retained"
    return "PRESERVE_BEHAVIOUR", "repository asset explicitly retained; no generated-state signature detected"


def build_legacy_disposition() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path == OUT / "legacy_disposition.json":
            continue
        disposition, reason = _classify(path)
        size = path.stat().st_size
        line_count = None
        if path.suffix.lower() in TEXT_EXTENSIONS or path.name in {"Dockerfile", "Procfile"}:
            try:
                line_count = len(path.read_text(encoding="utf-8-sig", errors="replace").splitlines())
            except Exception:
                line_count = None
        entries.append({
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": _sha256(path),
            "size_bytes": size,
            "line_count": line_count,
            "disposition": disposition,
            "reason": reason,
        })
    payload = _base("legacy_disposition")
    payload.update({
        "file_count": len(entries),
        "summary": dict(Counter(item["disposition"] for item in entries)),
        "files": entries,
        "scope_note": "Every repository file outside ignored caches/environments is hashed and dispositioned. UNKNOWN_REQUIRES_REVIEW remains a release blocker until explicitly resolved.",
    })
    return payload


def generate() -> None:
    command_registry = build_command_registry()
    callback_registry = build_callback_registry()
    environment, flags = build_environment_and_flags()
    decisions, conflicts, incidents, blockers = build_decisions_conflicts_incidents_blockers()

    _write("requirements.yaml", build_requirements())
    _write("decisions.yaml", decisions)
    _write("conflicts.yaml", conflicts)
    _write("incidents.yaml", incidents)
    _write("blockers.yaml", blockers)
    _write("feature_flags.yaml", flags)
    _write("environment_registry.yaml", environment)
    _write("command_registry.yaml", command_registry)
    _write("callback_registry.yaml", callback_registry)
    _write("provider_registry.yaml", build_provider_registry())
    _write("release_gates.yaml", build_release_gates())
    _write("evidence_catalogue.yaml", build_evidence_catalogue())
    _write("legacy_disposition.json", build_legacy_disposition())

    summary = {
        "generated": sorted(path.name for path in OUT.iterdir() if path.is_file()),
        "commit": _git("rev-parse", "HEAD"),
        "command_count": command_registry["count"],
        "callback_count": callback_registry["count"],
        "environment_variable_count": environment["variable_count"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Regenerate and fail if tracked output changes")
    args = parser.parse_args()
    before = {path.name: path.read_bytes() for path in OUT.glob("*") if path.is_file()} if args.check else {}
    generate()
    if args.check:
        after = {path.name: path.read_bytes() for path in OUT.glob("*") if path.is_file()}
        if before != after:
            print("V7 governance artefacts were stale; regenerate and commit them.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
