from pathlib import Path

from core.account_risk_presets import get_risk_preset
from core.tier_policy import evaluate_feature_access
from services.broker_connections import platform_catalog


ROOT=Path(__file__).resolve().parents[1]


def test_conservative_and_canary_risk_presets_are_bounded():
    conservative=get_risk_preset("conservative")
    canary=get_risk_preset("live_canary")
    assert str(conservative["max_risk_per_trade_pct"]) == "0.005"
    assert str(conservative["max_daily_loss_pct"]) == "0.02"
    assert str(conservative["max_weekly_loss_pct"]) == "0.04"
    assert str(conservative["max_total_drawdown_pct"]) == "0.06"
    assert conservative["max_open_positions"] == 3
    assert canary["max_risk_per_trade_pct"] < conservative["max_risk_per_trade_pct"]
    assert canary["max_open_positions"] == 1


def test_premium_can_connect_broker_but_auto_preflight_remains_vip():
    assert evaluate_feature_access("PREMIUM", "broker_connection").allowed is True
    assert evaluate_feature_access("PREMIUM", "execution_preflight").allowed is False
    assert evaluate_feature_access("VIP", "execution_preflight").allowed is True


def test_broker_catalogue_is_explicit_about_execution_readiness():
    rows={row["platform"]: row for row in platform_catalog("PREMIUM")}
    assert rows["mt5"]["execution_adapter"] == "ready"
    assert rows["bybit"]["execution_adapter"] == "ready"
    assert rows["binance"]["execution_adapter"] == "integration"
    assert rows["binanceus"]["execution_adapter"] == "integration"
    assert rows["okx"]["execution_adapter"] == "connection_only"
    assert rows["coinbase"]["execution_adapter"] == "connection_only"
    assert rows["kraken"]["execution_adapter"] == "connection_only"
    assert rows["mt5"]["connection_limit"] == 1


def test_first_party_platform_has_canonical_exchange_link_and_delivery_proof_gate():
    api=(ROOT/"web"/"platform_api.py").read_text(encoding="utf-8")
    assert '@router.post("/broker/exchange")' in api
    assert "register_platform_exchange_connection" in api
    execute=api[
        api.index('@router.post("/signals/{signal_id}/execute")'):
        api.index('@router.post("/signals/{signal_id}/feedback",')
    ]
    assert "signal_deliveries" in execute
    assert "notification_events" in execute
    assert "authorized_receipt" in execute
    assert "Signal not found in your authorized delivery history" in execute


def test_analytics_training_is_serialized_and_openai_probe_is_opt_in():
    source=(ROOT/"runtime"/"analytics.py").read_text(encoding="utf-8")
    assert "_ML_TRAIN_LOCK=asyncio.Lock()" in source
    assert source.count("_run_ml_training_serialized(") >= 3
    assert "OPENAI_STARTUP_PROBE_ENABLED" in source
    assert "[openai_startup_probe] status=PASS" in source
    # A stale Redis observation must not be used to refuse all future training.
    assert 'state.get_sync("signalrankai:ml:drift:retrain_running")' not in source


def test_new_account_defaults_match_conservative_policy():
    service=(ROOT/"services"/"account_policies.py").read_text(encoding="utf-8")
    api=(ROOT/"web"/"platform_api.py").read_text(encoding="utf-8")
    for source in (service, api):
        assert 'Decimal("0.005")' in source
        assert 'Decimal("0.02")' in source
        assert 'Decimal("0.04")' in source
        assert 'Decimal("0.06")' in source
    canonical=(ROOT/"core"/"account_policy.py").read_text(encoding="utf-8")
    assert 'field_name="max_daily_loss_pct",\n            default="0.02",' in canonical
    assert 'field_name="max_weekly_loss_pct",\n            default="0.04",' in canonical
    assert 'field_name="max_total_drawdown_pct",\n            default="0.06",' in canonical


def test_adaptive_candle_store_uses_short_transaction_default():
    source=(ROOT/"engine"/"adaptive"/"candle_store.py").read_text(encoding="utf-8")
    assert 'os.getenv("ADAPTIVE_CANDLE_UPSERT_CHUNK_SIZE", "50")' in source
    assert "for offset in range(0, len(records), chunk_size):" in source
    loop=source.index("for offset in range(0, len(records), chunk_size):")
    commit=source.index("await session.commit()", loop)
    assert commit > loop
    # The per-chunk session must be inside the chunk loop rather than wrapping
    # the entire initial history backfill in a single transaction.
    session=source.index("async with get_session(", loop)
    assert loop < session < commit
