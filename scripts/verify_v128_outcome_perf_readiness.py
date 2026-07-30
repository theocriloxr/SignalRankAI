"""Static/runtime verifier for SignalRankAI v1.2.8."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, label: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL {label}")
    print(f"PASS {label}")


def main() -> int:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    from scripts.production_readiness_check import run_readiness_checks

    require(APP_VERSION == "1.2.9", "runtime version")
    require(
        RELEASE_FINGERPRINT == "v1.2.9-lifecycle-profile-observability-hotfix-20260730",
        "release fingerprint",
    )

    tracker = (ROOT / "engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    require("from sqlalchemy import func, select" in tracker, "outcome tracker SQL functions imported")
    require("signal_check_failed" in tracker, "lifecycle failures have a dedicated boundary")
    require("recipient_lookup_failed" in tracker, "recipient lookup failures have a dedicated boundary")
    require("SignalDelivery.sent_ok.is_(True)" in tracker, "performance recipients require delivery proof")
    require("func.lower(SignalDelivery.delivery_state)" in tracker, "delivery-state casing normalized")

    railway = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    metrics_idx = railway.index('@app.get("/metrics/prometheus"')
    mount_idx = railway.index('app.mount("/", _web_app)')
    require(metrics_idx < mount_idx, "direct Prometheus route precedes catch-all mount")

    readiness = run_readiness_checks(ROOT)
    require(readiness.get("ok") is True, "offline production readiness")
    checks = {item["name"]: item for item in readiness.get("checks", [])}
    require(checks.get("railway_direct_observability_routes", {}).get("ok") is True, "Railway direct observability routes")

    require((ROOT / "SignalRankAI_v1.2.9_Railway_Production_Launch.env.example").exists(), "production profile")
    require((ROOT / "SignalRankAI_v1.2.9_Railway_Full_System_Live_Paystack_Staging.env.example").exists(), "staging profile")
    print("PASS v1.2.8 outcome/performance/readiness verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
