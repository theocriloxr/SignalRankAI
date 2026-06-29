"""Offline production readiness checks for SignalRankAI1.

This checker verifies launch-critical source artifacts without calling live
providers. It is meant to complement, not replace, sandbox/live deployment
checks from the production launch runbook.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_FILES = (
    "docs/GOVERNANCE_INDEX.md",
    "docs/PRODUCTION_LAUNCH_RUNBOOK.md",
    "docs/LIVING_DEPLOYMENT_REGISTER.md",
    "docs/PRODUCTION_READINESS_SCORECARD.md",
    "scripts/validate_governance_docs.py",
    "data/fetcher.py",
    "core/telemetry.py",
    "web/app.py",
    "signalrank_telegram/bot.py",
    "signalrank_telegram/commands.py",
)

REQUIRED_ENV_TEMPLATE_KEYS = (
    "DATABASE_URL",
    "TELEGRAM_BOT_TOKEN",
    "OWNER_IDS",
    "PAYSTACK_SECRET_KEY",
    "GEMINI_API_KEY",
)

REQUIRED_WEB_MARKERS = (
    '@app.get("/health"',
    '@app.get("/healthz"',
    '@app.get("/metrics/prometheus"',
)

REQUIRED_TELEMETRY_MARKERS = (
    "signalrank_service_up",
    "signalrank_http_request_seconds",
    "signalrank_engine_cycle_seconds",
    "signalrank_signal_dispatch_seconds",
)

REQUIRED_TELEGRAM_COMMAND_MARKERS = (
    'CommandHandler("start"',
    'CommandHandler("help"',
    'CommandHandler("signals"',
    'CommandHandler("upgrade"',
    'CommandHandler("ops_health"',
)

REQUIRED_REAL_DATA_MARKERS = (
    "real chart candles",
    "no demo/synthetic generation",
)


def _read(root: Path, rel_path: str) -> str:
    path = root / rel_path
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def run_readiness_checks(root: Path = ROOT) -> Dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    missing_files = [rel for rel in REQUIRED_FILES if not (root / rel).exists()]
    add("required_files", not missing_files, "missing=" + ",".join(missing_files) if missing_files else "all present")

    try:
        from scripts.validate_governance_docs import validate_governance_docs

        governance_errors = validate_governance_docs(root)
        add("governance_docs", not governance_errors, "errors=" + ",".join(governance_errors) if governance_errors else "valid")
    except Exception as exc:
        add("governance_docs", False, f"validator_error={exc}")

    env_text = (
        _read(root, ".env.production.template")
        + "\n"
        + _read(root, ".env.example")
        + "\n"
        + _read(root, "scripts/generate_railway_prefill_sheet.py")
        + "\n"
        + _read(root, "config.py")
    )
    missing_env = [key for key in REQUIRED_ENV_TEMPLATE_KEYS if key not in env_text]
    add("env_contracts", not missing_env, "missing=" + ",".join(missing_env) if missing_env else "required keys documented")

    web_text = _read(root, "web/app.py")
    missing_web = [marker for marker in REQUIRED_WEB_MARKERS if marker not in web_text]
    add("web_health_routes", not missing_web, "missing=" + ",".join(missing_web) if missing_web else "health and metrics routes present")

    telemetry_text = _read(root, "core/telemetry.py")
    missing_telemetry = [marker for marker in REQUIRED_TELEMETRY_MARKERS if marker not in telemetry_text]
    add("telemetry_markers", not missing_telemetry, "missing=" + ",".join(missing_telemetry) if missing_telemetry else "core metrics present")

    bot_text = _read(root, "signalrank_telegram/bot.py")
    missing_commands = [marker for marker in REQUIRED_TELEGRAM_COMMAND_MARKERS if marker not in bot_text]
    add("telegram_core_commands", not missing_commands, "missing=" + ",".join(missing_commands) if missing_commands else "core commands registered")

    fetcher_text = _read(root, "data/fetcher.py").lower()
    missing_real_data = [marker for marker in REQUIRED_REAL_DATA_MARKERS if marker not in fetcher_text]
    add(
        "actual_market_data_contract",
        not missing_real_data,
        "missing=" + ",".join(missing_real_data) if missing_real_data else "fetcher declares real chart candles with no demo/synthetic generation",
    )

    open_blockers = []
    for rel in ("docs/LIVING_TECHNICAL_DEBT_REGISTER.md", "docs/LIVING_RISK_REGISTER.md"):
        text = _read(root, rel)
        if "| High |" in text and "| Open |" in text:
            open_blockers.append(rel)
    add(
        "documented_high_risk_items",
        True,
        "open high-risk items documented in " + ",".join(open_blockers) if open_blockers else "no high-risk register markers found",
    )

    ok = all(check["ok"] for check in checks)
    return {"ok": ok, "checks": checks, "checked_count": len(checks)}


def main() -> int:
    result = run_readiness_checks()
    for check in result["checks"]:
        status = "PASS" if check["ok"] else "FAIL"
        print(f"{status} {check['name']}: {check['detail']}")
    print(f"overall={'PASS' if result['ok'] else 'FAIL'} checks={result['checked_count']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
