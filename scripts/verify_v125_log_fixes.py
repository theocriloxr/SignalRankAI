"""Static/runtime verifier for the v1.2.5 log-driven release."""
from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")
    print(f"PASS: {message}")


def main() -> int:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    require(APP_VERSION == "1.2.5", "runtime code version is v1.2.5")
    require(RELEASE_FINGERPRINT == "v1.2.5-live-paystack-delivery-adaptive-telemetry-20260729", "release fingerprint")

    helpers = importlib.import_module("engine.adaptive.helpers")
    for name in ("atr", "confirmed_pivots", "fingerprint", "ohlcv", "targets"):
        require(callable(getattr(helpers, name, None)), f"adaptive helper export {name}")

    from runtime_safety import apply_runtime_safety_environment
    env = {
        "APP_ENV": "staging",
        "FULL_SYSTEM_STAGING_TEST_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_ACK": "I_UNDERSTAND_STAGING_TESTS_CAN_TRIGGER_EXTERNAL_ACTIONS",
        "FULL_SYSTEM_TEST_USER_IDS": "1409578077",
        "PAYSTACK_LIVE_STAGING_ENABLED": "1",
        "PAYSTACK_LIVE_STAGING_ACK": "I_UNDERSTAND_PAYSTACK_LIVE_KEYS_MOVE_REAL_MONEY",
        "PAYSTACK_LIVE_STAGING_ALLOWED_USER_IDS": "1409578077",
        "PAYSTACK_LIVE_STAGING_MAX_AMOUNT_NGN": "56000",
        "PAYSTACK_SECRET_KEY": "sk_live_forbidden_example",
        "PAYSTACK_PUBLIC_KEY": "pk_live_forbidden_example",
    }
    result = apply_runtime_safety_environment(env)
    require(result.full_system_test_enabled, "full-system staging acknowledgement")
    require(env.get("PAYSTACK_LIVE_STAGING_ACTIVE") == "1", "guarded live Paystack staging active")
    require(env.get("PAYMENTS_PUBLIC_TEST_MODE") == "0", "Paystack live-mode marker")

    from payments.paystack_policy import evaluate_paystack_operation
    require(evaluate_paystack_operation(telegram_user_id=1409578077, amount_ngn=56000, environ=env).allowed, "owner live checkout at cap")
    require(not evaluate_paystack_operation(telegram_user_id=1409578077, amount_ngn=56001, environ=env).allowed, "amount above cap blocked")
    require(not evaluate_paystack_operation(telegram_user_id=999, amount_ngn=1000, environ=env).allowed, "non-allowlisted user blocked")

    from data.fetcher import validate_price_sanity
    require(validate_price_sanity("WTI", 84.3), "valid WTI price accepted")
    require(not validate_price_sanity("WTI", 3.535), "ghost WTI token price rejected")

    from engine.signal_deduplicator import _json_safe, get_ml_rejection_tracker
    stamp = datetime(2026, 7, 29, 22, 26, tzinfo=timezone.utc)
    require(_json_safe({"t": stamp})["t"] == stamp.isoformat(), "rejection features are JSON-safe")
    require(get_ml_rejection_tracker() is get_ml_rejection_tracker(), "ML rejection tracker singleton")

    bot_source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    require("TEST ONLY — NOT EXECUTION ELIGIBLE" in bot_source, "staging freshness advisory label")
    require("[autoexec] blocked staging/test-only signal" in bot_source, "live execution blocked for advisory messages")

    profile = ROOT / "SignalRankAI_v1.2.5_Railway_Full_System_Live_Paystack_Staging.env.example"
    require(profile.exists(), "v1.2.5 Railway staging profile")
    print("v1.2.5 verification complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
