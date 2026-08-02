from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from core.env import SafetyFlags
from core.financial_activation import (
    LIVE_FINANCIAL_ACK_VALUE,
    PRODUCTION_EXECUTION_ACK_VALUE,
    BYBIT_DEDICATED_ACCOUNT_ACK_VALUE,
    REAL_PAYOUT_ACK_VALUE,
    PAYSTACK_TRANSFERS_ACK_VALUE,
    evaluate_financial_activation,
    force_invalid_financial_flags_off,
)
from core.version import APP_VERSION, RELEASE_FINGERPRINT
from execution.service import ExecutionGate, ExecutionRequest
from services.bybit_client import BybitCredentials, BybitPermissionError, BybitV5Client, InstrumentRules
from scripts.schema_audit import audit_versions

ROOT = Path(__file__).resolve().parents[1]


def _full_env() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    return {
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "APP_ENV": "production",
        "PUBLIC_TESTING_MODE": "0",
        "FULL_SYSTEM_STAGING_TEST_MODE": "0",
        "LIVE_FINANCIAL_FEATURES_ENABLED": "1",
        "LIVE_FINANCIAL_FEATURES_ACK": LIVE_FINANCIAL_ACK_VALUE,
        "PRODUCTION_EXECUTION_ACK": PRODUCTION_EXECUTION_ACK_VALUE,
        "LIVE_ACTIVATION_OWNER_TELEGRAM_ID": "1",
        "LIVE_EXECUTION_ALLOWED_TELEGRAM_USERS": "1",
        "LIVE_EXECUTION_ALLOWED_BROKER_ACCOUNTS": "owner-mt5,owner-bybit",
        "LIVE_EXECUTION_ALLOWED_PROVIDERS": "mt5,bybit",
        "LIVE_EXECUTION_ALLOWED_SYMBOLS": "EURUSD,BTCUSDT",
        "DEMO_CERTIFICATION_REPORT_ID": "demo-cert-pass-1",
        "LIVE_MAX_POSITION_SIZE": "0.01",
        "LIVE_MAX_DAILY_LOSS": "10",
        "LIVE_MAX_TOTAL_EXPOSURE": "50",
        "LIVE_ACTIVATION_STARTED_AT": (now - timedelta(minutes=1)).isoformat(),
        "LIVE_ACTIVATION_EXPIRES_AT": (now + timedelta(hours=1)).isoformat(),
        "REAL_EXECUTION_ENABLED": "1",
        "AUTO_EXECUTION_ENABLED": "1",
        "AUTO_TRADE_ENABLED": "1",
        "COPY_TRADE_ENABLED": "1",
        "MT5_ALLOW_LIVE_ACCOUNTS": "1",
        "BYBIT_EXECUTION_ENABLED": "1",
        "BYBIT_TESTNET": "0",
        "BYBIT_REQUIRE_IP_BINDING": "1",
        "BYBIT_DEDICATED_ACCOUNT_ACK": BYBIT_DEDICATED_ACCOUNT_ACK_VALUE,
        "BYBIT_RECONCILIATION_ENABLED": "1",
        "GLOBAL_EXECUTION_KILL_SWITCH": "0",
        "ENCRYPTION_KEY": "configured-fernet-key",
        "META_API_TOKEN": "configured-metaapi-token",
        "PAYMENTS_ENABLED": "1",
        "PAYMENTS_PUBLIC_ENABLED": "1",
        "REAL_PAYOUTS_ENABLED": "1",
        "REAL_PAYOUTS_ACK": REAL_PAYOUT_ACK_VALUE,
        "PAYOUT_MANUAL_APPROVAL_REQUIRED": "1",
        "AUTOMATIC_PAYOUTS_ENABLED": "0",
        "PAYSTACK_TRANSFERS_ENABLED": "1",
        "PAYSTACK_TRANSFERS_APPROVED_ACK": PAYSTACK_TRANSFERS_ACK_VALUE,
        "PAYSTACK_TRANSFER_OTP_FLOW_ENABLED": "1",
        "PAYSTACK_SECRET_KEY": "sk_live_configured",
        "PAYSTACK_PUBLIC_KEY": "pk_live_configured",
    }


def test_version_and_migration_head():
    assert APP_VERSION == "1.3.6"
    assert RELEASE_FINGERPRINT == "v1.3.6-railway-performance-decomposition-20260802"
    assert audit_versions(ROOT)["heads"] == ["0033_ml_learning_runtime"]


def test_financial_flags_off_are_safe():
    report = evaluate_financial_activation({"APP_ENV": "production"})
    assert report.requested is False
    assert report.ok is True


def test_partial_live_activation_is_forced_off():
    env = {"APP_ENV": "production", "REAL_EXECUTION_ENABLED": "1", "AUTO_TRADE_ENABLED": "1"}
    forced = force_invalid_financial_flags_off(env)
    assert "REAL_EXECUTION_ENABLED" in forced
    assert "AUTO_TRADE_ENABLED" in forced
    assert env["REAL_EXECUTION_ENABLED"] == "0"
    assert env["AUTO_TRADE_ENABLED"] == "0"


def test_full_live_activation_contract_passes():
    report = evaluate_financial_activation(_full_env())
    assert report.requested is True
    assert report.ok is True
    assert all(check.ok for check in report.checks if check.blocking)


def test_execution_gate_requires_auto_execution_master():
    flags = SafetyFlags(
        real_execution_enabled=True,
        auto_execution_enabled=False,
        auto_trade_enabled=True,
        bybit_execution_enabled=True,
    )
    request = ExecutionRequest(
        user_id=1,
        signal_id="sig",
        signal={"entry": 100, "stop_loss": 99, "direction": "long"},
        tier="VIP",
        mode="auto",
        consent=True,
        account_ready=True,
        quote_trusted=True,
        market_open=True,
        risk_allowed=True,
        evidence_allowed=True,
        account_id="acct",
        user_enabled=True,
        account_is_demo=False,
        credentials_encrypted=True,
        quote_age_seconds=0,
        broker_healthy=True,
        resources_available=True,
        reconciliation_ready=True,
        broker_provider="bybit",
    )
    decision = ExecutionGate(safety_flags=flags).preflight(request)
    assert not decision.allowed
    assert "AUTO_EXECUTION_DISABLED" in decision.reasons


def test_bybit_permission_policy_rejects_transfer():
    with pytest.raises(BybitPermissionError, match="withdraw_or_transfer"):
        BybitV5Client.validate_trade_only_permissions({
            "readOnly": 0,
            "permissions": {"ContractTrade": ["Order", "Position"], "Wallet": ["AccountTransfer"]},
            "ips": ["1.2.3.4"],
        })


def test_bybit_permission_policy_accepts_trade_only():
    result = BybitV5Client.validate_trade_only_permissions({
        "readOnly": 0,
        "permissions": {"ContractTrade": ["Order", "Position"]},
        "ips": ["1.2.3.4"],
    })
    assert result["trade"] is True
    assert result["withdraw"] is False
    assert result["ip_bound"] is True


def test_instrument_rules_round_down():
    rules = InstrumentRules("BTCUSDT", "linear", Decimal("0.10"), Decimal("0.001"), Decimal("0.001"))
    assert rules.quantize_qty(Decimal("0.0019")) == Decimal("0.001")
    assert rules.quantize_price(Decimal("100.19")) == Decimal("100.10")


@pytest.mark.asyncio
async def test_bybit_order_ack_is_confirmed_before_success():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/v5/market/instruments-info"):
            return httpx.Response(200, json={"retCode": 0, "result": {"list": [{
                "symbol": "BTCUSDT",
                "priceFilter": {"tickSize": "0.1"},
                "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "minNotionalValue": "5"},
            }]}})
        if request.url.path.endswith("/v5/market/tickers"):
            return httpx.Response(200, json={"retCode": 0, "result": {"list": [{"lastPrice": "100000"}]}})
        if request.url.path.endswith("/v5/order/create"):
            assert request.headers.get("X-BAPI-SIGN")
            body = json.loads(request.content.decode())
            assert body["orderLinkId"] == "sr-test"
            return httpx.Response(200, json={"retCode": 0, "result": {"orderId": "order-1"}})
        if request.url.path.endswith("/v5/order/realtime"):
            return httpx.Response(200, json={"retCode": 0, "result": {"list": [{"orderId": "order-1", "orderStatus": "New"}]}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = BybitV5Client(BybitCredentials("api-key-123", "api-secret-123", False), client=http_client)
        result = await client.place_market_order(
            symbol="BTCUSDT", side="buy", qty=Decimal("0.0024"),
            stop_loss=Decimal("99000.19"), take_profit=Decimal("101000.19"), order_link_id="sr-test",
        )
    assert result["success"] is True
    assert result["order_id"] == "order-1"
    assert [request.url.path for request in seen] == [
        "/v5/market/instruments-info", "/v5/market/tickers", "/v5/order/create", "/v5/order/realtime",
    ]


def test_live_and_public_env_profiles_document_all_flags():
    public = (ROOT / "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example").read_text(encoding="utf-8")
    live = (ROOT / "SignalRankAI_v1.3.2_Railway_Live_Financial_Activation.env.example").read_text(encoding="utf-8")
    for marker in (
        "APP_VERSION=1.3.2",
        "DELIVERY_AUDIENCE_ALLOWLIST=",
        "PAYMENTS_PUBLIC_ENABLED=1",
        "FREE_SIGNAL_DISTRIBUTION_ENABLED=1",
    ):
        assert marker in public
    for marker in (
        "LIVE_FINANCIAL_FEATURES_ENABLED=1",
        f"LIVE_FINANCIAL_FEATURES_ACK={LIVE_FINANCIAL_ACK_VALUE}",
        "REAL_EXECUTION_ENABLED=1",
        "AUTO_EXECUTION_ENABLED=1",
        "AUTO_TRADE_ENABLED=1",
        "COPY_TRADE_ENABLED=1",
        "MT5_ALLOW_LIVE_ACCOUNTS=1",
        "BYBIT_EXECUTION_ENABLED=1",
        "BYBIT_TESTNET=0",
        f"BYBIT_DEDICATED_ACCOUNT_ACK={BYBIT_DEDICATED_ACCOUNT_ACK_VALUE}",
        "BYBIT_RECONCILIATION_ENABLED=1",
        "REAL_PAYOUTS_ENABLED=1",
        "AUTOMATIC_PAYOUTS_ENABLED=0",
        "PAYOUT_MANUAL_APPROVAL_REQUIRED=1",
        f"REAL_PAYOUTS_ACK={REAL_PAYOUT_ACK_VALUE}",
        f"PAYSTACK_TRANSFERS_APPROVED_ACK={PAYSTACK_TRANSFERS_ACK_VALUE}",
        "PAYSTACK_TRANSFER_OTP_FLOW_ENABLED=1",
        "VIP_SEAT_LIMIT=0",
        "API_TOKEN_PEPPER=<random-long-api-token-pepper>",
        "DB_MAX_CONCURRENT_SESSIONS=2",
        "OUTCOME_TRACKER_MAX_CONCURRENCY=1",
        "BYBIT_API_KEY=<bybit-mainnet-api-key>",
        "TWELVEDATA_API_KEY=<twelve-data-api-key-with-commodity-access>",
        "OANDA_API_KEY=<oanda-v20-api-token>",
        "OANDA_ACCOUNT_ID=<oanda-v20-account-id>",
        "TV_WEBHOOK_SECRET=<random-long-tradingview-webhook-secret>",
        "TRADINGVIEW_ENABLED=1",
        "PAYSTACK_SECRET_KEY=<paystack-live-secret-key>",
        "PAYSTACK_PUBLIC_KEY=<paystack-live-public-key>",
    ):
        assert marker in live


def test_payout_routes_are_owner_controlled_and_otp_complete():
    source = (ROOT / "web" / "app.py").read_text(encoding="utf-8")
    assert 'recipient_telegram_user_id: int' in source
    assert '@app.post("/payout/request")' in source
    assert 'if not await _is_admin_user(int(user_id))' in source
    assert '@app.post("/payout/finalize")' in source
    assert 'PAYSTACK_TRANSFER_OTP_FLOW_ENABLED' in source
    assert '@app.get("/payout/verify/{reference}")' in source


def test_vip_enrollment_can_be_unlimited():
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    assert 'VIP_SEAT_LIMIT", "0"' in source
    assert 'Open enrollment' in source


def test_bybit_reconciliation_and_shared_quota_are_wired():
    worker = (ROOT / "worker" / "worker.py").read_text(encoding="utf-8")
    router = (ROOT / "services" / "bybit_signal_router.py").read_text(encoding="utf-8")
    reconciler = (ROOT / "services" / "bybit_reconciler.py").read_text(encoding="utf-8")
    migration = (ROOT / "db" / "migrations" / "versions" / "0029_live_financial_ledger.py").read_text(encoding="utf-8")
    assert 'BYBIT_RECONCILIATION_ENABLED' in worker
    assert 'reserve_user_execution_quota' in router
    assert '/v5/position/closed-pnl' in (ROOT / "services" / "bybit_client.py").read_text(encoding="utf-8")
    assert 'realized_pnl_pct' in reconciler
    assert 'sa.Column("realized_pnl_pct"' in migration
    assert 'sa.Column("closed_at"' in migration


def test_mt5_and_bybit_use_the_same_execution_quota_ledger():
    mt5 = (ROOT / "services" / "mt5_signal_router.py").read_text(encoding="utf-8")
    bybit = (ROOT / "services" / "bybit_signal_router.py").read_text(encoding="utf-8")
    shared = (ROOT / "services" / "execution_quota.py").read_text(encoding="utf-8")
    assert "from services.execution_quota import reserve_user_execution_quota" in mt5
    assert "reserve_user_execution_quota" in bybit
    assert "MT5Execution.realized_pnl_pct" in shared
    assert "BrokerExecution.realized_pnl_pct" in shared


def test_legacy_tier_executor_does_not_duplicate_canonical_ledger_writes():
    source = (ROOT / "engine" / "tiered_executor.py").read_text(encoding="utf-8")
    premium = source[source.index("async def execute_premium_signal"):source.index("async def execute_vip_signal")]
    vip = source[source.index("async def execute_vip_signal"):source.index("async def execute_for_user")]
    assert "_record_execution(" not in premium
    assert "_record_execution(" not in vip
    assert "daily_executions_today =" not in premium
