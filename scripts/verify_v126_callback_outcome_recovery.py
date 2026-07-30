"""Static/runtime verifier for SignalRankAI v1.2.7."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")
    print(f"PASS: {message}")


def main() -> None:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    from engine.realtime_outcome_tracker import _outcome_db_priority, _outcome_db_timeout

    require(APP_VERSION == "1.3.2", "runtime code version")
    require(RELEASE_FINGERPRINT == "v1.3.2-auto-delivery-callback-monitor-recovery-20260730", "release fingerprint")
    require(_outcome_db_priority() in {"critical", "interactive"}, "outcome DB foreground lane")
    require(_outcome_db_timeout() >= 1.0, "outcome DB admission timeout")

    bot_source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    require("refusing partial startup" in bot_source, "partial Telegram startup refused")
    require("immediate callback ack guard registered" in bot_source, "callback ACK guard present")

    outcome_source = (ROOT / "engine" / "realtime_outcome_tracker.py").read_text(encoding="utf-8")
    require("active_scan fetched=%d" in outcome_source, "outcome scan evidence")
    require("reconciliation_backfill fetched=%d" in outcome_source, "outcome reconciliation evidence")

    profile = ROOT / "SignalRankAI_v1.3.2_Railway_Full_System_Live_Paystack_Staging.env.example"
    require(profile.exists(), "v1.2.7 Railway staging profile")
    print("v1.2.7 verification complete")


if __name__ == "__main__":
    main()
