"""Verifier for SignalRankAI v1.2.9 lifecycle/profile/observability hotfix."""
from __future__ import annotations

import inspect
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, label: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def main() -> None:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    from engine.signal_lifecycle import record_lifecycle_event

    require(APP_VERSION == "1.3.0", "runtime version")
    require(RELEASE_FINGERPRINT == "v1.3.0-production-cutover-outcome-recovery-20260730", "fingerprint")
    lifecycle = inspect.getsource(record_lifecycle_event)
    require("from sqlalchemy import func, select" in lifecycle, "lifecycle func import")
    commands = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    require("maybe_prompt_timezone(update.message, user_id, user=timezone_user)" in commands, "profile timezone reuse")
    require('label="profile.read" if is_read else "profile.write"' in commands, "profile DB labels")
    require('pool.get("engine_inventory")' in commands, "pool inventory fallback")
    railway = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    require("BOT_READY_NOTIFICATION_DEDUPE_SECONDS" in railway and "nx=True" in railway, "ready notification dedupe")
    require((ROOT / "SignalRankAI_v1.3.0_Railway_Production_Launch.env.example").exists(), "production profile")
    require((ROOT / "SignalRankAI_v1.3.0_Railway_Full_System_Live_Paystack_Staging.env.example").exists(), "staging profile")
    print("PASS v1.2.9 lifecycle/profile/observability verification")


if __name__ == "__main__":
    main()
