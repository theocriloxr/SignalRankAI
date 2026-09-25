from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services import mt5_client
from services import mt5_reconciler


def _execution(**overrides):
    values = {
        "id": 7,
        "order_id": "order-1",
        "symbol": "EURUSD",
        "user_id": 11,
        "connection_id": "connection-1",
        "metaapi_account_id": "meta-account-1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_exact_deals_reject_same_symbol_from_another_position():
    deals = [
        {
            "id": "deal-a",
            "orderId": "order-1",
            "positionId": "position-1",
            "symbol": "EURUSD",
        },
        {
            "id": "deal-b",
            "orderId": "other-order",
            "positionId": "other-position",
            "symbol": "EURUSD",
        },
    ]
    exact = mt5_reconciler._exact_deals(
        deals,
        order_ref="order-1",
        position_ref="position-1",
    )
    assert [row["id"] for row in exact] == ["deal-a"]


def test_merge_deals_is_provider_id_idempotent():
    entry = {"id": "deal-1", "positionId": "position-1"}
    exit_ = {"id": "deal-2", "positionId": "position-1"}
    merged = mt5_reconciler._merge_deals([entry], [entry, exit_])
    assert [row["id"] for row in merged] == ["deal-1", "deal-2"]


def test_closing_deal_requires_explicit_metaapi_entry_type():
    deals = [
        {"id": "in", "entryType": "DEAL_ENTRY_IN", "profit": 0},
        {"id": "out", "entryType": "DEAL_ENTRY_OUT", "profit": 12.5},
        {"id": "unknown", "profit": 999},
    ]
    closing = mt5_reconciler._closing_deals(deals)
    assert [row["id"] for row in closing] == ["out"]


def test_financial_summary_preserves_provider_profit_commission_swap_and_fees():
    summary = mt5_reconciler._financial_summary(
        [
            {"profit": "0", "commission": "-0.40", "swap": "0"},
            {
                "profit": "15.25",
                "commission": "-0.40",
                "swap": "-0.15",
                "fee": "-0.05",
            },
        ]
    )
    assert str(summary["profit"]) == "15.25"
    assert str(summary["commission"]) == "-0.80"
    assert str(summary["swap"]) == "-0.15"
    assert str(summary["fees"]) == "-0.05"
    assert str(summary["net"]) == "14.25"


def test_ledger_events_are_stable_per_provider_deal():
    events = mt5_reconciler._ledger_events(
        [
            {
                "id": "deal-2",
                "orderId": "close-order",
                "positionId": "position-1",
                "entryType": "DEAL_ENTRY_OUT",
                "symbol": "EURUSD",
                "price": "1.10",
                "volume": "0.2",
                "profit": "12",
                "commission": "-0.3",
                "swap": "-0.1",
                "time": "2026-09-25T10:00:00.000Z",
            }
        ],
        execution=_execution(),
        position_ref="position-1",
        currency="USD",
    )
    by_type = {event["entry_type"]: event for event in events}
    assert {
        "fill",
        "realized_pnl",
        "commission",
        "swap",
    }.issubset(by_type)
    assert by_type["fill"]["source_event_id"] == "deal:deal-2:fill"
    assert by_type["realized_pnl"]["source_event_id"] == "deal:deal-2:profit"
    assert by_type["commission"]["source_event_id"] == "deal:deal-2:commission"
    assert by_type["swap"]["source_event_id"] == "deal:deal-2:swap"
    assert by_type["fill"]["position_ref"] == "position-1"


@pytest.mark.asyncio
async def test_provider_deals_discovers_position_from_exact_ticket(monkeypatch):
    async def ticket(account_id, ticket):
        assert account_id == "meta-account-1"
        assert ticket == "order-1"
        return [
            {
                "id": "entry-deal",
                "orderId": "order-1",
                "positionId": "position-1",
                "entryType": "DEAL_ENTRY_IN",
            }
        ]

    async def position(account_id, position_id):
        assert account_id == "meta-account-1"
        assert position_id == "position-1"
        return [
            {
                "id": "entry-deal",
                "orderId": "order-1",
                "positionId": "position-1",
                "entryType": "DEAL_ENTRY_IN",
            },
            {
                "id": "exit-deal",
                "orderId": "close-order",
                "positionId": "position-1",
                "entryType": "DEAL_ENTRY_OUT",
                "profit": "10",
            },
            {
                "id": "unrelated",
                "orderId": "other",
                "positionId": "other-position",
                "entryType": "DEAL_ENTRY_OUT",
                "profit": "500",
            },
        ]

    monkeypatch.setattr(mt5_reconciler, "get_history_deals_by_ticket", ticket)
    monkeypatch.setattr(mt5_reconciler, "get_history_deals_by_position", position)

    deals, position_ref = await mt5_reconciler._provider_deals(_execution())
    assert position_ref == "position-1"
    assert deals is not None
    assert [row["id"] for row in deals] == ["entry-deal", "exit-deal"]


def test_metaapi_history_time_is_url_safe_utc():
    encoded = mt5_client._metaapi_path_time(
        datetime(2026, 9, 25, 10, 11, 12, 345000, tzinfo=timezone.utc)
    )
    assert encoded == "2026-09-25T10%3A11%3A12.345Z"


@pytest.mark.asyncio
async def test_metaapi_ticket_history_uses_documented_rest_path(monkeypatch):
    captured = {}

    async def deploy(account_id):
        captured["deployed"] = account_id

    async def get(url, params=None):
        captured["url"] = url
        captured["params"] = params
        return [{"id": "deal-1"}]

    monkeypatch.setattr(mt5_client, "_deploy_account", deploy)
    monkeypatch.setattr(mt5_client, "_http_get", get)
    monkeypatch.setattr(
        mt5_client,
        "_client_base",
        lambda account_id=None: (
            f"https://example.test/users/current/accounts/{account_id}"
            if account_id
            else "https://example.test/users/current/accounts"
        ),
    )

    rows = await mt5_client.get_history_deals_by_ticket(
        "meta-account-1",
        "ticket/with spaces",
    )
    assert rows == [{"id": "deal-1"}]
    assert captured["deployed"] == "meta-account-1"
    assert captured["url"].endswith(
        "/history-deals/ticket/ticket%2Fwith%20spaces"
    )
