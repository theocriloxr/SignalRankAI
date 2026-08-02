#!/usr/bin/env python
"""Source-level verifier for the v1.3.6.6 runtime certification hotfix."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.version import APP_VERSION, RELEASE_FINGERPRINT  # noqa: E402
from ml.train_model import _promotion_quality_gate  # noqa: E402
from services.outcome_reconciliation import build_outcome_reconciliation_query  # noqa: E402


def check(name: str, condition: bool) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {name}")
    print(f"PASS: {name}")


def main() -> None:
    check("release version", APP_VERSION == "1.3.6.6")
    check(
        "release fingerprint",
        RELEASE_FINGERPRINT == "v1.3.6.6-runtime-certification-hotfix-20260802",
    )

    sql = str(
        build_outcome_reconciliation_query(
            cutoff=datetime(2026, 7, 1), limit=5000
        ).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()
    check("reconciliation avoids invalid DISTINCT ON", "DISTINCT ON" not in sql)
    check("reconciliation groups delivery proof", "GROUP BY SIGNAL_DELIVERIES.SIGNAL_ID" in sql)
    check("reconciliation selects missing outcomes", "OUTCOMES.ID IS NULL" in sql)

    quality_ok, min_accuracy, min_auc = _promotion_quality_gate(
        {"accuracy": 0.50, "auc": 0.575}, deployed_runtime=True
    )
    check("weak logged ML model rejected", not quality_ok)
    check("deployed ML accuracy threshold", min_accuracy == 0.55)
    check("deployed ML AUC threshold", min_auc == 0.60)

    training_source = (ROOT / "ml" / "train_model.py").read_text(encoding="utf-8")
    check(
        "calibration required for deployed promotion",
        "ML_PROMOTION_REQUIRES_VALID_CALIBRATION" in training_source
        and "status=candidate_only reason=calibration_unvalidated" in training_source,
    )

    bot_source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    snapshot_pos = bot_source.index("pending = run_sync(_fetch())")
    deadline_pos = bot_source.index(
        "_outcome_deadline = time.monotonic() + _outcome_budget_seconds",
        snapshot_pos,
    )
    check("notification budget starts after DB snapshot", deadline_pos > snapshot_pos)
    check(
        "notification market fetch fail-closed",
        'OUTCOME_NOTIFICATION_FETCH_MARKET_PRICE_FALLBACK", False' in bot_source,
    )

    router_source = (ROOT / "services" / "mt5_signal_router.py").read_text(encoding="utf-8")
    check(
        "master execution switches evaluated early",
        "Master execution flags" in router_source and "AUTO_TRADE_DISABLED" in router_source,
    )
    check(
        "real execution integrity retained",
        "evaluate_live_signal_admission" in router_source,
    )

    print(
        "overall=PASS release=v1.3.6.6 "
        "live_activation=BLOCKED_UNTIL_RUNTIME_CERTIFIED"
    )


if __name__ == "__main__":
    main()
