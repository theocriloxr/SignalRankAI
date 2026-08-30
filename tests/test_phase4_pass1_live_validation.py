from datetime import datetime, timedelta, timezone


def _signal(**overrides):
    base = {
        "asset": "BNBUSDT",
        "timeframe": "5m",
        "direction": "BUY",
        "entry": 556.43,
        "stop_loss": 554.93,
        "take_profit": [559.42, 562.41, 565.40],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def test_time_to_telegraph_blocks_queue_expired(monkeypatch):
    from engine.delivery_freshness import evaluate_time_to_telegraph

    monkeypatch.setenv("DELIVERY_TIME_TO_TELEGRAPH_ENABLED", "1")
    monkeypatch.setenv("DELIVERY_QUEUE_MAX_AGE_CRYPTO_SECONDS", "30")
    old = datetime.now(timezone.utc) - timedelta(seconds=90)
    result = evaluate_time_to_telegraph(_signal(created_at=old.isoformat(), generated_at=old.isoformat()))
    assert not result.ok
    assert result.state == "EXPIRED_IN_QUEUE"
    assert "expired_in_queue" in result.reason


def test_time_to_telegraph_allows_fresh_signal(monkeypatch):
    from engine.delivery_freshness import evaluate_time_to_telegraph

    monkeypatch.setenv("DELIVERY_TIME_TO_TELEGRAPH_ENABLED", "1")
    monkeypatch.setenv("DELIVERY_QUEUE_MAX_AGE_CRYPTO_SECONDS", "60")
    fresh = datetime.now(timezone.utc) - timedelta(seconds=5)
    result = evaluate_time_to_telegraph(_signal(created_at=fresh.isoformat(), generated_at=fresh.isoformat()))
    assert result.ok
    assert result.state == "LIVE_QUEUE_CHECK_PASSED"


def test_live_price_provider_routing_stock_not_fx(monkeypatch):
    from data.get_live_price import _get_providers_for_asset

    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    providers = _get_providers_for_asset("META")
    assert providers[0] == "yahoo"
    assert "binance" not in providers[:1]


def test_live_price_provider_routing_metals_prioritizes_configured_broker(monkeypatch):
    from data.get_live_price import _get_providers_for_asset

    monkeypatch.setenv("META_API_TOKEN", "token")
    monkeypatch.setenv("META_API_MARKET_DATA_ACCOUNT_ID", "account")
    monkeypatch.setenv("OANDA_API_KEY", "key")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "account")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "key")
    providers = _get_providers_for_asset("XAGUSD")
    assert providers == ["metaapi", "oanda", "twelvedata", "yahoo"]


def test_live_price_provider_routing_skips_unconfigured_keyed_providers(monkeypatch):
    from data.get_live_price import _get_providers_for_asset

    for name in (
        "META_API_TOKEN", "META_API_MARKET_DATA_ACCOUNT_ID", "META_API_ACCOUNT_ID",
        "METAAPI_ACCOUNT_ID", "TELEGRAM_OWNER_ID", "OWNER_TELEGRAM_ID", "OWNER_IDS",
        "OANDA_API_KEY", "OANDA_TOKEN", "OANDA_ACCOUNT_ID",
        "TWELVEDATA_API_KEY", "TWELVE_DATA_API_KEY", "FCS_API_KEY", "FCS_API_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    assert _get_providers_for_asset("XAGUSD") == ["yahoo"]


def test_rich_message_builder_uses_table_and_details():
    from signalrank_telegram.rich_messages import build_signal_rich_html

    html = build_signal_rich_html(_signal(signal_id="abc123def456"))
    assert "<table>" in html
    assert "<details>" in html
    assert "TP1" in html
