from scripts.live_production_evidence import _asset_class, _wilson_interval


def test_wilson_interval_for_sparse_sample_is_wide() -> None:
    low, high = _wilson_interval(9, 24)
    assert 0.20 < low < 0.25
    assert 0.55 < high < 0.60


def test_wilson_interval_empty_sample_returns_zero_bounds() -> None:
    assert _wilson_interval(0, 0) == (0.0, 0.0)


def test_asset_class_aliases_supported_markets() -> None:
    assert _asset_class("BTCUSDT") == "crypto"
    assert _asset_class("EURUSD") == "forex"
    assert _asset_class("XAUUSD") == "commodity"
    assert _asset_class("AAPL") in {"equity", "stock"}


def test_environment_requires_distinct_state_and_delivery_redis(monkeypatch) -> None:
    from scripts import live_production_evidence as module

    for key, value in {
        "DATABASE_URL": "postgresql://configured",
        "TELEGRAM_BOT_TOKEN": "configured",
        "TELEGRAM_WEBHOOK_SECRET": "configured",
        "OWNER_IDS": "1",
        "ENCRYPTION_KEY": "configured",
        "WEBHOOK_DOMAIN": "https://example.test",
        "STATE_REDIS_URL": "redis://same",
        "DELIVERY_REDIS_URL": "redis://same",
        "REQUIRE_DISTINCT_DELIVERY_REDIS": "1",
    }.items():
        monkeypatch.setenv(key, value)
    result = module.check_environment()
    assert result.ok is False
    assert "distinct DELIVERY_REDIS_URL" in result.detail


def test_environment_accepts_complete_distinct_topology(monkeypatch) -> None:
    from scripts import live_production_evidence as module

    for key, value in {
        "DATABASE_URL": "postgresql://configured",
        "TELEGRAM_BOT_TOKEN": "configured",
        "TELEGRAM_WEBHOOK_SECRET": "configured",
        "OWNER_IDS": "1",
        "ENCRYPTION_KEY": "configured",
        "WEBHOOK_DOMAIN": "https://example.test",
        "STATE_REDIS_URL": "redis://state",
        "DELIVERY_REDIS_URL": "redis://delivery",
        "REQUIRE_DISTINCT_DELIVERY_REDIS": "1",
    }.items():
        monkeypatch.setenv(key, value)
    result = module.check_environment()
    assert result.ok is True
    assert result.data["redis_distinct"] is True


def test_safe_error_does_not_echo_secret_text() -> None:
    from scripts.live_production_evidence import _safe_error

    marker = "redis://user:TOP_SECRET@private"
    assert _safe_error(RuntimeError(marker)) == "RuntimeError"
