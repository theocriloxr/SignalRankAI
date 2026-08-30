#!/usr/bin/env python3
"""Static release verifier for SignalRankAI v1.3.1."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *markers: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise SystemExit(f"FAIL {path}: missing {missing}")
    print(f"PASS {path}")


def main() -> int:
    require("core/version.py", 'CODE_VERSION = "1.3.2"', "v1.3.2-auto-delivery-callback-monitor-recovery-20260730")
    require(
        "core/financial_activation.py",
        "LIVE_FINANCIAL_FEATURES_ENABLED",
        "PAYSTACK_TRANSFERS_APPROVED_ACK",
        "PAYSTACK_TRANSFER_OTP_FLOW_ENABLED",
        "BYBIT_DEDICATED_ACCOUNT_ACK",
        "BYBIT_RECONCILIATION_ENABLED",
    )
    require(
        "services/bybit_client.py",
        "/v5/user/query-api",
        "/v5/order/create",
        "/v5/order/realtime",
        "/v5/position/closed-pnl",
    )
    require("services/bybit_signal_router.py", "reserve_user_execution_quota", "BrokerExecution", "ExecutionGate")
    require("services/bybit_reconciler.py", "reconcile_bybit_executions_once", "realized_pnl_pct")
    require("payments/payout_service.py", "/transferrecipient", "/transfer/finalize_transfer", "/transfer/verify/")
    require("web/app.py", '@app.post("/payout/request")', '@app.post("/payout/finalize")', '@app.get("/payout/verify/{reference}")')
    require(
        "db/migrations/versions/0029_live_financial_ledger.py",
        'revision = "0029_live_financial_ledger"',
        'sa.Column("realized_pnl_pct"',
        'sa.Column("closed_at"',
    )
    require(
        "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example",
        "DELIVERY_AUDIENCE_ALLOWLIST=",
        "VIP_SEAT_LIMIT=0",
        "PAYMENTS_PUBLIC_ENABLED=1",
    )
    require(
        "SignalRankAI_v1.3.2_Railway_Live_Financial_Activation.env.example",
        "REAL_EXECUTION_ENABLED=1",
        "AUTO_EXECUTION_ENABLED=1",
        "COPY_TRADE_ENABLED=1",
        "REAL_PAYOUTS_ENABLED=1",
        "AUTOMATIC_PAYOUTS_ENABLED=0",
    )
    print("overall=PASS release=v1.3.2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
