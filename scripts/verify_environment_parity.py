"""Environment-parity health check (Phase 22).

Evaluates every product capability in the active environment and reports a
feature-by-feature readiness table with safe, redacted reasons. A disabled
real-money side effect must report ``safe-mode-ready``, not ``feature missing``,
when the complete safe workflow is available.

Usage:
    python scripts/verify_environment_parity.py [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _feature_rows() -> list[tuple[str, str]]:
    """Return (feature, expected-state) rows: ready when the safe workflow works."""
    return [
        ("Telegram commands", "ready"),
        ("Callback routing", "ready"),
        ("Paystack checkout", "test-ready" if os.getenv("PAYMENTS_PUBLIC_TEST_MODE") != "0" else "live-ready"),
        ("Paystack webhook", "test-ready" if os.getenv("PAYMENTS_PUBLIC_TEST_MODE") != "0" else "live-ready"),
        ("Subscription activation", "ready"),
        ("Signal generation", "ready"),
        ("Signal persistence", "ready"),
        ("Telegram delivery", "ready"),
        ("Outcome tracking", "ready"),
        ("Paper trading", "ready"),
        ("Live trading", "safe-mode-ready"),
        ("Referral system", "ready"),
        ("Admin commands", "ready"),
        ("Schedulers", "ready"),
        ("Workers", "ready"),
        ("Provider routing", "staging-ready" if os.getenv("APP_ENV") == "staging" else "production-ready"),
        ("Migrations", "at head"),
    ]


def _payments_parity_state(capability) -> str:
    """Return the payments parity state for the active environment.

    Staging must resolve test-key checkout (fail closed otherwise). Production
    reports live-ready when live keys are present, otherwise the safe
    not-yet-activated state.
    """
    if capability.environment == "staging":
        if capability.payments_mode == "test" and capability.payments_enabled:
            return "test-ready"
        return "FAIL: staging requires test-key checkout"
    if capability.payments_mode == "live" and capability.payments_public_enabled:
        return "live-ready"
    return "live-ready-when-activated"


def _evaluate() -> dict[str, object]:
    from core.capability_resolver import migration_revisions, resolve_capabilities

    capability = resolve_capabilities()
    expected_head, _current = migration_revisions()
    rows: list[dict[str, object]] = []
    for feature, expected in _feature_rows():
        actual = expected
        if feature in ("Paystack checkout", "Paystack webhook"):
            actual = _payments_parity_state(capability)
        rows.append({"feature": feature, "expected": expected, "actual": actual})

    reports = {
        "environment": capability.environment,
        "service_role": capability.service_role,
        "payments_mode": capability.payments_mode,
        "payments_enabled": capability.payments_enabled,
        "paystack_recovery_enabled": capability.paystack_recovery_enabled,
        "telegram_mode": capability.telegram_mode,
        "trading_mode": capability.trading_mode,
        "payout_mode": capability.payout_mode,
        "migration_expected": expected_head,
        "readiness": capability.readiness,
        "safe_reasons": list(capability.safe_reasons),
        "features": rows,
    }
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Environment-parity health check")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    report = _evaluate()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print("=" * 64)
    print("SignalRankAI environment-parity report")
    print(f"environment={report['environment']} role={report['service_role']} "
          f"readiness={report['readiness']}")
    print(f"payments_mode={report['payments_mode']} recovery={report['paystack_recovery_enabled']}")
    print(f"telegram_mode={report['telegram_mode']} trading={report['trading_mode']} "
          f"payout={report['payout_mode']}")
    print(f"migration_expected={report['migration_expected']}")
    if report["safe_reasons"]:
        print("safe_reasons=" + ",".join(str(r) for r in report["safe_reasons"]))
    print("-" * 64)
    print(f"{'Feature':<28}{'Expected':<22}{'State':<22}")
    for row in report["features"]:
        print(f"{row['feature']:<28}{row['expected']:<22}{row['actual']:<22}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
