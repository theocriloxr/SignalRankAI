"""Release verifier for SignalRankAI v1.3.0 production cutover."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, label: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {label}")


def main() -> int:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    from scripts.schema_audit import audit_outcome_projection_contract, audit_versions
    from scripts.validate_env_contract import validate

    require(APP_VERSION == "1.3.2", "runtime version")
    require(
        RELEASE_FINGERPRINT == "v1.3.2-auto-delivery-callback-monitor-recovery-20260730",
        "release fingerprint",
    )
    migrations = audit_versions(ROOT)
    require(migrations["ok"] is True, "migration graph")
    require(migrations["heads"] == ["0030_signal_monitor_reliability"], "migration head")
    require(audit_outcome_projection_contract(ROOT)["ok"] is True, "outcome projection guard")
    profile = ROOT / "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example"
    require(profile.exists(), "production profile")
    require(validate(profile) == [], "production environment contract")
    source = (ROOT / "db/pg_features.py").read_text()
    require("pg_advisory_xact_lock" in source, "outcome advisory lock")
    require("on_conflict_do_update" not in source[source.index("async def upsert_outcome"):], "no fragile outcome ON CONFLICT")
    print("PASS v1.3.0 production cutover verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
