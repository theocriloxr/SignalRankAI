from datetime import datetime, timedelta, timezone
from dataclasses import replace
import math
import random

import pandas as pd
import pytest

from engine.adaptive.dataset import build_dataset
from engine.adaptive.integrity import audit_adaptive_dataset
from engine.adaptive.promotion import evaluate_profile_promotion
from engine.adaptive.statistics import (
    deflated_sharpe, probability_backtest_overfitting, return_diagnostics, block_bootstrap_survival,
)
from engine.adaptive.walk_forward import walk_forward_evaluate
from engine.backtest import BacktestEngine, BacktestRunner
from engine.wfo import WalkForwardOptimizer


def dataset(count=160):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [{"signal_id": str(i), "decision_time": start + timedelta(hours=i),
             "outcome_known_at": start + timedelta(hours=i, minutes=20),
             "r_multiple": -0.5 if i % 5 == 0 else 0.4, "family": "trend",
             "asset": "BTCUSDT", "regime": "trend", "evidence_category": "shadow",
             "sequence_hashes": [str(i)]} for i in range(count)]
    return build_dataset(rows)[0]


def wfo(rows):
    return walk_forward_evaluate(rows, family_weights={}, minimum_train=60, validation_size=20)


def test_overlapping_future_labels_are_purged_from_training():
    rows = list(dataset())
    rows[0] = replace(rows[0], r_multiple=500, outcome_known_at=rows[100].decision_time)
    first = wfo(rows).folds[0]
    assert first.purged_count >= 1
    assert first.train_outcome_end < first.validation_start
    altered = list(rows)
    altered[0] = replace(altered[0], r_multiple=-500)
    assert wfo(altered).folds[0] == first


def test_missing_label_availability_blocks_validation_and_integrity():
    rows = list(dataset())
    rows[3] = replace(rows[3], outcome_known_at=None)
    result = wfo(rows)
    assert not result.leakage_checks_passed and not result.folds
    assert "outcome_availability_unverified" in result.reasons
    assert not audit_adaptive_dataset(rows, result)["passed"]


def test_hash_lineage_does_not_claim_repainting_or_costs_verified():
    rows = dataset()
    checks = {item["check_id"]: item for item in audit_adaptive_dataset(rows, wfo(rows))["checks"]}
    assert checks["lookahead_and_repainting"]["status"] == "UNVERIFIED"
    assert checks["execution_fills"]["blocking"]
    assert checks["purged_chronology"]["status"] == "PASS"


@pytest.mark.parametrize("variant", ["duplicate", "mixed", "nan"])
def test_bad_observation_sets_fail_closed(variant):
    rows = list(dataset())
    if variant == "duplicate":
        rows[1] = replace(rows[1], signal_id=rows[0].signal_id)
    elif variant == "mixed":
        rows[1] = replace(rows[1], evidence_category="live_delivered")
    else:
        rows[1] = replace(rows[1], r_multiple=float("nan"))
    assert not wfo(rows).leakage_checks_passed


def test_dataset_revisions_include_label_availability_and_drop_unresolved():
    base = {"signal_id": "1", "decision_time": datetime(2026, 1, 1), "r_multiple": None}
    rows, manifest = build_dataset([base])
    assert not rows and manifest.row_count == 0
    base.update(r_multiple=0, outcome_known_at=datetime(2026, 1, 2))
    _, original = build_dataset([base])
    base["outcome_known_at"] = datetime(2026, 1, 3)
    _, corrected = build_dataset([base])
    assert original.content_hash != corrected.content_hash


def test_trial_count_penalizes_dsr_without_changing_annualization_math():
    rng = random.Random(71)
    returns = [rng.gauss(0.05, 1) for _ in range(500)]
    def evaluate(n, basis):
        return deflated_sharpe(returns, raw_trial_count=n, trial_sharpe_variance=0.03,
                              periods_per_year=basis, annualization_basis=f"{basis} uniform daily observations")
    single, many, crypto = evaluate(1, 252), evaluate(1000, 252), evaluate(1000, 365)
    assert many["deflated_sharpe_probability"] < single["deflated_sharpe_probability"]
    assert many["deflated_sharpe_probability"] == crypto["deflated_sharpe_probability"]
    assert crypto["annualized_sharpe"] / many["annualized_sharpe"] == pytest.approx(math.sqrt(365 / 252))
    assert many["effective_trial_count"] == 1000


def test_dependent_returns_do_not_qualify_via_iid_dsr():
    returns = [0.1 + i * 0.001 for i in range(100)]
    result = deflated_sharpe(returns, raw_trial_count=1, trial_sharpe_variance=0,
                           periods_per_year=252, annualization_basis="daily_session_excess_returns")
    assert result["deflated_sharpe_probability"] > 0.95
    assert not result["pass_fail"]


@pytest.mark.parametrize("n,variance,basis", [(0, 0.1, 252), (2, 0, 252), (2, -1, 252), (2, 0.1, 0)])
def test_dsr_rejects_unknown_or_invalid_trials(n, variance, basis):
    with pytest.raises(ValueError):
        deflated_sharpe([0.1, -0.05] * 30, raw_trial_count=n, trial_sharpe_variance=variance,
                        periods_per_year=basis, annualization_basis="daily")


def test_cscv_has_no_overfitting_for_consistently_dominant_candidate():
    matrix = [[0.1 + 0.01 * (i % 2), 0.005 + 0.1 * (-1) ** i] for i in range(16)]
    result = probability_backtest_overfitting(matrix, blocks=4)
    assert result["pbo"] == 0 and result["partitions"] == 6
    assert result["sample_visits"] == 16 * 2 * 6


def test_cscv_large_shapes_fail_before_copying_or_scoring_observations(monkeypatch):
    from engine.adaptive import statistics
    class LargeMatrix:
        def __len__(self):
            return 1280
        def __getitem__(self, index):
            return [0.1] * 32
        def __iter__(self):
            pytest.fail("oversized matrix must not be consumed")
    monkeypatch.setattr(statistics, "_values", lambda *args: pytest.fail("oversized data must not be normalized"))
    with pytest.raises(ValueError, match="cscv_compute_budget_exceeded"):
        statistics.probability_backtest_overfitting(LargeMatrix(), blocks=8)


@pytest.mark.parametrize("blocks", [True, 8.0, "8"])
def test_cscv_invalid_partition_types_cannot_start_work(blocks):
    with pytest.raises(ValueError, match="invalid_cscv_partition"):
        probability_backtest_overfitting([[0.1, -0.1]] * 16, blocks=blocks)


def test_boolean_trade_returns_cannot_become_performance_evidence():
    with pytest.raises(ValueError, match="boolean_research_observation"):
        return_diagnostics([True, False])


def test_oversized_return_series_fail_before_iteration():
    class OversizedSeries:
        def __len__(self):
            return 100_001
        def __iter__(self):
            pytest.fail("oversized return series must not be consumed")
    with pytest.raises(ValueError, match="invalid_research_sample"):
        return_diagnostics(OversizedSeries())


def test_cscv_refuses_unaligned_or_silently_truncated_partitions():
    with pytest.raises(ValueError):
        probability_backtest_overfitting([[0.1, -0.1]] * 9, blocks=4)


def test_drawdown_starts_at_initial_equity_and_tracks_open_underwater_duration():
    result = return_diagnostics([-1, -1, 3, -0.5, -0.5, 0.2])
    assert result["max_drawdown_r"] == 2
    assert result["max_drawdown_duration_observations"] == 3
    assert result["open_drawdown_duration_observations"] == 3
    assert result["annualized_sharpe"] is None


def test_survival_is_seeded_and_risk_sensitive_with_compute_bounds():
    returns = [-1] * 10 + [0.5] * 10
    kwargs = dict(block_size=5, horizon=100, runs=100, seed=31)
    small = block_bootstrap_survival(returns, risk_fraction=0.001, **kwargs)
    large = block_bootstrap_survival(returns, risk_fraction=0.02, **kwargs)
    assert small == block_bootstrap_survival(returns, risk_fraction=0.001, **kwargs)
    assert large["drawdown_breach_probability"] > small["drawdown_breach_probability"]
    with pytest.raises(ValueError, match="budget"):
        block_bootstrap_survival(returns, risk_fraction=0.01, block_size=5, horizon=10000, runs=10000)


def valid_promotion():
    return {"sample_size": 500, "positive_wfo_folds": 4, "fold_count": 5,
            "worst_fold_expectancy": 0, "expectancy_r": 0.2, "profit_factor": 1.4,
            "max_drawdown_r": 0, "brier_score": 0.2, "leakage_checks_passed": True,
            **{key: True for key in ("integrity_audit_passed", "trial_history_verified", "selection_bias_passed",
                                     "execution_stress_passed", "risk_survival_passed", "portfolio_validation_passed",
                                     "kill_conditions_approved")}}


@pytest.mark.parametrize("field,value", [("expectancy_r", float("nan")), ("max_drawdown_r", float("inf")),
                                         ("leakage_checks_passed", "true"), ("selection_bias_passed", "true"),
                                         ("worst_fold_expectancy", -1), ("fold_count", 40)])
def test_promotion_refuses_nan_truthy_strings_and_fold_instability(field, value):
    metrics = valid_promotion()
    metrics[field] = value
    assert not evaluate_profile_promotion(metrics, human_approved=True, current_state="PAPER", target_state="CANARY").eligible


def test_zero_drawdown_is_not_missing_but_missing_leakage_is_blocking():
    metrics = valid_promotion()
    assert evaluate_profile_promotion(metrics, human_approved=True, current_state="PAPER", target_state="CANARY").eligible
    metrics.pop("leakage_checks_passed")
    assert not evaluate_profile_promotion(metrics, human_approved=True, current_state="PAPER", target_state="CANARY").eligible


def signal():
    return {"asset": "TEST", "timeframe": "1m", "timestamp": pd.Timestamp("2026-01-01T00:02Z"),
            "direction": "long", "entry": 100, "stop_loss": 90, "take_profit": [110]}


def simulate(rows, sig=None, **kwargs):
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    runner = BacktestRunner()
    return WalkForwardOptimizer(runner)._simulate_pnl([sig or signal()], {"TEST|1m": frame},
           test_start=datetime(2026, 1, 1), test_end=datetime(2026, 1, 2), account_equity=1000, **kwargs)[0]


def test_execution_skips_predecision_bars_and_resolves_ambiguity_stop_first():
    result = simulate([
        {"timestamp": "2026-01-01T00:01Z", "open": 100, "high": 150, "low": 99, "close": 140, "volume": 100},
        {"timestamp": "2026-01-01T00:03Z", "open": 100, "high": 120, "low": 80, "close": 100, "volume": 100},
    ], commission_pct=0, slippage_pct=0)
    assert result["entry_execution_at"] > signal()["timestamp"].isoformat()
    assert result["same_bar_ambiguities"] == 1 and result["pnl"] < 0
    assert result["status"] == "CLOSED"


def test_exit_slippage_is_adverse_and_commission_uses_both_notionals():
    rows = [{"timestamp": "2026-01-01T00:03Z", "open": 100, "high": 111, "low": 99, "close": 110, "volume": 100}]
    costless = simulate(rows, commission_pct=0, slippage_pct=0)
    costs = simulate(rows, commission_pct=0.001, slippage_pct=0.001)
    quantity = costs["filled_quantity"]
    assert costs["pnl"] < costless["pnl"]
    assert costs["fee_cost"] == pytest.approx((100.1 + 109.89) * quantity * 0.001)


@pytest.mark.parametrize("direction,stop,target", [("long", 99, 110), ("short", 101, 90)])
def test_stop_replay_cannot_oversize_the_known_two_sided_execution_loss(direction, stop, target, monkeypatch):
    monkeypatch.setattr("engine.risk_manager.BASE_RISK_PCT", 0.5)
    sig = signal()
    sig.update(direction=direction, stop_loss=stop, take_profit=[target])
    result = simulate([{"timestamp": "2026-01-01T00:03Z", "open": 100, "high": 102,
                        "low": 98, "close": 100, "volume": 1000}], sig,
                      commission_pct=0.001, slippage_pct=0.02)
    assert result["status"] == "CLOSED" and result["pnl"] < 0
    assert result["risk_budget"] == pytest.approx(5)
    assert -result["pnl"] <= 5 + 1e-10
    assert result["modeled_stop_risk"] == pytest.approx(-result["pnl"])
    assert result["filled_quantity"] * result["fill_entry"] <= 100 + 1e-10
    assert result["risk_budget_breached"] is False


@pytest.mark.parametrize("direction,stop,target,gap", [("long", 99, 110, 70), ("short", 101, 90, 130)])
def test_market_gaps_retain_the_actual_loss_and_report_budget_breach(direction, stop, target, gap, monkeypatch):
    monkeypatch.setattr("engine.risk_manager.BASE_RISK_PCT", 0.5)
    sig = signal()
    sig.update(direction=direction, stop_loss=stop, take_profit=[target])
    result = simulate([
        {"timestamp": "2026-01-01T00:03Z", "open": 100, "high": 100.5, "low": 99.5, "close": 100, "volume": 1000},
        {"timestamp": "2026-01-01T00:04Z", "open": gap, "high": gap + 1, "low": gap - 1,
         "close": gap, "volume": 1000},
    ], sig, commission_pct=0.001, slippage_pct=0.02)
    assert result["status"] == "CLOSED"
    assert -result["pnl"] > result["risk_budget"]
    assert result["risk_budget_breached"] is True
    assert "gap_losses_not_bounded_by_stop" in result["limitations"]


def test_calendar_wfo_report_keeps_observed_risk_breaches_and_current_fill_policy(monkeypatch):
    from engine.backtest_execution import FILL_POLICY_VERSION
    runner = BacktestRunner()
    frame = pd.DataFrame([
        {"timestamp": "2026-02-01T00:03Z", "open": 100, "high": 100.5, "low": 99.5, "close": 100, "volume": 1000},
        {"timestamp": "2026-02-01T00:04Z", "open": 70, "high": 71, "low": 69, "close": 70, "volume": 1000},
    ])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    runner.register_dataframe("TEST", "1m", frame)
    sig = {**signal(), "timestamp": pd.Timestamp("2026-02-01T00:02Z"), "stop_loss": 99}
    monkeypatch.setattr(runner, "run_backtest", lambda *args, **kwargs: {"TEST": [sig]})
    reports = WalkForwardOptimizer(runner).run(["TEST"], ["1m"], train_months=1, test_months=1,
        start=datetime(2026, 1, 1), end=datetime(2026, 3, 1))
    assert len(reports) == 1 and reports[0]["completed_trades"] == 1
    assert reports[0]["risk_budget_breaches"] == 1
    assert reports[0]["fill_policy_version"] == FILL_POLICY_VERSION


@pytest.mark.parametrize("field,value", [("account_equity", True), ("account_equity", 0),
    ("commission_pct", True), ("commission_pct", 1), ("commission_pct", float("nan")),
    ("slippage_pct", True), ("slippage_pct", 1), ("slippage_pct", float("inf")), ("slippage_pct", -0.1)])
def test_invalid_execution_policy_is_not_a_usable_research_run(field, value):
    from engine.backtest_execution import simulate_signals
    policy = {"account_equity": 1000, "commission_pct": 0, "slippage_pct": 0, field: value}
    with pytest.raises(ValueError, match="invalid_backtest_execution_cost_or_equity"):
        simulate_signals([], {}, test_start=datetime(2026, 1, 1), test_end=datetime(2026, 1, 2), **policy)


def test_extreme_gap_cannot_publish_nonfinite_execution_metrics():
    sig = {**signal(), "direction": "short", "stop_loss": 101, "take_profit": [90]}
    with pytest.raises(ValueError, match="backtest_execution_arithmetic_overflow"):
        simulate([
            {"timestamp": "2026-01-01T00:03Z", "open": 100, "high": 100.5, "low": 99.5, "close": 100, "volume": 1000},
            {"timestamp": "2026-01-01T00:04Z", "open": 1.7e308, "high": 1.71e308, "low": 1.6e308,
             "close": 1.7e308, "volume": 1000},
        ], sig, commission_pct=0.001, slippage_pct=0.99)


def test_target_allocation_cannot_refill_on_subsequent_bars():
    sig = signal()
    sig["take_profit"] = [{"price": 110, "exit_percent": 50}, {"price": 120, "exit_percent": 50}]
    rows = [{"timestamp": f"2026-01-01T00:0{i}Z", "open": 100, "high": 111, "low": 99, "close": 110, "volume": 100} for i in range(3, 7)]
    result = simulate(rows, sig, commission_pct=0, slippage_pct=0)
    assert result["remaining_quantity"] == pytest.approx(result["filled_quantity"] * 0.5)
    assert result["win"] is None and result["status"] == "OPEN"


def test_no_liquidity_and_unverified_limit_orders_are_nonfills():
    rows = [{"timestamp": "2026-01-01T00:03Z", "open": 100, "high": 111, "low": 99, "close": 110, "volume": 0}]
    assert simulate(rows)["status"] == "NOT_FILLED"
    sig = signal()
    sig["order_type"] = "limit"
    rows[0]["volume"] = 100
    assert simulate(rows, sig)["status"] == "NOT_FILLED"


def test_backtest_cash_statistics_do_not_invent_daily_sharpe_or_equity_drawdown():
    engine = BacktestEngine()
    start = datetime(2026, 1, 1)
    engine.add_trade("TEST", 1, start, 100, start + timedelta(hours=1), 90, 1, 10)
    result = engine.calculate_metrics()
    assert result["max_drawdown"] == -10
    assert result["sharpe_ratio"] is None and result["max_drawdown_pct"] is None
    assert "None" in engine.get_summary()


def test_training_callback_cannot_read_future_rows_or_overlap_test_boundary(monkeypatch):
    times = pd.date_range("2026-01-01", "2026-04-01", freq="D", tz="UTC")
    runner = BacktestRunner()
    runner.register_dataframe("TEST", "1d", pd.DataFrame({"timestamp": times, "close": 100}))
    seen = []
    monkeypatch.setattr(runner, "run_backtest", lambda *args, **kwargs: {"TEST": []})
    def train(signals, frames):
        seen.append(frames["TEST|1d"]["timestamp"].max())
        return lambda sig: 0.5
    result = WalkForwardOptimizer(runner).run(["TEST"], ["1d"], train_months=1, test_months=1,
              start=datetime(2026, 1, 1), end=datetime(2026, 4, 1), train_callback=train)
    assert seen and all(cutoff < pd.to_datetime(fold["test_start"], utc=True) for cutoff, fold in zip(seen, result))


def test_research_model_uses_recorded_features_and_never_returns_a_fake_training_success(monkeypatch):
    from types import SimpleNamespace
    import engine.wfo as module
    runner = BacktestRunner()
    optimizer = WalkForwardOptimizer(runner)
    start = pd.Timestamp("2026-01-01T00:00Z")
    signals = [{"timestamp": start + pd.Timedelta(hours=i), "asset": "TEST", "timeframe": "1h",
                "_research_feature_available_at": start + pd.Timedelta(hours=i),
                "_research_features": {"feature_b": i + 1, "feature_a": i}} for i in range(32)]
    monkeypatch.setattr(optimizer, "_label_signals", lambda *args: {i: i % 2 for i in range(32)})
    matrices = []
    def matrix(values, **kwargs):
        matrices.append(values)
        return values
    fake = SimpleNamespace(DMatrix=matrix, train=lambda *args, **kwargs: SimpleNamespace(predict=lambda dm: [0.7]))
    monkeypatch.setattr(module, "xgb", fake)
    predictor = optimizer.default_train_xgb(signals, {})
    assert predictor(signals[-1]) == 0.7
    assert matrices[0].shape == (32, 2)
    assert matrices[0][0].tolist() == [0, 1], "feature order must be reproducible"
    signals[0]["_research_feature_available_at"] = start + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="availability_invalid"):
        optimizer.default_train_xgb(signals, {})
    monkeypatch.setattr(module, "xgb", None)
    with pytest.raises(RuntimeError, match="dependency_unavailable"):
        optimizer.default_train_xgb(signals, {})


def test_backtest_feature_snapshots_do_not_change_when_future_candles_change(monkeypatch):
    from types import SimpleNamespace
    runner = BacktestRunner()
    times = pd.date_range("2026-01-01", periods=62, freq="h", tz="UTC")
    frame = pd.DataFrame({"timestamp": times, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100})
    sig = SimpleNamespace(direction="long", entry=100, stop_loss=90, take_profit=[110], score=80,
                          strategy_name="audit", strategy_group="trend", confidence=0.8)
    monkeypatch.setattr(runner.signal_gen, "generate_signals", lambda *args: [sig])
    runner.register_dataframe("TEST", "1h", frame)
    before = runner.run_backtest(["TEST"], ["1h"], times[0].to_pydatetime(), (times[-1] + pd.Timedelta(hours=1)).to_pydatetime())["TEST"]
    frame.loc[61, ["close", "high"]] = [150, 151]
    runner.register_dataframe("TEST", "1h", frame)
    after = runner.run_backtest(["TEST"], ["1h"], times[0].to_pydatetime(), (times[-1] + pd.Timedelta(hours=1)).to_pydatetime())["TEST"]
    assert before[0]["_research_features"] == after[0]["_research_features"]
    assert before[-1]["_research_features"] != after[-1]["_research_features"]
    assert all(row["_research_feature_available_at"] <= row["timestamp"] for row in after)
