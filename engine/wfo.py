from datetime import datetime, timedelta
from typing import Iterable, Dict, Any
import pandas as pd

from engine.backtest import BacktestRunner
from typing import Callable
from ml.features import extract_features
from engine.backtest_execution import FILL_POLICY_VERSION, fixed_bar_duration

try:
    import xgboost as xgb
except Exception:
    xgb = None

import numpy as np
import math


def _month_ranges(start: datetime, end: datetime):
    cur = datetime(start.year, start.month, 1, tzinfo=start.tzinfo)
    while cur < end:
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield cur, nxt
        cur = nxt


class WalkForwardOptimizer:
    """Simple walk-forward optimizer that runs rolling train/test windows.

    Usage: provide data in BacktestRunner (registered DataFrames). The WFO
    will call optional train_callback(train_df) and then evaluate on test
    window using a simple backtest PnL simulator.
    """

    def __init__(self, runner: BacktestRunner):
        self.runner = runner

    @staticmethod
    def _timeframe_minutes(timeframe: str | None) -> int:
        return int(fixed_bar_duration(timeframe if timeframe is not None else "1m").total_seconds() / 60)

    @staticmethod
    def _average_daily_volume_notional(
        df: pd.DataFrame | None, timeframe: str | None, price_fallback: float = 1.0
    ) -> float:
        if df is None or df.empty or "volume" not in df.columns:
            return 0.0
        try:
            volume = df["volume"]
            if not isinstance(volume, pd.Series):
                raise ValueError("ambiguous_volume_column")
            numeric_volume = pd.to_numeric(volume, errors="coerce")
            if not isinstance(numeric_volume, pd.Series):
                raise ValueError("invalid_volume_series")
            avg_bar_volume = float(numeric_volume.dropna().tail(1000).mean() or 0.0)
        except Exception:
            avg_bar_volume = 0.0
        if avg_bar_volume <= 0:
            return 0.0
        minutes = max(1, WalkForwardOptimizer._timeframe_minutes(timeframe))
        bars_per_day = max(1.0, 1440.0 / float(minutes))
        return max(0.0, avg_bar_volume * bars_per_day * max(price_fallback, 1e-9))

    @staticmethod
    def _market_impact_pct(
        fill_qty: float,
        price: float,
        adv_notional: float,
        depth_available: float,
        spread_pct: float = 0.0,
    ) -> float:
        if fill_qty <= 0 or price <= 0:
            return 0.0
        notional = abs(fill_qty * price)
        adv_notional = max(adv_notional, notional, 1e-9)
        depth_available = max(depth_available, fill_qty, 1e-9)
        adv_pressure = min(5.0, notional / adv_notional)
        depth_pressure = min(5.0, fill_qty / depth_available)
        spread_component = max(0.0, spread_pct) * 0.5
        adv_component = 0.0025 * math.sqrt(max(adv_pressure, 0.0))
        depth_component = 0.0045 * depth_pressure
        return min(0.05, spread_component + adv_component + depth_component)

    def _simulate_pnl(
        self,
        signals: Iterable[Dict[str, Any]],
        df_map: Dict[str, pd.DataFrame],
        test_start: datetime,
        test_end: datetime,
        account_equity: float = 10000.0,
        commission_pct: float = 0.0005,
        slippage_pct: float = 0.0005,
        train_predictor: Callable[[Dict[str, Any]], float] | None = None,
    ):
        from engine.backtest_execution import simulate_signals

        return simulate_signals(
            signals, df_map, test_start=test_start, test_end=test_end,
            account_equity=account_equity, commission_pct=commission_pct,
            slippage_pct=slippage_pct, train_predictor=train_predictor,
        )

    # ---------------- ML training helpers ----------------
    def _label_signals(
        self, signals: Iterable[Dict[str, Any]], df_map: Dict[str, pd.DataFrame], lookahead_minutes: int = 1440
    ) -> Dict[int, int | None]:
        """Label signals as win(1) or loss(0) by scanning forward for TP/SL within lookahead window."""
        labeled = {}
        for idx, sig in enumerate(signals):
            asset = sig.get("asset")
            tf = sig.get("timeframe")
            df = df_map.get(f"{asset}|{tf}")
            label = None
            if df is None:
                labeled[idx] = label
                continue
            entry = float(sig.get("entry") or 0.0)
            stop = float(sig.get("stop_loss") or 0.0)
            tps = sig.get("take_profit") or sig.get("targets") or []
            if not tps or entry <= 0:
                labeled[idx] = label
                continue
            tp = float(tps[0].get("price") if isinstance(tps[0], dict) else tps[0])
            start_ts = pd.to_datetime(sig.get("timestamp") or df["timestamp"].iloc[0], utc=True)
            end_ts = start_ts + pd.Timedelta(minutes=lookahead_minutes)
            availability = df["timestamp"] + fixed_bar_duration(sig["timeframe"])
            rows = df.loc[(df["timestamp"] > start_ts) & (availability <= end_ts), :].sort_values("timestamp")
            for row in rows.to_dict(orient="records"):
                high = float(row["high"])
                low = float(row["low"])
                dirn = str(sig.get("direction") or "long").lower()
                hit_tp = (high >= tp) if dirn == "long" else (low <= tp)
                hit_sl = (low <= stop) if dirn == "long" else (high >= stop)
                if hit_tp and not hit_sl:
                    label = 1
                    break
                if hit_sl and not hit_tp:
                    label = 0
                    break
                if hit_tp and hit_sl:
                    label = 0
                    break
            labeled[idx] = label
        return labeled

    def default_train_xgb(self, train_signals: Iterable[Dict[str, Any]], df_map: Dict[str, pd.DataFrame]):
        """Fit a research-only model; unavailable training is an explicit failure."""
        booster_module = xgb
        if booster_module is None:
            raise RuntimeError("research_training_dependency_unavailable")

        # Build labelled dataset using quick labeling
        flat = list(train_signals or [])
        if not flat:
            raise ValueError("research_training_signals_missing")

        labels = self._label_signals(flat, df_map)
        X = []
        y = []
        feat_cols: list[str] | None = None

        def feature_vector(sig: Dict[str, Any], *, prediction: bool = False) -> dict:
            decision = pd.to_datetime(sig["timestamp"], utc=True)
            cached = sig.get("_research_features")
            if cached is not None:
                availability_value = sig.get("_research_feature_available_at")
                if availability_value is None:
                    raise ValueError("research_feature_availability_invalid")
                available_at = pd.to_datetime(availability_value, utc=True)
                if not isinstance(available_at, pd.Timestamp):
                    raise ValueError("research_feature_availability_invalid")
                if pd.isna(available_at) or available_at > decision:
                    raise ValueError("research_feature_availability_invalid")
                return dict(cached)
            # Manual research inputs must reconstruct their closed-bar context.
            # An inference beyond training data requires a decision-time feature
            # snapshot from BacktestRunner rather than stale training candles.
            context = {}
            for key, frame in df_map.items():
                parts = key.split("|")
                if len(parts) != 2 or parts[0] != sig.get("asset"):
                    continue
                availability = frame["timestamp"] + pd.Timedelta(minutes=self._timeframe_minutes(parts[1]))
                if prediction and (frame.empty or availability.max() < decision):
                    raise ValueError("research_prediction_feature_snapshot_required")
                closed = frame.loc[availability <= decision, :].tail(300)
                context[parts[1]] = {"candles": closed.to_dict("records")}
            if not context:
                raise ValueError("research_feature_context_missing")
            return extract_features(sig, context)

        for i, sig in enumerate(flat):
            label = labels.get(i)
            if label is None:
                continue
            feat = feature_vector(sig)
            if not feat or not all(math.isfinite(float(value)) for value in feat.values()):
                raise ValueError("research_feature_values_invalid")
            if feat_cols is None:
                feat_cols = sorted(feat)
            if set(feat) != set(feat_cols):
                raise ValueError("research_training_feature_schema_changed")
            X.append([float(feat[key]) for key in feat_cols])
            y.append(label)

        if len(X) < 30 or len(set(y)) < 2 or feat_cols is None:
            raise ValueError("research_training_sample_or_classes_insufficient")
        columns = tuple(feat_cols)
        dtrain = booster_module.DMatrix(np.array(X, dtype=np.float32), label=np.array(y, dtype=np.float32))
        params = {"objective": "binary:logistic", "eval_metric": "logloss", "verbosity": 0, "seed": 0}
        bst = booster_module.train(params, dtrain, num_boost_round=50)

        def _predictor(sig: Dict[str, Any]) -> float:
            fdict = feature_vector(sig, prediction=True)
            if set(fdict) != set(columns):
                raise ValueError("research_prediction_feature_schema_mismatch")
            vec = [float(fdict[key]) for key in columns]
            if not all(math.isfinite(value) for value in vec):
                raise ValueError("research_prediction_features_nonfinite")
            dm = booster_module.DMatrix(np.array([vec], dtype=np.float32))
            probability = float(bst.predict(dm)[0])
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("research_prediction_probability_invalid")
            return probability

        # Publication is reserved for the governed champion/challenger registry.
        return _predictor

    def run(
        self,
        assets: Iterable[str],
        timeframes: Iterable[str],
        train_months: int = 3,
        test_months: int = 1,
        start: datetime | None = None,
        end: datetime | None = None,
        train_callback: Callable[
            [Iterable[Dict[str, Any]], Dict[str, pd.DataFrame]], Callable[[Dict[str, Any]], float] | None
        ]
        | None = None,
    ):
        if start is None or end is None:
            raise ValueError("start and end datetimes must be provided")
        if train_months < 1 or test_months < 1 or start >= end:
            raise ValueError("invalid_walk_forward_calendar_window")
        assets, timeframes = tuple(assets), tuple(timeframes)
        # Build monthly anchors
        months = list(_month_ranges(start, end))
        df_map = {}
        for asset in assets:
            for tf in timeframes:
                key = f"{asset}|{tf}"
                df = self.runner.get_df(asset, tf)
                if df is not None:
                    df_map[key] = df
                for suffix, getter in (("ticks", self.runner.get_tick_df), ("orderbook", self.runner.get_orderbook_df)):
                    observations = getter(asset, tf)
                    if observations is not None:
                        df_map[key + "|" + suffix] = observations

        results = []
        # sliding windows
        for i in range(0, len(months) - (train_months + test_months) + 1):
            train_start = max(start, months[i][0])
            train_end = months[i + train_months - 1][1] - timedelta(microseconds=1)
            test_start = months[i + train_months][0]
            test_end = min(end, months[i + train_months + test_months - 1][1])
            if test_start >= test_end:
                continue

            # train phase: allow caller to fit models using raw data
            train_signals = self.runner.run_backtest(assets, timeframes, train_start, train_end, include_ml=False)
            predictor = None
            if train_callback is not None:
                try:
                    # flatten train signals
                    flat_train = []
                    for a, lst in train_signals.items():
                        for s in lst:
                            flat_train.append(s)
                    # Neither labels nor arbitrary callback feature transforms
                    # may see the validation/test period. Deep-copy boundaries.
                    training_frames = {}
                    for key, frame in df_map.items():
                        quote_data = key.endswith(("|ticks", "|orderbook"))
                        availability = frame["timestamp"] if quote_data else frame["timestamp"] + pd.Timedelta(
                            minutes=self._timeframe_minutes(key.split("|")[1])
                        )
                        training_frames[key] = frame[(frame["timestamp"] >= pd.to_datetime(train_start, utc=True))
                                                     & (availability <= pd.to_datetime(train_end, utc=True))].copy(deep=True)
                    predictor = train_callback(flat_train, training_frames)
                except Exception as exc:
                    raise RuntimeError("walk_forward_training_failed") from exc

            # evaluation: run backtest on test window
            test_signals = self.runner.run_backtest(assets, timeframes, test_start, test_end, include_ml=False)
            # flatten signals
            flat = []
            for a, lst in test_signals.items():
                for s in lst:
                    flat.append(s)
            sim = self._simulate_pnl(
                flat, df_map, test_start, test_end, account_equity=10000.0, train_predictor=predictor
            )
            completed = [row for row in sim if row["status"] == "CLOSED"]
            wins = sum(1 for row in completed if row.get("win"))
            total = len(completed)
            avg = sum(r.get("return", 0.0) for r in completed) / total if total > 0 else 0.0
            win_rate = wins / total if total > 0 else 0.0
            results.append(
                {
                    "train_start": train_start,
                    "train_end": train_end,
                    "test_start": test_start,
                    "test_end": test_end,
                    "n_signals": len(sim),
                    "completed_trades": total,
                    "nonfills": sum(row["status"] == "NOT_FILLED" for row in sim),
                    "open_trades": sum(row["status"] == "OPEN" for row in sim),
                    "risk_budget_breaches": sum(row["risk_budget_breached"] for row in sim),
                    "excluded_unclosed_candle_observations": sum(row["excluded_unclosed_candles"] for row in sim),
                    "fill_policy_version": FILL_POLICY_VERSION,
                    "evidence_class": "simulation",
                    "win_rate": win_rate,
                    "avg_return": avg,
                }
            )
        return results
