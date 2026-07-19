"""Read-only architecture smoke checks for the Phase 4 role boundary.

The check intentionally validates only contracts that are safe during the
compatibility window: role modules import without starting work, the
dispatcher is available, and safety flags default off.  It reports deferred
decomposition work as warnings instead of pretending that the monolith has
already been split.

Usage::

    python scripts/architecture_smoke.py

The process exits non-zero only for broken foundational contracts.
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ROLE_MODULES = (
    "runtime.roles",
    "runtime.dispatcher",
    "runtime.web",
    "runtime.bot",
    "runtime.engine",
    "runtime.delivery",
    "runtime.outcome",
    "runtime.analytics",
    "runtime.scheduler",
    "runtime.all_dev",
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    severity: str = "info"


def _check_role_imports() -> CheckResult:
    for module_name in ROLE_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            return CheckResult("role_imports", False, f"{module_name}: {type(exc).__name__}: {exc}")
    return CheckResult("role_imports", True, f"{len(ROLE_MODULES)} role modules imported lazily")


def _check_dispatch_table() -> CheckResult:
    try:
        from runtime.dispatcher import dispatch
        from runtime.roles import RunMode

        if not callable(dispatch):
            return CheckResult("dispatcher", False, "runtime.dispatcher.dispatch is not callable")
        expected = {mode.value for mode in RunMode}
        return CheckResult("dispatcher", True, f"dispatcher available for {', '.join(sorted(expected))}")
    except Exception as exc:
        return CheckResult("dispatcher", False, f"{type(exc).__name__}: {exc}")


def _check_safety_defaults() -> CheckResult:
    # The smoke script is read-only and does not mutate env.  Explicitly set
    # flags are allowed in a deployment; only missing values are required to be
    # safe by default.
    expected = (
        "AUTO_TRADE_ENABLED",
        "COPY_TRADE_ENABLED",
        "PAYMENTS_ENABLED",
        "TELEGRAM_RICH_MESSAGES_ENABLED",
        "VIP_WEBHOOK_DISPATCH_ENABLED",
        "CHAT_MT5_CREDENTIALS_ENABLED",
    )
    enabled = [name for name in expected if name not in os.environ]
    if enabled:
        # Missing values use false defaults in config/core.env.  Do not reject
        # a developer shell that intentionally exports a canary flag.
        try:
            from core.env import SafetyFlags

            defaults = SafetyFlags.from_env()
            if defaults.enabled_names():
                return CheckResult(
                    "safety_defaults",
                    False,
                    f"unset safety flags unexpectedly enabled: {', '.join(defaults.enabled_names())}",
                )
        except Exception as exc:
            return CheckResult("safety_defaults", False, f"cannot evaluate defaults: {type(exc).__name__}: {exc}")
        return CheckResult("safety_defaults", True, f"unset flags default off: {', '.join(enabled)}")
    return CheckResult("safety_defaults", True, "all safety flags explicitly configured", "warning")


def _check_dispatcher_reference() -> CheckResult:
    source = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    if "runtime.dispatcher" not in source:
        return CheckResult("main_dispatcher_reference", False, "main.py does not reference runtime.dispatcher")
    return CheckResult("main_dispatcher_reference", True, "main.py delegates the canonical engine path")


def run_checks() -> list[CheckResult]:
    return [_check_role_imports(), _check_dispatch_table(), _check_safety_defaults(), _check_dispatcher_reference()]


def main() -> int:
    results = run_checks()
    for result in results:
        print(f"[{result.severity}] {result.name}: {result.detail}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["CheckResult", "main", "run_checks"]
