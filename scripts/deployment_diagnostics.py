#!/usr/bin/env python3
"""Evidence-first SignalRankAI deployment diagnostics.

The command is safe/read-only by default.  It inventories the entire configured
runtime and records PASS/FAIL/BLOCKED/SAFE_EXPECTED_OFF/NOT_IN_SCOPE instead of treating missing
credentials as success.  Optional network sends, Paystack calls, Gemini calls,
and MetaApi demo orders require explicit opt-in flags.

Examples:
  python scripts/deployment_diagnostics.py --phase predeploy --strict-core
  python scripts/deployment_diagnostics.py --phase runtime --base-url https://... \
      --output /tmp/signalrank_deployment_diagnostics.json
  python scripts/deployment_diagnostics.py --phase full --run-full-suite \
      --live-providers --continue-on-failure
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Use the same normalized environment and sandbox boundaries as the main
# Railway process. This prevents the diagnostics subprocess from reporting a
# different full-system mode than the running application.
try:
    from runtime_safety import apply_runtime_safety_environment
    _DIAGNOSTIC_RUNTIME_SAFETY = apply_runtime_safety_environment()
except Exception:
    _DIAGNOSTIC_RUNTIME_SAFETY = None

# Telegram's HTTP transport embeds the bot token in the request URL. Keep
# third-party transport logs below INFO so deployment evidence cannot disclose
# credentials even when the root logger is verbose.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
SAFE_EXPECTED_OFF = "SAFE_EXPECTED_OFF"
NOT_IN_SCOPE = "NOT_IN_SCOPE"


@dataclass(slots=True)
class Check:
    name: str
    category: str
    status: str
    severity: str
    detail: str
    duration_ms: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)
    remediation: str | None = None
    check_id: str = ""
    evidence_type: str = "unit"
    required: bool = True
    required_profile: str = "all"
    started_at: str = ""
    finished_at: str = ""


class Report:
    def __init__(self, *, phase: str, profile: str) -> None:
        self.phase = phase
        self.profile = profile
        self.started = time.monotonic()
        self.checks: list[Check] = []
        self.missing_permissions: list[dict[str, str]] = []

    def add(self, check: Check) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        check.check_id = check.check_id or f"{check.category}.{check.name}"
        check.started_at = check.started_at or timestamp
        check.finished_at = check.finished_at or timestamp
        self.checks.append(check)
        print(
            f"[{check.status}] {check.category}/{check.name} "
            f"severity={check.severity} detail={check.detail}",
            flush=True,
        )

    def missing(self, *, name: str, purpose: str, env_vars: list[str]) -> None:
        self.missing_permissions.append(
            {"name": name, "purpose": purpose, "env_vars": ",".join(env_vars)}
        )

    def payload(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.checks:
            counts[item.status] = counts.get(item.status, 0) + 1
        blockers = [
            item.name
            for item in self.checks
            if item.required and item.status in {FAIL, BLOCKED}
        ]
        from core.version import get_version_banner

        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": self.phase,
            "profile": self.profile,
            "version": get_version_banner(),
            "duration_seconds": round(time.monotonic() - self.started, 3),
            "summary": {
                "counts": counts,
                "required_blockers": blockers,
                "critical_or_high_failures": blockers,
                "core_ok": not blockers,
            },
            "checks": [asdict(item) for item in self.checks],
            "missing_permissions_or_credentials": self.missing_permissions,
            "evidence_boundaries": [
                "A PASS proves only the named check at the report timestamp.",
                "BLOCKED on any required check makes the selected profile fail.",
                "Missing credentials are BLOCKED, never PASS.",
                "Read-only provider calls do not prove order execution.",
                "A hermetic test suite does not prove Railway or Telegram network delivery.",
                "A live smoke test does not replace the 24-72 hour soak.",
            ],
        }


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def _value(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _masked_url(raw: str) -> str:
    if not raw:
        return ""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(raw)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        user = f"{parts.username}:***@" if parts.username else ""
        return urlunsplit((parts.scheme, f"{user}{host}{port}", parts.path, "", ""))
    except Exception:
        return "<configured>"


def _timed_sync(fn: Callable[[], Check]) -> Check:
    started = time.monotonic()
    result = fn()
    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result


async def _timed_async(fn: Callable[[], Awaitable[Check]]) -> Check:
    started = time.monotonic()
    result = await fn()
    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result


def check_environment(report: Report) -> None:
    required = {
        "database_url": (["DATABASE_URL"], "critical"),
        "state_redis": (["STATE_REDIS_URL", "REDIS_URL"], "critical"),
        "delivery_redis": (["DELIVERY_REDIS_URL"], "critical"),
        "telegram_token": (["TELEGRAM_BOT_TOKEN"], "critical"),
        "telegram_webhook_secret": (["TELEGRAM_WEBHOOK_SECRET"], "critical"),
        "owner_identity": (["OWNER_IDS", "OWNER_TELEGRAM_ID", "TELEGRAM_OWNER_ID"], "high"),
        "encryption_key": (["ENCRYPTION_KEY"], "high"),
        "api_token_pepper": (["API_TOKEN_PEPPER"], "high"),
    }
    for name, (envs, severity) in required.items():
        configured = bool(_value(*envs))
        report.add(
            Check(
                name=name,
                category="environment",
                status=PASS if configured else FAIL,
                severity=severity,
                detail="configured" if configured else f"missing any of {envs}",
                remediation=None if configured else f"Set and seal one of: {', '.join(envs)}",
            )
        )

    state_url = _value("STATE_REDIS_URL", "REDIS_URL")
    delivery_url = _value("DELIVERY_REDIS_URL")
    distinct = bool(state_url and delivery_url and state_url != delivery_url)
    report.add(
        Check(
            name="redis_separation",
            category="environment",
            status=PASS if distinct else FAIL,
            severity="critical",
            detail="distinct URLs" if distinct else "state and delivery Redis are missing or identical",
            evidence={"state": _masked_url(state_url), "delivery": _masked_url(delivery_url)},
            remediation="Provision two Redis services and reference them separately.",
        )
    )

    from runtime_safety import is_full_system_ack_valid

    full_test_requested = _truthy("FULL_SYSTEM_STAGING_TEST_MODE", False)
    full_test_ack = is_full_system_ack_valid(os.getenv("FULL_SYSTEM_STAGING_TEST_ACK"))
    full_test_mode = bool(full_test_requested and full_test_ack)
    report.add(
        Check(
            name="full_system_staging_test_ack",
            category="safety_flags",
            status=PASS if (not full_test_requested or full_test_ack) else FAIL,
            severity="critical",
            detail=f"requested={int(full_test_requested)} acknowledgement_valid={int(full_test_ack)}",
            remediation=None if (not full_test_requested or full_test_ack) else "Set the exact FULL_SYSTEM_STAGING_TEST_ACK value from the v1.2.3 profile.",
        )
    )

    safety_flags = {
        "REAL_EXECUTION_ENABLED": full_test_mode,
        "AUTO_TRADE_ENABLED": full_test_mode,
        "COPY_TRADE_ENABLED": full_test_mode,
        "REAL_PAYOUTS_ENABLED": False,
        "PAYMENTS_PUBLIC_ENABLED": full_test_mode,
        # Live MT5 accounts remain blocked even while the execution workflow is enabled.
        "MT5_ALLOW_LIVE_ACCOUNTS": False,
    }
    for name, expected in safety_flags.items():
        actual = _truthy(name, False)
        ok = actual is expected
        report.add(
            Check(
                name=name.lower(),
                category="safety_flags",
                status=PASS if ok else FAIL,
                severity="critical",
                detail=f"actual={int(actual)} expected={int(expected)} full_test_mode={int(full_test_mode)}",
                remediation=None if ok else f"Apply the v1.2.3 full-system staging profile for {name}.",
            )
        )

    def _clean_paystack_key(value: object) -> str:
        text = str(value or "").strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
            text = text[1:-1].strip()
        return text

    paystack_secret = _clean_paystack_key(os.getenv("PAYSTACK_SECRET_KEY"))
    paystack_public = _clean_paystack_key(os.getenv("PAYSTACK_PUBLIC_KEY"))
    paystack_test_pair = (
        paystack_secret.startswith("sk_test_")
        and paystack_public.startswith("pk_test_")
    )
    paystack_test_mode = paystack_test_pair and _truthy("PAYMENTS_PUBLIC_TEST_MODE", False)
    paystack_live_pair = (
        paystack_secret.startswith("sk_live_")
        and paystack_public.startswith("pk_live_")
    )
    paystack_live_guarded = False
    paystack_key_safe = (not paystack_secret) or paystack_test_mode
    sandbox_ok = (
        (not full_test_mode)
        or (
            paystack_key_safe
            and _truthy("BYBIT_TESTNET", False)
            and not _truthy("MT5_ALLOW_LIVE_ACCOUNTS", False)
        )
    )
    report.add(
        Check(
            name="external_sandbox_boundaries",
            category="safety_flags",
            status=PASS if sandbox_ok else FAIL,
            severity="critical",
            detail=(
                f"paystack_test={int(paystack_test_mode)} "
                f"paystack_test_pair={int(paystack_test_pair)} "
                f"paystack_live_pair={int(paystack_live_pair)} "
                f"paystack_live_guarded={int(paystack_live_guarded)} "
                f"paystack_key_safe={int(paystack_key_safe)} "
                f"bybit_testnet={int(_truthy('BYBIT_TESTNET', False))} "
                f"mt5_live_allowed={int(_truthy('MT5_ALLOW_LIVE_ACCOUNTS', False))}"
            ),
            remediation=None if sandbox_ok else (
                "Use Paystack test keys, or enable guarded live staging with the exact second acknowledgement, "
                "an allowlisted user set and an amount cap; keep BYBIT_TESTNET=1 and MT5_ALLOW_LIVE_ACCOUNTS=0."
            ),
        )
    )

    free_enabled = _truthy("FREE_RANDOM_DISTRIBUTION_ENABLED", False) or _truthy(
        "FREE_SIGNAL_DISTRIBUTION_ENABLED", False
    )
    allowlist = str(os.getenv("DELIVERY_AUDIENCE_ALLOWLIST") or "").strip()
    free_ok = (free_enabled and bool(allowlist)) if full_test_mode else not free_enabled
    report.add(
        Check(
            name="free_distribution_test_audience",
            category="safety_flags",
            status=PASS if free_ok else FAIL,
            severity="critical",
            detail=f"enabled={free_enabled} allowlist_configured={bool(allowlist)} full_test_mode={full_test_mode}",
            remediation=None if free_ok else "Enable free distribution only with DELIVERY_AUDIENCE_ALLOWLIST in full-system staging mode.",
        )
    )

    ws_master = _truthy("WS_INGEST_ENABLED", False)
    ws_crypto = _truthy("CRYPTO_WS_ENABLED", ws_master)
    ws_ok = (ws_master and ws_crypto) if full_test_mode else not (ws_master and ws_crypto)
    report.add(
        Check(
            name="websocket_mode",
            category="market_data",
            status=PASS if ws_ok else FAIL,
            severity="medium",
            detail=f"master={ws_master} crypto={ws_crypto} full_test_mode={full_test_mode}",
            remediation=None if ws_ok else "Apply the matching safe or full-system staging profile.",
        )
    )

    proxy_url = _value("PROXY_API_PROVIDER_URL")
    proxy_enabled = _truthy("PROXY_VALIDATION_ENABLED", False)
    proxy_safe = (not proxy_enabled) or bool(proxy_url and "example.com" not in proxy_url.lower())
    report.add(
        Check(
            name="proxy_validation_configuration",
            category="environment",
            status=PASS if proxy_safe else FAIL,
            severity="medium",
            detail=f"enabled={proxy_enabled} provider_url_configured={bool(proxy_url)}",
            remediation="Disable proxy validation or configure a real provider URL.",
        )
    )


def run_subprocess_check(
    report: Report,
    *,
    name: str,
    category: str,
    command: list[str],
    severity: str = "high",
    timeout: int = 180,
    env: dict[str, str] | None = None,
) -> None:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            env=env or dict(os.environ),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if proc.returncode != 0 and output:
            print(f"[deployment_diagnostics_failure_detail] {category}/{name}\n{output[-4000:]}")
        report.add(
            Check(
                name=name,
                category=category,
                status=PASS if proc.returncode == 0 else FAIL,
                severity=severity,
                detail=f"exit_code={proc.returncode}",
                duration_ms=int((time.monotonic() - started) * 1000),
                evidence={"command": shlex.join(command), "output_tail": output[-4000:]},
                remediation=None if proc.returncode == 0 else "Inspect output_tail and repair the canonical implementation.",
            )
        )
    except subprocess.TimeoutExpired as exc:
        report.add(
            Check(
                name=name,
                category=category,
                status=FAIL,
                severity=severity,
                detail=f"timed out after {timeout}s",
                duration_ms=int((time.monotonic() - started) * 1000),
                evidence={"command": shlex.join(command), "stdout": str(exc.stdout or "")[-1000:]},
                remediation="Diagnose the hang; do not increase the timeout without root-cause evidence.",
            )
        )
    except Exception as exc:
        report.add(
            Check(
                name=name,
                category=category,
                status=FAIL,
                severity=severity,
                detail=f"{type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
                evidence={"command": shlex.join(command)},
            )
        )


def static_checks(report: Report) -> None:
    python = sys.executable
    env_profiles = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "configs" / "env").glob("*.env.example"))
    commands = [
        ("compile_tracked_python", [python, "scripts/compile_tracked_python.py"], "critical"),
        ("pip_dependency_check", [python, "-m", "pip", "check"], "high"),
        ("schema_audit", [python, "scripts/schema_audit.py"], "critical"),
        ("architecture_smoke", [python, "scripts/architecture_smoke.py"], "critical"),
        ("db_session_audit", [python, "scripts/audit_db_session_calls.py"], "high"),
        ("secret_scan", [python, "scripts/secret_scan.py"], "critical"),
        ("production_readiness", [python, "scripts/production_readiness_check.py"], "high"),
        ("governance_validation", [python, "scripts/validate_governance_docs.py"], "high"),
        (
            "environment_contracts",
            [
                python,
                "scripts/validate_env_contract.py",
                ".env.example",
                "RAILWAY_ENV_UPDATED.env.example",
                "deploy/railway_roles/monolith_safe.env",
                "SignalRankAI_v1.3.2_Railway_Full_System_Live_Paystack_Staging.env.example",
                "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example",
                "SignalRankAI_v1.3.3_Railway_Staging_Certification.env.example",
                "SignalRankAI_v1.3.3_Railway_Production_Advisory.env.example",
                *env_profiles,
            ],
            "critical",
        ),
        (
            "repository_proof_manifest",
            [python, "scripts/generate_repository_proof_manifest.py", "--json", "/tmp/signalrank_repository_proof_manifest.json", "--summary", "/tmp/signalrank_repository_proof_manifest.md"],
            "high",
        ),
    ]
    for name, command, severity in commands:
        run_subprocess_check(
            report,
            name=name,
            category="static",
            command=command,
            severity=severity,
        )

    def _routes() -> Check:
        module = importlib.import_module("railway_main")
        routes: list[tuple[str, str]] = []
        for route in getattr(module.app, "routes", []):
            path = str(getattr(route, "path", ""))
            methods = sorted(getattr(route, "methods", set()) or set())
            for method in methods or [""]:
                routes.append((method, path))
        duplicates = sorted({item for item in routes if routes.count(item) > 1})
        required = {"/healthz", "/livez", "/readyz", "/telegram/webhook", "/webhook/tradingview"}
        paths = {path for _, path in routes}
        missing = sorted(required - paths)
        ok = not duplicates and not missing
        return Check(
            name="fastapi_route_inventory",
            category="static",
            status=PASS if ok else FAIL,
            severity="critical",
            detail=f"routes={len(routes)} duplicates={len(duplicates)} missing={missing}",
            evidence={"duplicates": duplicates, "missing": missing},
            remediation=None if ok else "Remove duplicate routes and restore every required ingress path.",
        )

    try:
        report.add(_timed_sync(_routes))
    except Exception as exc:
        report.add(Check("fastapi_route_inventory", "static", FAIL, "critical", f"{type(exc).__name__}: {exc}"))

    def _command_inventory() -> Check:
        source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
        commands = sorted(set(re.findall(r"CommandHandler\(\s*[\"']([^\"']+)", source)))
        callbacks = sorted(set(re.findall(r"pattern\s*=\s*r?[\"']([^\"']+)", source)))
        required = {"start", "help", "signals", "profile", "selfcheck", "db_health", "assets", "system"}
        missing = sorted(required - set(commands))
        return Check(
            name="telegram_command_callback_inventory",
            category="static",
            status=PASS if not missing else FAIL,
            severity="high",
            detail=f"commands={len(commands)} callback_patterns={len(callbacks)} missing_required={missing}",
            evidence={"commands": commands, "callback_patterns": callbacks[:200]},
            remediation=None if not missing else "Restore and test missing command handlers.",
        )

    try:
        report.add(_timed_sync(_command_inventory))
    except Exception as exc:
        report.add(Check("telegram_command_callback_inventory", "static", FAIL, "high", f"{type(exc).__name__}: {exc}"))



def extended_scan_inventory(report: Report, *, run_scans: bool) -> None:
    """Report advanced scanner availability and optionally execute safe scans.

    Production images intentionally remain small, so missing development tools
    are BLOCKED rather than silently treated as passed. A dedicated Railway
    certification service can install ``requirements-audit.txt`` and set
    ``DEPLOYMENT_EXTENDED_SCANS_ENABLED=1``.
    """
    tools: list[tuple[str, list[str] | None, str]] = [
        ("ruff", ["ruff", "check", "."], "Python lint/static analysis"),
        ("mypy", ["mypy", "core", "db", "engine", "services", "worker", "web", "signalrank_telegram"], "Python type analysis"),
        ("pyright", ["pyright"], "Python type analysis"),
        ("bandit", ["bandit", "-q", "-r", "core", "db", "engine", "services", "worker", "web", "signalrank_telegram"], "Python security analysis"),
        ("pip-audit", ["pip-audit", "-r", "requirements.txt"], "dependency CVE audit"),
        ("semgrep", ["semgrep", "scan", "--config", "auto", "--error", "--quiet"], "multi-language SAST"),
        ("vulture", ["vulture", "core", "db", "engine", "services", "worker", "web", "signalrank_telegram", "--min-confidence", "80"], "dead-code analysis"),
        ("shellcheck", ["shellcheck", "start.sh"], "shell analysis"),
        ("hadolint", ["hadolint", "Dockerfile", "Dockerfile.prod"], "container lint"),
    ]
    for executable, command, purpose in tools:
        path = shutil.which(executable)
        if not path:
            report.add(
                Check(
                    name=f"scanner_{executable}",
                    category="extended_scans",
                    status=BLOCKED,
                    severity="medium",
                    detail=f"not installed; purpose={purpose}",
                    remediation="Install requirements-audit.txt or the corresponding system package in an isolated certification service.",
                )
            )
            continue
        if not run_scans:
            report.add(
                Check(
                    name=f"scanner_{executable}",
                    category="extended_scans",
                    status=BLOCKED,
                    severity="medium",
                    detail=f"available={path}; use --extended-scans to execute",
                )
            )
            continue
        assert command is not None
        run_subprocess_check(
            report,
            name=f"scanner_{executable}",
            category="extended_scans",
            command=command,
            severity="high" if executable in {"bandit", "pip-audit", "semgrep"} else "medium",
            timeout=int(os.getenv("DEPLOYMENT_SCANNER_TIMEOUT_SECONDS", "600") or 600),
        )

    coverage_path = ROOT / ".coverage"
    if coverage_path.exists():
        run_subprocess_check(
            report,
            name="coverage_report",
            category="extended_scans",
            command=[sys.executable, "-m", "coverage", "report", "--show-missing"],
            severity="high",
            timeout=120,
        )
    else:
        report.add(
            Check(
                "coverage_report",
                "extended_scans",
                BLOCKED,
                "high",
                ".coverage data not present; run the coverage-enabled suite in the certification service",
            )
        )

    mutation_available = bool(shutil.which("mutmut"))
    if not mutation_available:
        report.add(Check("mutation_testing", "extended_scans", BLOCKED, "high", "mutmut not installed"))
    elif not _truthy("DEPLOYMENT_MUTATION_TESTS_ENABLED", False):
        report.add(Check("mutation_testing", "extended_scans", BLOCKED, "high", "set DEPLOYMENT_MUTATION_TESTS_ENABLED=1 in an isolated certification service"))
    elif run_scans:
        run_subprocess_check(
            report,
            name="mutation_testing",
            category="extended_scans",
            command=["mutmut", "run"],
            severity="high",
            timeout=int(os.getenv("DEPLOYMENT_MUTATION_TIMEOUT_SECONDS", "3600") or 3600),
        )


async def database_check(report: Report) -> None:
    if not _value("DATABASE_URL"):
        report.add(Check("postgresql", "live_dependencies", BLOCKED, "critical", "DATABASE_URL missing"))
        return

    started = time.monotonic()
    try:
        from sqlalchemy import text
        from db.session import get_pool_diagnostics, get_session

        async with get_session(
            priority="interactive",
            label="deployment_diagnostics.db",
            timeout_seconds=10,
        ) as session:
            one = (await session.execute(text("SELECT 1"))).scalar_one()
            revision = (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
            column = (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM information_schema.columns
                        WHERE table_name='decision_log' AND column_name='created_at'
                        """
                    )
                )
            ).scalar_one()
            active_duplicate_groups = (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM (
                            SELECT asset, direction, timeframe
                            FROM signals
                            WHERE status = 'active'
                            GROUP BY asset, direction, timeframe
                            HAVING COUNT(*) > 1
                        ) duplicate_groups
                        """
                    )
                )
            ).scalar_one()
            signal_runtime_columns = (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = 'signals'
                          AND column_name IN ('mfe_pct', 'mae_pct', 'performance_version')
                        """
                    )
                )
            ).scalar_one()
            active_guard_index = (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM pg_index AS i
                        JOIN pg_class AS idx ON idx.oid = i.indexrelid
                        JOIN pg_class AS tbl ON tbl.oid = i.indrelid
                        JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
                        WHERE ns.nspname = current_schema()
                          AND tbl.relname = 'signals'
                          AND idx.relname = 'ix_signals_active_thesis'
                          AND i.indisunique IS TRUE
                          AND pg_get_expr(i.indpred, i.indrelid) ILIKE '%status%'
                          AND pg_get_expr(i.indpred, i.indrelid) ILIKE '%active%'
                        """
                    )
                )
            ).scalar_one()
            outcome_duplicate_groups = (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM (
                            SELECT signal_id
                            FROM outcomes
                            GROUP BY signal_id
                            HAVING COUNT(*) > 1
                        ) duplicate_outcomes
                        """
                    )
                )
            ).scalar_one()
            outcome_guard_index = (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM pg_index AS i
                        JOIN pg_class AS idx ON idx.oid = i.indexrelid
                        JOIN pg_class AS tbl ON tbl.oid = i.indrelid
                        JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
                        WHERE ns.nspname = current_schema()
                          AND tbl.relname = 'outcomes'
                          AND idx.relname = 'uq_outcomes_signal_id'
                          AND i.indisunique IS TRUE
                        """
                    )
                )
            ).scalar_one()
            max_connections = int((await session.execute(text("SHOW max_connections"))).scalar_one() or 0)
            current_connections = int((
                await session.execute(
                    text("SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()")
                )
            ).scalar_one() or 0)
            queued_free = (
                await session.execute(
                    text("SELECT COUNT(*) FROM free_signal_queue WHERE status='queued'")
                )
            ).scalar_one()
            oldest_free = (
                await session.execute(
                    text(
                        """
                        SELECT MIN(queued_at)
                        FROM free_signal_queue
                        WHERE status='queued'
                        """
                    )
                )
            ).scalar_one_or_none()
            await session.rollback()

        expected = _expected_alembic_head()
        schema_ok = (
            one == 1
            and bool(revision)
            and int(column or 0) == 1
            and int(active_duplicate_groups or 0) == 0
            and int(signal_runtime_columns or 0) == 3
            and int(active_guard_index or 0) == 1
            and int(outcome_duplicate_groups or 0) == 0
            and int(outcome_guard_index or 0) == 1
            and (not expected or str(revision) == expected)
        )
        report.add(
            Check(
                name="postgresql_schema_and_admission",
                category="live_dependencies",
                status=PASS if schema_ok else FAIL,
                severity="critical",
                detail=(
                    f"select1={one} revision={revision} expected={expected} "
                    f"decision_log.created_at={column} "
                    f"active_duplicate_groups={active_duplicate_groups} "
                    f"signal_runtime_columns={signal_runtime_columns}/3 "
                    f"active_guard_unique_index={active_guard_index} "
                    f"outcome_duplicate_groups={outcome_duplicate_groups} "
                    f"outcome_guard_unique_index={outcome_guard_index}"
                ),
                duration_ms=int((time.monotonic() - started) * 1000),
                evidence={
                    "pool": get_pool_diagnostics(),
                    "active_duplicate_groups": int(active_duplicate_groups or 0),
                    "signal_runtime_columns": int(signal_runtime_columns or 0),
                    "active_guard_unique_index": bool(active_guard_index),
                    "outcome_duplicate_groups": int(outcome_duplicate_groups or 0),
                    "outcome_guard_unique_index": bool(outcome_guard_index),
                },
                remediation=(
                    None
                    if schema_ok
                    else (
                        "Run the sole Alembic head, confirm decision_log.created_at and "
                        "signals performance columns, reconcile duplicate active theses, "
                        "verify ix_signals_active_thesis and uq_outcomes_signal_id, "
                        "reconcile duplicate outcome projections, and inspect DB admission holders. "
                        "The fallback command is: "
                        "python scripts/repair_active_signal_duplicates.py --apply"
                    )
                ),
            )
        )

        pool_diag = get_pool_diagnostics()
        local_capacity = int(pool_diag.get("effective_pool_size") or 0) + int(pool_diag.get("effective_max_overflow") or 0)
        reserve = max(3, int(os.getenv("DB_PRODUCTION_CONNECTION_RESERVE", "5") or 5))
        available_headroom = max(0, int(max_connections or 0) - int(current_connections or 0))
        capacity_ok = bool(max_connections) and available_headroom >= max(1, local_capacity + reserve)
        report.add(
            Check(
                name="postgresql_capacity_headroom",
                category="live_dependencies",
                status=PASS if capacity_ok else FAIL,
                severity="high",
                detail=(
                    f"max_connections={max_connections} current={current_connections} "
                    f"available={available_headroom} local_pool_capacity={local_capacity} reserve={reserve}"
                ),
                evidence={
                    "max_connections": int(max_connections or 0),
                    "current_connections": int(current_connections or 0),
                    "available_headroom": int(available_headroom),
                    "local_pool_capacity": int(local_capacity),
                    "reserve": int(reserve),
                },
                remediation=(
                    None
                    if capacity_ok
                    else "Reduce the app pool, reduce concurrent services, add PgBouncer transaction pooling, or upgrade PostgreSQL before public launch. Do not add a second writable primary."
                ),
            )
        )

        free_enabled = _truthy("FREE_RANDOM_DISTRIBUTION_ENABLED", False) or _truthy(
            "FREE_SIGNAL_DISTRIBUTION_ENABLED", False
        )
        unsafe_queue = (not free_enabled) and int(queued_free or 0) > 0
        queue_status = PASS
        queue_severity = "high"
        if unsafe_queue:
            # A pre-deploy diagnostic must not prevent the corrected release from
            # being deployed solely because an older release left rows behind.
            # Runtime diagnostics fail until the rows are explicitly reconciled.
            queue_status = BLOCKED if report.phase == "predeploy" else FAIL
        report.add(
            Check(
                name="free_signal_queue_safety",
                category="delivery_queues",
                status=queue_status,
                severity=queue_severity,
                detail=(
                    f"queued={int(queued_free or 0)} distribution_enabled={free_enabled} "
                    f"oldest={oldest_free or ''}"
                ),
                evidence={
                    "queued_free_rows": int(queued_free or 0),
                    "oldest_queued_at": str(oldest_free or ""),
                },
                remediation=(
                    "Run scripts/quarantine_free_signal_queue.py in dry-run mode, review the rows, then use --apply if they are accidental staging/owner-test deliveries."
                    if unsafe_queue
                    else None
                ),
            )
        )
    except Exception as exc:
        report.add(
            Check(
                "postgresql_schema_and_admission",
                "live_dependencies",
                FAIL,
                "critical",
                f"{type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )


def _expected_alembic_head() -> str:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(ROOT / "alembic.ini"))
        heads = tuple(ScriptDirectory.from_config(cfg).get_heads())
        return heads[0] if len(heads) == 1 else ",".join(sorted(heads))
    except Exception:
        return ""


async def redis_check(report: Report, *, name: str, url: str) -> None:
    if not url:
        report.add(Check(name, "live_dependencies", BLOCKED, "critical", "URL missing"))
        return

    async def _run() -> Check:
        import redis.asyncio as redis

        client = redis.from_url(url, decode_responses=True, max_connections=2)
        key = f"signalrank:diagnostics:{name}:{int(time.time())}"
        try:
            pong = await asyncio.wait_for(client.ping(), timeout=5)
            await asyncio.wait_for(client.set(key, "ok", ex=30), timeout=5)
            value = await asyncio.wait_for(client.get(key), timeout=5)
            await asyncio.wait_for(client.delete(key), timeout=5)
            ok = bool(pong and value == "ok")
            return Check(name, "live_dependencies", PASS if ok else FAIL, "critical", f"ping={pong} roundtrip={value}")
        finally:
            await client.aclose()

    try:
        report.add(await _timed_async(_run))
    except Exception as exc:
        report.add(Check(name, "live_dependencies", FAIL, "critical", f"{type(exc).__name__}: {exc}"))



async def redis_delivery_queue_diagnostics(report: Report, *, url: str) -> None:
    """Inspect the known delivery queues without consuming or mutating work."""
    if not url:
        report.add(
            Check(
                "delivery_queue_backlog",
                "delivery_queues",
                BLOCKED,
                "critical",
                "DELIVERY_REDIS_URL missing",
            )
        )
        return

    try:
        import redis.asyncio as redis
    except Exception as exc:
        report.add(
            Check(
                "delivery_queue_backlog",
                "delivery_queues",
                FAIL,
                "critical",
                f"{type(exc).__name__}: {exc}",
                remediation="Install the locked Redis client dependency before deployment.",
            )
        )
        return

    stream_name = _value("TELEGRAM_UPDATES_STREAM") or "signalrank:telegram_updates:v1"
    group_name = _value("TELEGRAM_UPDATES_CONSUMER_GROUP") or "signalrank:telegram"
    dlq_name = _value("TELEGRAM_UPDATES_DLQ_STREAM") or "signalrank:telegram_updates:dead_letter:v1"
    legacy_key = _value("TELEGRAM_UPDATES_QUEUE_KEY") or "telegram_updates_queue"
    max_pending_age_ms = max(
        5_000,
        int(float(os.getenv("DEPLOYMENT_QUEUE_MAX_PENDING_AGE_SECONDS", "120") or 120) * 1000),
    )
    max_group_lag = max(0, int(os.getenv("DEPLOYMENT_QUEUE_MAX_GROUP_LAG", "10") or 10))
    started = time.monotonic()
    client = redis.from_url(url, decode_responses=True, max_connections=2)
    try:
        stream_depth = int(await asyncio.wait_for(client.xlen(stream_name), timeout=5) or 0)
        dlq_depth = int(await asyncio.wait_for(client.xlen(dlq_name), timeout=5) or 0)
        legacy_depth = int(await asyncio.wait_for(client.llen(legacy_key), timeout=5) or 0)
        group_info: dict[str, Any] | None = None
        try:
            groups = await asyncio.wait_for(client.xinfo_groups(stream_name), timeout=5)
            for row in groups or []:
                normalized = {
                    str(k.decode() if isinstance(k, bytes) else k): (
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in dict(row).items()
                }
                if str(normalized.get("name") or "") == group_name:
                    group_info = normalized
                    break
        except Exception as exc:
            # A missing stream/group before first startup is represented in the
            # report, not hidden as a successful empty queue.
            group_info = {"inspection_error": f"{type(exc).__name__}: {exc}"}

        pending_count = 0
        group_lag = 0
        last_delivered_id = "0-0"
        consumers = 0
        if group_info and "inspection_error" not in group_info:
            pending_count = int(group_info.get("pending") or 0)
            raw_lag = group_info.get("lag")
            group_lag = int(raw_lag or 0) if raw_lag is not None else 0
            last_delivered_id = str(group_info.get("last-delivered-id") or "0-0")
            consumers = int(group_info.get("consumers") or 0)

        pending_sample: list[dict[str, Any]] = []
        oldest_pending_idle_ms = 0
        if pending_count:
            try:
                rows = await asyncio.wait_for(
                    client.xpending_range(
                        stream_name,
                        group_name,
                        min="-",
                        max="+",
                        count=min(20, max(1, pending_count)),
                    ),
                    timeout=5,
                )
                for row in rows or []:
                    item = {
                        str(k.decode() if isinstance(k, bytes) else k): (
                            v.decode() if isinstance(v, bytes) else v
                        )
                        for k, v in dict(row).items()
                    }
                    idle_ms = int(
                        item.get("time_since_delivered")
                        or item.get("idle")
                        or item.get("idle_ms")
                        or 0
                    )
                    oldest_pending_idle_ms = max(oldest_pending_idle_ms, idle_ms)
                    pending_sample.append(
                        {
                            "message_id": str(item.get("message_id") or ""),
                            "consumer": str(item.get("consumer") or ""),
                            "idle_ms": idle_ms,
                            "times_delivered": int(item.get("times_delivered") or 0),
                        }
                    )
            except Exception as exc:
                pending_sample.append({"inspection_error": f"{type(exc).__name__}: {exc}"})

        oldest_unconsumed_age_ms = 0
        oldest_unconsumed_id = ""
        if group_lag > 0:
            try:
                rows = await asyncio.wait_for(
                    client.xrange(stream_name, min=f"({last_delivered_id}", max="+", count=1),
                    timeout=5,
                )
                if rows:
                    oldest_unconsumed_id = str(rows[0][0])
                    fields = dict(rows[0][1] or {})
                    enqueued_at_ms = int(fields.get("enqueued_at_ms") or 0)
                    if enqueued_at_ms:
                        oldest_unconsumed_age_ms = max(0, int(time.time() * 1000) - enqueued_at_ms)
            except Exception:
                pass

        group_missing = not group_info or "inspection_error" in group_info
        stale_pending = pending_count > 0 and oldest_pending_idle_ms >= max_pending_age_ms
        stale_lag = group_lag > max_group_lag and oldest_unconsumed_age_ms >= max_pending_age_ms
        unsafe = stale_pending or stale_lag or dlq_depth > 0 or legacy_depth > 0

        if group_missing and report.phase == "predeploy":
            status = SAFE_EXPECTED_OFF
            severity = "medium"
            detail_prefix = "consumer group not created yet (valid before first app startup)"
        elif group_missing:
            status = FAIL
            severity = "critical"
            detail_prefix = "consumer group missing or unreadable"
        elif unsafe and report.phase == "predeploy":
            status = BLOCKED
            severity = "high"
            detail_prefix = "existing backlog requires runtime reconciliation after deploy"
        elif unsafe:
            status = FAIL
            severity = "critical" if stale_pending or stale_lag else "high"
            detail_prefix = "stale or dead-lettered delivery work detected"
        else:
            status = PASS
            severity = "critical"
            detail_prefix = "delivery stream healthy"

        report.add(
            Check(
                name="delivery_queue_backlog",
                category="delivery_queues",
                status=status,
                severity=severity,
                detail=(
                    f"{detail_prefix}; stream_depth={stream_depth} pending={pending_count} "
                    f"lag={group_lag} oldest_pending_idle_ms={oldest_pending_idle_ms} "
                    f"oldest_unconsumed_age_ms={oldest_unconsumed_age_ms} "
                    f"dlq={dlq_depth} legacy_list={legacy_depth}"
                ),
                duration_ms=int((time.monotonic() - started) * 1000),
                evidence={
                    "stream": stream_name,
                    "group": group_name,
                    "dead_letter_stream": dlq_name,
                    "legacy_queue": legacy_key,
                    "stream_depth": stream_depth,
                    "pending_count": pending_count,
                    "group_lag": group_lag,
                    "consumers": consumers,
                    "last_delivered_id": last_delivered_id,
                    "oldest_pending_idle_ms": oldest_pending_idle_ms,
                    "oldest_unconsumed_id": oldest_unconsumed_id,
                    "oldest_unconsumed_age_ms": oldest_unconsumed_age_ms,
                    "dead_letter_depth": dlq_depth,
                    "legacy_list_depth": legacy_depth,
                    "pending_sample": pending_sample,
                    "group_info": group_info or {},
                },
                remediation=(
                    None
                    if status == PASS
                    else "Inspect consumer health and webhook rejection logs; reconcile pending/dead-letter work explicitly. Do not delete the stream blindly."
                ),
            )
        )
    except Exception as exc:
        report.add(
            Check(
                "delivery_queue_backlog",
                "delivery_queues",
                FAIL,
                "critical",
                f"{type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
    finally:
        await client.aclose()


async def redis_state_queue_diagnostics(report: Report, *, url: str) -> None:
    """Inspect the known state-side dispatch list without consuming it."""
    if not url:
        report.add(Check("signal_dispatch_queue", "delivery_queues", BLOCKED, "high", "STATE_REDIS_URL missing"))
        return
    try:
        import redis.asyncio as redis
    except Exception as exc:
        report.add(
            Check(
                "signal_dispatch_queue",
                "delivery_queues",
                FAIL,
                "high",
                f"{type(exc).__name__}: {exc}",
                remediation="Install the locked Redis client dependency before deployment.",
            )
        )
        return

    key = _value("SIGNAL_DISPATCH_QUEUE_KEY") or "signalrankai:signal_dispatch:queue"
    max_depth = max(1, int(os.getenv("DEPLOYMENT_SIGNAL_DISPATCH_MAX_DEPTH", "1000") or 1000))
    client = redis.from_url(url, decode_responses=True, max_connections=2)
    started = time.monotonic()
    try:
        depth = int(await asyncio.wait_for(client.llen(key), timeout=5) or 0)
        status = PASS if depth <= max_depth else FAIL
        report.add(
            Check(
                "signal_dispatch_queue",
                "delivery_queues",
                status,
                "high",
                f"depth={depth} threshold={max_depth}",
                duration_ms=int((time.monotonic() - started) * 1000),
                evidence={"key": key, "depth": depth, "threshold": max_depth},
                remediation=None if status == PASS else "Inspect delivery consumers and DB-backed delivery proof before replaying queued items.",
            )
        )
    except Exception as exc:
        report.add(Check("signal_dispatch_queue", "delivery_queues", FAIL, "high", f"{type(exc).__name__}: {exc}"))
    finally:
        await client.aclose()

async def telegram_check(report: Report) -> None:
    token = _value("TELEGRAM_BOT_TOKEN")
    secret = _value("TELEGRAM_WEBHOOK_SECRET")
    if not token:
        report.add(Check("telegram_api", "live_dependencies", BLOCKED, "critical", "TELEGRAM_BOT_TOKEN missing"))
        report.missing(name="Telegram staging bot", purpose="getMe/getWebhookInfo and callback delivery proof", env_vars=["TELEGRAM_BOT_TOKEN"])
        return

    async def _run() -> Check:
        from telegram import Bot

        async with Bot(token=token) as bot:
            me = await asyncio.wait_for(bot.get_me(), timeout=15)
            wh = await asyncio.wait_for(bot.get_webhook_info(), timeout=15)
            send_evidence: dict[str, Any] = {}
            if _truthy("DEPLOYMENT_TELEGRAM_SEND_TEST", False):
                chat_id = int(_value("DEPLOYMENT_TEST_CHAT_ID") or 0)
                if chat_id <= 0:
                    send_evidence = {"status": BLOCKED, "reason": "DEPLOYMENT_TEST_CHAT_ID missing"}
                else:
                    msg = await asyncio.wait_for(
                        bot.send_message(
                            chat_id=chat_id,
                            text=f"SignalRankAI deployment diagnostic {datetime.now(timezone.utc).isoformat()}",
                        ),
                        timeout=20,
                    )
                    send_evidence = {"status": PASS, "chat_id": chat_id, "message_id": int(msg.message_id)}
            expected_domain = _value("RAILWAY_PUBLIC_DOMAIN", "WEBHOOK_DOMAIN", "WEBHOOK_URL", "APP_BASE_URL")
            if expected_domain and not expected_domain.startswith("http"):
                expected_domain = f"https://{expected_domain}"
            expected_url = f"{expected_domain.rstrip('/')}/telegram/webhook" if expected_domain else ""
            url_ok = bool(wh.url) and (not expected_url or wh.url == expected_url)
            if report.phase == "predeploy":
                # The new container has not started yet, so first-deploy webhook
                # registration may legitimately still be absent. getMe and the
                # configured secret are the pre-deploy gates; runtime diagnostics
                # require the exact registered URL.
                ok = bool(me.id and secret)
            else:
                ok = bool(me.id and url_ok and secret and int(wh.pending_update_count or 0) < 100)
            return Check(
                name="telegram_api_and_webhook",
                category="live_dependencies",
                status=PASS if ok else FAIL,
                severity="critical",
                detail=f"bot=@{me.username} webhook_set={bool(wh.url)} pending={wh.pending_update_count} secret_configured={bool(secret)}",
                evidence={
                    "bot_id": int(me.id),
                    "username": me.username,
                    "webhook_url": wh.url,
                    "expected_url": expected_url,
                    "last_error_date": str(wh.last_error_date or ""),
                    "last_error_message": wh.last_error_message,
                    "send_test": send_evidence,
                },
                remediation=None if ok else "Set the webhook secret, correct the URL, and inspect webhook rejection diagnostics.",
            )

    try:
        report.add(await _timed_async(_run))
    except Exception as exc:
        report.add(Check("telegram_api_and_webhook", "live_dependencies", FAIL, "critical", f"{type(exc).__name__}: {exc}"))


def http_check(report: Report, base_url: str) -> None:
    if not base_url:
        report.add(Check("public_http", "postdeploy", BLOCKED, "high", "base URL missing"))
        return
    base = base_url.rstrip("/")
    for path, critical in (("/healthz", False), ("/livez", True), ("/readyz", True)):
        started = time.monotonic()
        attempts = 1
        if path == "/readyz":
            attempts = max(
                1,
                int(os.getenv("DEPLOYMENT_READINESS_RETRY_ATTEMPTS", "4") or 4),
            )
        retry_delay = max(
            0.0,
            float(os.getenv("DEPLOYMENT_READINESS_RETRY_DELAY_SECONDS", "2") or 2),
        )
        for attempt in range(1, attempts + 1):
            try:
                req = request.Request(f"{base}{path}", headers={"Accept": "application/json"})
                with request.urlopen(req, timeout=15) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    parsed = json.loads(body or "{}")
                    ok = response.status == 200
                    if path == "/readyz":
                        ok = ok and parsed.get("ready") is True
                    if not ok and attempt < attempts:
                        time.sleep(retry_delay)
                        continue
                    report.add(
                        Check(
                            name=f"http_{path.strip('/')}",
                            category="postdeploy",
                            status=PASS if ok else FAIL,
                            severity="critical" if critical else "high",
                            detail=f"status={response.status} attempts={attempt}",
                            duration_ms=int((time.monotonic() - started) * 1000),
                            evidence=parsed,
                        )
                    )
                    break
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                if attempt < attempts:
                    time.sleep(retry_delay)
                    continue
                report.add(
                    Check(
                        f"http_{path.strip('/')}",
                        "postdeploy",
                        FAIL,
                        "critical" if critical else "high",
                        f"HTTP {exc.code} after {attempt} attempts: {body[:1000]}",
                    )
                )
            except Exception as exc:
                if attempt < attempts:
                    time.sleep(retry_delay)
                    continue
                report.add(
                    Check(
                        f"http_{path.strip('/')}",
                        "postdeploy",
                        FAIL,
                        "critical" if critical else "high",
                        f"{type(exc).__name__} after {attempt} attempts: {exc}",
                    )
                )


def _external_certification_evidence(name: str) -> tuple[bool, dict[str, Any], str]:
    """Validate a named, redacted external proof file without making credentials equal proof."""
    env_name = "SIGNALRANK_CERTIFICATION_" + re.sub(r"[^A-Z0-9]+", "_", name.upper()) + "_EVIDENCE"
    raw_path = _value(env_name)
    if not raw_path:
        return False, {}, f"{env_name} is missing"
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        return False, {"reference": str(path)}, "evidence file does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, {"reference": str(path)}, f"invalid evidence JSON: {type(exc).__name__}"
    evidence_type = str(payload.get("evidence_type") or "").strip().lower()
    allowed_types = {"sandbox external", "live read-only", "live write canary"}
    ok = payload.get("status") == PASS and evidence_type in allowed_types
    evidence = {
        "reference": str(path),
        "evidence_type": evidence_type or None,
        "report_id": payload.get("report_id"),
        "release_commit": payload.get("release_commit"),
    }
    detail = "validated external proof" if ok else "proof must have status=PASS and an external evidence type"
    return ok, evidence, detail


def _not_in_scope_approved(name: str) -> bool:
    approved = {item.strip().lower() for item in _value("NOT_IN_SCOPE_INTEGRATIONS").split(",") if item.strip()}
    approval_id = _value("NOT_IN_SCOPE_OWNER_APPROVAL_ID")
    return bool(approval_id and name.lower() in approved)

def integration_inventory(report: Report) -> None:
    paystack_secret = str(os.getenv("PAYSTACK_SECRET_KEY") or "").strip().strip('"').strip("'")
    paystack_public = str(os.getenv("PAYSTACK_PUBLIC_KEY") or "").strip().strip('"').strip("'")
    paystack_mode = (
        "live"
        if paystack_secret.startswith("sk_live_") and paystack_public.startswith("pk_live_")
        else "test"
        if paystack_secret.startswith("sk_test_") and paystack_public.startswith("pk_test_")
        else "incomplete"
        if paystack_secret or paystack_public
        else "missing"
    )
    paystack_proof_ok, paystack_proof, paystack_proof_detail = _external_certification_evidence(
        f"paystack_{paystack_mode}"
    )
    report.add(
        Check(
            name=f"paystack_{paystack_mode}",
            category="optional_integrations",
            status=PASS if paystack_mode in {"live", "test"} and paystack_proof_ok else FAIL if paystack_mode == "incomplete" else BLOCKED,
            severity="high" if paystack_mode in {"live", "incomplete"} else "medium",
            detail=(
                f"key_pair={paystack_mode}; {paystack_proof_detail}"
                if paystack_mode in {"live", "test"}
                else "PAYSTACK_SECRET_KEY and PAYSTACK_PUBLIC_KEY must be a matching pair"
                if paystack_mode == "incomplete"
                else "Paystack keys are not configured"
            ),
            remediation=(
                None
                if paystack_mode in {"live", "test"}
                else "Set PAYSTACK_SECRET_KEY and PAYSTACK_PUBLIC_KEY using matching sk_/pk_ mode prefixes."
            ),
            evidence=paystack_proof,
            evidence_type=str(paystack_proof.get("evidence_type") or "integration"),
            required=True,
            required_profile=report.profile,
        )
    )

    optional = [
        ("gemini", ["GEMINI_API_KEY"], "AI review live call"),
        ("tradingview", ["TV_WEBHOOK_SECRET"], "signed alert ingress"),
        ("metaapi_demo", ["META_API_TOKEN"], "demo account quote/order/reconciliation"),
        ("provider_twelvedata", ["TWELVEDATA_API_KEY"], "forex/equity provider certification"),
        ("provider_polygon", ["POLYGON_API_KEY"], "equity/index provider certification"),
        ("provider_fmp", ["FMP_API_KEY"], "equity provider certification"),
        ("provider_oanda", ["OANDA_API_KEY", "OANDA_ACCOUNT_ID"], "forex practice certification"),
    ]
    profile_required = {
        "staging-certification": {name for name, _, _ in optional},
        "production-advisory": {"tradingview"},
        "production-live-owner-canary": {"tradingview", "metaapi_demo"},
    }.get(report.profile, set())
    profile_required.update(
        item.strip().lower()
        for item in _value("REQUIRED_CERTIFIED_INTEGRATIONS").split(",")
        if item.strip()
    )
    for name, envs, purpose in optional:
        configured = all(bool(_value(env)) for env in envs)
        proof_ok, proof, proof_detail = _external_certification_evidence(name)
        excluded = _not_in_scope_approved(name)
        required = name in profile_required and not excluded
        if configured and proof_ok:
            status = PASS
            detail = proof_detail
        elif excluded:
            status = NOT_IN_SCOPE
            detail = f"excluded by owner approval {_value('NOT_IN_SCOPE_OWNER_APPROVAL_ID')}"
        else:
            status = BLOCKED
            detail = f"configured={configured}; {proof_detail}"
        report.add(
            Check(
                name=name,
                category="optional_integrations",
                status=status,
                severity="medium",
                detail=detail,
                evidence=proof,
                evidence_type=str(proof.get("evidence_type") or "integration"),
                required=required,
                required_profile=report.profile,
            )
        )
        if not configured and required:
            report.missing(name=name, purpose=purpose, env_vars=envs)


def run_provider_certification(report: Report, providers: str) -> None:
    command = [sys.executable, "scripts/certify_providers.py", "--live", "--output-dir", "/tmp/signalrank-provider-certification"]
    if providers:
        command.extend(["--providers", providers])
    run_subprocess_check(
        report,
        name="live_provider_certification",
        category="providers",
        command=command,
        severity="high",
        timeout=300,
    )


def run_full_suite(report: Report, *, live_providers: bool, continue_on_failure: bool) -> None:
    output = "/tmp/signalrank-complete-system-test"
    command = [
        sys.executable,
        "scripts/run_complete_system_test.py",
        "--full",
        "--output-dir",
        output,
        "--pytest-batches",
        "1",
    ]
    if live_providers:
        command.append("--live-providers")
    if continue_on_failure:
        command.append("--continue-on-failure")
    run_subprocess_check(
        report,
        name="complete_system_orchestrator",
        category="full_suite",
        command=command,
        severity="critical",
        timeout=int(os.getenv("DEPLOYMENT_FULL_SUITE_TIMEOUT_SECONDS", "1800") or 1800),
    )


async def main_async(args: argparse.Namespace) -> int:
    report = Report(phase=args.phase, profile=args.profile)
    check_environment(report)
    static_checks(report)
    extended_scan_inventory(report, run_scans=args.extended_scans)
    integration_inventory(report)

    if args.phase in {"predeploy", "runtime", "full"}:
        await database_check(report)
        state_redis_url = _value("STATE_REDIS_URL", "REDIS_URL")
        delivery_redis_url = _value("DELIVERY_REDIS_URL")
        await redis_check(report, name="redis_state", url=state_redis_url)
        await redis_check(report, name="redis_delivery", url=delivery_redis_url)
        await redis_state_queue_diagnostics(report, url=state_redis_url)
        await redis_delivery_queue_diagnostics(report, url=delivery_redis_url)
        await telegram_check(report)

    if args.phase in {"runtime", "full"}:
        base = args.base_url or _value("RAILWAY_PUBLIC_DOMAIN", "WEBHOOK_DOMAIN", "WEBHOOK_URL", "APP_BASE_URL")
        if base and not base.startswith("http"):
            base = f"https://{base}"
        http_check(report, base)

    if args.live_providers:
        run_provider_certification(report, args.providers)
    else:
        proof_ok, proof, detail = _external_certification_evidence("live_provider_certification")
        required = report.profile == "staging-certification" or _truthy("REQUIRE_LIVE_PROVIDER_CERTIFICATION", False)
        status = PASS if proof_ok else BLOCKED if required else NOT_IN_SCOPE
        report.add(
            Check(
                "live_provider_certification",
                "providers",
                status,
                "high",
                detail,
                evidence=proof,
                evidence_type=str(proof.get("evidence_type") or "integration"),
                required=required,
                required_profile=report.profile,
            )
        )

    if args.run_full_suite:
        run_full_suite(report, live_providers=args.live_providers, continue_on_failure=args.continue_on_failure)
    else:
        proof_ok, proof, detail = _external_certification_evidence("full_system_e2e")
        required = report.profile == "staging-certification" or _truthy("REQUIRE_FULL_SYSTEM_E2E", False)
        status = PASS if proof_ok else BLOCKED if required else NOT_IN_SCOPE
        report.add(
            Check(
                "complete_system_orchestrator",
                "full_suite",
                status,
                "critical",
                detail,
                evidence=proof,
                evidence_type=str(proof.get("evidence_type") or "integration"),
                required=required,
                required_profile=report.profile,
            )
        )

    payload = report.payload()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"[deployment_diagnostics] report={output}")
    print(json.dumps(payload["summary"], sort_keys=True))

    failures = payload["summary"]["critical_or_high_failures"]
    if args.strict_core and failures:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("predeploy", "runtime", "full"), default="runtime")
    parser.add_argument("--profile", choices=("staging-certification", "production-advisory", "production-live-owner-canary"), default=os.getenv("SIGNALRANK_ENV_PROFILE", "production-advisory"))
    parser.add_argument("--base-url", default="")
    parser.add_argument("--output", default="artifacts/deployment-diagnostics.json")
    parser.add_argument("--strict-core", action="store_true")
    parser.add_argument("--live-providers", action="store_true")
    parser.add_argument("--providers", default=os.getenv("DEPLOYMENT_DIAGNOSTIC_PROVIDERS", "coinbase,okx"))
    parser.add_argument("--run-full-suite", action="store_true")
    parser.add_argument("--extended-scans", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
