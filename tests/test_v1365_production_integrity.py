from __future__ import annotations

import json
from pathlib import Path

import pytest


def _signal(**overrides):
    payload = {
        "asset": "BTCUSDT",
        "asset_class": "crypto",
        "direction": "short",
        "timeframe": "1h",
        "entry": 63000.0,
        "stop_loss": 63200.0,
        "take_profit": [62750.0, 62500.0, 62400.0],
        "strategy_name": "ema_trend",
        "regime": "trending",
        "score": 88.0,
        "quality_gate_passed": True,
        "ml_probability_calibrated": 0.67,
        "ml_calibration_version": "isotonic:model-2",
        "ml_calibration_validated": True,
        "ml_calibration_validation_rows": 250,
        "ml_calibration_brier": 0.16,
        "ml_calibration_ece": 0.04,
        "asset_discovery_provider": "coinbase,okx",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None),
    }
    payload.update(overrides)
    return payload


def test_thesis_fingerprint_collapses_tiny_repricing_but_not_material_move(monkeypatch):
    from core.production_integrity import signal_thesis_fingerprint

    monkeypatch.setenv("SIGNAL_THESIS_ENTRY_BAND_PCT", "0.003")
    first = signal_thesis_fingerprint(_signal(entry=63000.0))
    tiny = signal_thesis_fingerprint(_signal(entry=63001.0))
    moved = signal_thesis_fingerprint(_signal(entry=64000.0))
    assert first == tiny
    assert first != moved


def test_public_win_rate_claim_is_statistical_not_marketing(monkeypatch):
    from core.production_integrity import evaluate_public_win_rate_claim

    monkeypatch.setenv("PUBLIC_CLAIM_MIN_TERMINAL_SAMPLE", "200")
    monkeypatch.setenv("PUBLIC_CLAIM_MIN_UNIQUE_THESES", "100")
    monkeypatch.setenv("PUBLIC_CLAIM_MIN_TERMINAL_COVERAGE", "0.95")
    small = evaluate_public_win_rate_claim(
        wins=12, losses=8, delivered=20, resolved=20, unique_theses=20, target_rate=0.60
    )
    assert not small.allowed
    assert "sample" in small.reason
    supported = evaluate_public_win_rate_claim(
        wins=150, losses=50, delivered=205, resolved=200, unique_theses=200, target_rate=0.60
    )
    assert supported.allowed
    assert supported.lower_bound > 0.60


def test_public_probability_requires_validated_calibration(monkeypatch):
    from core.production_integrity import probability_for_public_display

    monkeypatch.setenv("ML_PROBABILITY_DISPLAY_REQUIRES_CALIBRATION", "1")
    hidden = probability_for_public_display(_signal(ml_calibration_validated=False))
    assert hidden.probability is None
    assert not hidden.calibrated
    shown = probability_for_public_display(_signal())
    assert shown.calibrated
    assert shown.probability == pytest.approx(0.67)
    assert shown.label == "Calibrated win probability"
    metric_failed = probability_for_public_display(_signal(ml_calibration_ece=0.30))
    assert metric_failed.probability is None
    assert not metric_failed.calibrated


def test_profile_filters_asset_timeframe_strategy_and_score():
    from services.user_intelligence import UserTradingPreferences, signal_matches_preferences

    prefs = UserTradingPreferences(
        trade_profile="day",
        risk_profile="balanced",
        asset_classes=("crypto",),
        preferred_assets=("BTCUSDT",),
        preferred_timeframes=("1h",),
        preferred_strategies=("ema",),
        min_signal_score=80,
    )
    assert signal_matches_preferences(_signal(), prefs) == (True, "ok")
    assert signal_matches_preferences(_signal(asset="ETHUSDT"), prefs)[0] is False
    assert signal_matches_preferences(_signal(timeframe="4h"), prefs)[0] is False
    assert signal_matches_preferences(_signal(strategy_name="breakout"), prefs)[0] is False
    assert signal_matches_preferences(_signal(score=79), prefs)[0] is False


def test_profile_payload_round_trip_keeps_strategy_filters():
    from services.user_intelligence import UserTradingPreferences, preferences_from_payload, preferences_to_payload

    original = UserTradingPreferences(
        preferred_assets=("BTCUSDT",),
        preferred_timeframes=("15m", "1h"),
        preferred_strategies=("breakout", "ema"),
        execution_mode="copy_trade",
        trading_mode="both",
    )
    restored = preferences_from_payload(preferences_to_payload(original))
    assert restored.preferred_strategies == original.preferred_strategies
    assert restored.execution_mode == "copy_trade"
    assert restored.trading_mode == "both"


def test_outcome_notifications_are_monotonic():
    from core.outcome_ordering import evaluate_outcome_delivery, outcome_stage_rank

    assert outcome_stage_rank("tp3") > outcome_stage_rank("tp2") > outcome_stage_rank("tp1")
    assert not evaluate_outcome_delivery("tp1", highest_delivered_rank=outcome_stage_rank("tp2")).allowed
    assert not evaluate_outcome_delivery("tp2", terminal_already_delivered=True).allowed
    assert evaluate_outcome_delivery("tp3", highest_delivered_rank=outcome_stage_rank("tp1")).allowed


def test_live_execution_fails_closed_until_certified(monkeypatch):
    from core.live_execution_integrity import evaluate_live_signal_admission

    for name in ("PRODUCTION_INTEGRITY_CERTIFIED", "LIVE_RUNTIME_CERTIFICATION_ID"):
        monkeypatch.delenv(name, raising=False)
    blocked = evaluate_live_signal_admission(_signal())
    assert not blocked.allowed
    monkeypatch.setenv("PRODUCTION_INTEGRITY_CERTIFIED", "1")
    monkeypatch.setenv("LIVE_RUNTIME_CERTIFICATION_ID", "runtime-cert-001")
    monkeypatch.setenv("LIVE_EXECUTION_REQUIRES_CALIBRATED_ML", "1")
    monkeypatch.setenv("LIVE_MIN_CALIBRATION_VALIDATION_ROWS", "100")
    allowed = evaluate_live_signal_admission(_signal())
    assert allowed.allowed, allowed.reasons


def test_asset_discovery_snapshot_distinguishes_trusted_and_manual(monkeypatch):
    import data.pair_discovery as discovery

    with discovery._ASSET_DISCOVERY_PROVENANCE_LOCK:
        discovery._ASSET_DISCOVERY_PROVENANCE.clear()
    discovery._record_provider_symbols(["BTCUSDT"], "okx")
    discovery._record_provider_symbols(["ETHUSDT"], "manual_config")
    monkeypatch.setattr(discovery, "get_latest_asset_universe", lambda force_refresh=False: {
        "crypto": ["BTCUSDT", "ETHUSDT"], "fx": [], "stocks": [], "indices": [], "commodities": []
    })
    monkeypatch.setattr(discovery, "_ASSET_UNIVERSE_LAST_REFRESH", __import__("time").time())
    snapshot = discovery.get_asset_discovery_snapshot()
    assert snapshot["trusted_provider_total"] == 1
    assert snapshot["untrusted_total"] == 1
    assert snapshot["providers"]["provider_backed"] is False


def test_coinbase_discovery_uses_public_catalog_and_liquidity(monkeypatch):
    import data.pair_discovery as discovery

    class Response:
        def __init__(self, payload, ok=True):
            self._payload = payload
            self.ok = ok
        def json(self):
            return self._payload

    calls = []
    def fake_get(url, **kwargs):
        calls.append(url)
        if url == discovery.COINBASE_PRODUCTS_API:
            return Response([
                {"id": "BTC-USD", "base_currency": "BTC", "quote_currency": "USD", "status": "online"},
                {"id": "ETH-USD", "base_currency": "ETH", "quote_currency": "USD", "status": "online"},
                {"id": "USDC-USD", "base_currency": "USDC", "quote_currency": "USD", "status": "online"},
            ])
        if "BTC-USD" in url:
            return Response({"volume": "1000", "last": "60000"})
        if "ETH-USD" in url:
            return Response({"volume": "100", "last": "3000"})
        return Response({"volume": "1", "last": "1"})

    monkeypatch.setattr(discovery.requests, "get", fake_get)
    monkeypatch.setenv("ASSET_DISCOVERY_MIN_QUOTE_VOLUME_USD", "100000")
    pairs = discovery._coinbase_top_crypto_pairs(2)
    assert pairs == ["BTCUSDT", "ETHUSDT"]
    assert discovery.COINBASE_PRODUCTS_API in calls
    assert any("/stats" in call for call in calls)


def test_model_metadata_reads_training_calibration_metrics(tmp_path):
    from ml.model_registry import extract_metadata

    payload = {
        "version": "2",
        "training_meta": {"metrics": {"auc": 0.8, "calibration": {"validated": True, "validation_rows": 250}}},
    }
    metadata = extract_metadata(payload)
    assert metadata["metrics"]["auc"] == 0.8
    assert metadata["calibration_metrics"]["validated"] is True


def test_paper_freshness_is_rechecked_at_fill_time():
    source = Path("core/paper_trading_service.py").read_text(encoding="utf-8")
    assert 'now=now_utc_naive(),\n                    purpose="paper"' in source
    assert 'deadline = generated_at + timedelta(seconds=freshness.max_age_seconds)' in source
    assert "duplicate_open_asset" in source
    assert "max_total_exposure" in source


def test_migration_enforces_paper_asset_uniqueness_and_calibration_fields():
    source = Path("db/migrations/versions/0034_production_integrity.py").read_text(encoding="utf-8")
    assert "uq_paper_open_user_asset" in source
    assert "ml_calibration_validated" in source
    assert "ml_calibration_validation_rows" in source
    assert "stage_rank" in source


def test_outcome_query_prioritizes_highest_stage():
    source = Path("db/pg_features.py").read_text(encoding="utf-8")
    assert "OutcomeNotification.stage_rank.desc()" in source

@pytest.mark.asyncio
async def test_profile_demand_includes_active_users_without_saved_preferences():
    from services.profile_demand import load_profile_demand

    class Result:
        def __init__(self, rows):
            self._rows = rows
        def all(self):
            return list(self._rows)

    class Session:
        def __init__(self):
            self.calls = 0
        async def execute(self, statement):
            self.calls += 1
            if self.calls == 1:
                return Result([])
            return Result([(1001,), (1002,)])

    snapshot = await load_profile_demand(Session())
    assert snapshot.active_profiles == 2
    assert set(snapshot.asset_classes) == {"crypto", "fx", "commodity", "index", "stock"}


def test_pending_outcomes_remain_eligible_for_tracking():
    source = Path("engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert 'func.lower(Outcome.status).in_([' in source
    assert '"pending"' in source
    assert '"active"' in source
    assert '"tp2"' in source


def test_delivery_integrity_fail_closed_controls_exist():
    source = Path("engine/core.py").read_text(encoding="utf-8")
    assert "DELIVERY_LIMIT_FAIL_CLOSED" in source
    assert "PROFILE_POLICY_FAIL_CLOSED" in source
    assert "DELIVERY_PRICE_VALIDATION_FAIL_CLOSED" in source
    assert 'continue\n                                # Non-production operators' in source


def test_performance_is_provisional_below_terminal_coverage():
    ledger = Path("services/performance_ledger.py").read_text(encoding="utf-8")
    command = Path("signalrank_telegram/commands.py").read_text(encoding="utf-8")
    assert "PERFORMANCE_CERTIFIED_MIN_TERMINAL_COVERAGE" in ledger
    assert '"performance_certified": performance_certified' in ledger
    assert "PROVISIONAL — NOT FOR PUBLIC CLAIMS" in command


def test_main_engine_persistence_path_enforces_canonical_thesis_integrity():
    source = Path("db/pg_features.py").read_text(encoding="utf-8")
    assert 'pg_advisory_xact_lock(hashtext(:fingerprint))' in source
    assert 'Signal.thesis_fingerprint == thesis_fingerprint' in source
    assert 'confirmed_delivery_count == 0' in source
    assert 'existing.entry = entry' in source
    assert 'thesis_fingerprint=thesis_fingerprint' in source
    for field in (
        'asset_discovery_provider=asset_discovery_provider',
        'ml_probability_raw=raw_probability',
        'ml_probability_calibrated=calibrated_probability',
        'ml_calibration_validated=calibration_validated',
        'ml_calibration_validation_rows=calibration_rows',
        'ml_calibration_brier=calibration_brier',
        'ml_calibration_ece=calibration_ece',
        'quality_gate_passed=quality_gate_passed',
    ):
        assert field in source


def test_integrity_migration_installs_pgcrypto_before_fingerprint_backfill():
    source = Path("db/migrations/versions/0034_production_integrity.py").read_text(encoding="utf-8")
    assert 'CREATE EXTENSION IF NOT EXISTS pgcrypto' in source
    assert source.index('CREATE EXTENSION IF NOT EXISTS pgcrypto') < source.index('SET thesis_fingerprint = encode(digest(')


def test_ml_calibration_uses_disjoint_temporal_windows():
    from ml.train_model import _temporal_three_way_indices

    train, calibration, validation = _temporal_three_way_indices(
        100,
        ordered_indices=list(range(100)),
        train_ratio=0.70,
        calibration_ratio=0.15,
    )
    assert len(train) == 70
    assert len(calibration) == 15
    assert len(validation) == 15
    assert set(train).isdisjoint(calibration)
    assert set(train).isdisjoint(validation)
    assert set(calibration).isdisjoint(validation)
    assert max(train) < min(calibration) < min(validation)


def test_calibration_evidence_is_persisted_and_serialized():
    repository = Path("db/repository.py").read_text(encoding="utf-8")
    bot = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    for field in (
        "ml_calibration_validated",
        "ml_calibration_validation_rows",
        "ml_calibration_brier",
        "ml_calibration_ece",
    ):
        assert field in repository
        assert field in bot


def test_fallback_delivery_paths_apply_profile_freshness_and_quality():
    source = Path("db/pg_features.py").read_text(encoding="utf-8")
    assert "_profile_and_integrity_filter_available_signals" in source
    assert 'purpose="delivery"' in source
    assert "signal_matches_preferences" in source
    assert "evaluate_signal_quality" in source
    assert "outcome_is_terminal" in source


def test_outcome_reconciliation_is_worker_owned():
    worker = Path("worker/worker.py").read_text(encoding="utf-8")
    bot = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    assert '"outcome_reconciliation"' in worker
    assert "ensure_outcome_projections" in worker
    assert "DATA_INTEGRITY_BACKFILL_INTERVAL_MINUTES" in bot
    assert "'360'" in bot


def test_delivery_dedup_serializes_user_asset_and_blocks_reservations():
    pg_source = Path("db/pg_features.py").read_text(encoding="utf-8")
    position_source = Path("services/asset_position_manager.py").read_text(encoding="utf-8")
    assert 'f"delivery:{int(user.id)}:{str(sig.asset).upper()}"' in pg_source
    assert 'delivery_reservation_active' in position_source
    assert '"reserved", "sending", "sent", "delivered", "confirmed", "updated"' in position_source


def test_supersede_does_not_mutate_confirmed_delivered_signal_rows():
    source = Path("db/pg_features.py").read_text(encoding="utf-8")
    assert 'confirmed_delivery_exists = (' in source
    assert '~confirmed_delivery_exists' in source


def test_internal_probability_resolution_prefers_validated_calibration():
    from engine.signal_metrics import resolve_ml_probability

    signal = {
        "ml_probability": 0.97,
        "ml_probability_raw": 0.97,
        "ml_probability_calibrated": 0.61,
        "ml_calibration_version": "isotonic:model-7",
        "ml_calibration_validated": True,
    }
    assert resolve_ml_probability(signal) == pytest.approx(0.61)
    signal["ml_calibration_validated"] = False
    assert resolve_ml_probability(signal) == pytest.approx(0.97)


def test_outcome_range_is_conservative_and_cannot_replay_pre_signal_candle():
    from datetime import datetime, timedelta, timezone
    from engine.realtime_outcome_tracker import (
        OutcomePriceObservation,
        _check_hit_observation,
        _range_is_new_for_signal,
    )

    # Both target and SL were touched inside one candle: stop-loss-first is the
    # conservative, non-inflating adjudication.
    assert _check_hit_observation(
        "long", 99.0, [101.0, 102.0, 103.0], 100.5, high=103.5, low=98.5
    ) == "sl"

    candle_start = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    signal = {"created_at": candle_start + timedelta(seconds=30)}
    observation = OutcomePriceObservation(
        asset="BTCUSDT",
        price=100.0,
        provider="coinbase",
        quote_time=None,
        provider_trusted=True,
        high=101.0,
        low=99.0,
        range_time=candle_start.isoformat(),
        range_trusted=True,
    )
    assert not _range_is_new_for_signal(signal, observation)


def test_shadow_tracking_is_worker_default_and_ambiguity_is_terminally_recorded():
    worker = Path("worker/worker.py").read_text(encoding="utf-8")
    shadow = Path("engine/shadow_outcome_worker.py").read_text(encoding="utf-8")
    assert '("SHADOW_OUTCOME_TRACKER_ENABLED", "WORKER_SHADOW_TRACKER_ENABLED"),\n            True,' in worker
    assert 'return row, "ambiguous"' in shadow


def test_live_activation_requires_each_integrity_certification(monkeypatch):
    from tests.test_v131_live_financial_activation import _full_env
    from core.financial_activation import evaluate_financial_activation

    for required in (
        "FRESHNESS_CERTIFICATION_ID",
        "PROFILE_ROUTING_CERTIFICATION_ID",
        "PAPER_TRADING_CERTIFICATION_ID",
        "OUTCOME_TRACKER_CERTIFICATION_ID",
        "PERFORMANCE_TRUTH_CERTIFICATION_ID",
    ):
        env = _full_env()
        env.pop(required)
        report = evaluate_financial_activation(env)
        assert not report.ok
        assert any((not check.ok) and required.split("_CERTIFICATION_ID")[0].lower().split("_")[0] in check.name for check in report.checks) or any(not check.ok for check in report.checks)


def test_manual_crypto_list_does_not_disable_provider_discovery(monkeypatch):
    import data.pair_discovery as discovery

    monkeypatch.setenv("CRYPTO_PAIRS", "MANUALUSDT")
    monkeypatch.setenv("ASSET_DISCOVERY_MODE", "auto")
    monkeypatch.delenv("RAILWAY_SERVICE_NAME", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.setattr(discovery, "_okx_top_crypto_pairs", lambda top_n: ["BTCUSDT"])
    monkeypatch.setattr(discovery, "_bybit_top_crypto_pairs", lambda top_n: [])
    monkeypatch.setattr(discovery, "_coinbase_top_crypto_pairs", lambda top_n: [])
    monkeypatch.setattr(discovery, "_cryptocompare_top_crypto_pairs", lambda top_n: [])
    monkeypatch.setattr(discovery, "_binance_top_crypto_pairs", lambda top_n: [])
    pairs = discovery.get_trending_crypto_pairs(5)
    assert pairs[0] == "BTCUSDT"
    assert "MANUALUSDT" in pairs


def test_shadow_and_pulse_truth_paths_are_wired():
    shadow = Path("engine/shadow_outcome_worker.py").read_text(encoding="utf-8")
    pulse = Path("engine/admin_pulse.py").read_text(encoding="utf-8")
    assert "candle_time < created_at" in shadow
    assert "Signals generated:" in pulse
    assert "Confirmed recipient deliveries:" in pulse
    assert "unclassified_reason" in pulse


def test_live_and_copy_routes_share_integrity_gate():
    mt5 = Path("services/mt5_signal_router.py").read_text(encoding="utf-8")
    bybit = Path("services/bybit_signal_router.py").read_text(encoding="utf-8")
    assert "evaluate_live_signal_admission" in mt5
    assert "evaluate_live_signal_admission" in bybit
    assert '"copy_trade"' in mt5
    assert '"copy_trade"' in bybit


def test_worker_continuously_reconciles_performance_ledgers():
    source = Path("worker/worker.py").read_text(encoding="utf-8")
    assert "reconcile_all_performance_ledgers" in source
    assert "performance_result.as_dict()" in source


def test_release_gates_shadow_and_engine_pulse_certification():
    release = Path("core/release_guard.py").read_text(encoding="utf-8")
    financial = Path("core/financial_activation.py").read_text(encoding="utf-8")
    assert "SHADOW_TRACKING_CERTIFICATION_ID" in release
    assert "ENGINE_PULSE_CERTIFICATION_ID" in release
    assert "SHADOW_TRACKING_CERTIFICATION_ID" in financial
    assert "ENGINE_PULSE_CERTIFICATION_ID" in financial


def test_production_readiness_requires_shadow_pulse_and_performance_health():
    source = Path("railway_main.py").read_text(encoding="utf-8")
    assert '"performance_ledger": performance_ledger' in source
    assert 'checks["engine_pulse"]' in source
    assert '_env_bool("SHADOW_OUTCOME_TRACKER_ENABLED", True)' in source


def test_public_performance_fails_closed_until_certified():
    source = Path("signalrank_telegram/commands.py").read_text(encoding="utf-8")
    assert 'if not report.get("performance_certified", False) and tier not in {"owner", "admin"}' in source
    assert "no provisional win rate" in source
    assert "Status: CERTIFICATION PENDING" in source


def test_paper_portfolio_circuit_breakers_are_wired():
    source = Path("core/paper_trading_service.py").read_text(encoding="utf-8")
    assert '"PAPER_MAX_DAILY_LOSS_PCT", 5.0' in source
    assert '"PAPER_MAX_OPEN_RISK_PCT", 3.0' in source
    assert 'reason="max_open_risk"' in source
    assert 'skip_reason = skip_reason or "paper_daily_loss_limit"' in source
