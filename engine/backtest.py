from typing import Dict, Iterable, List, Optional
import pandas as pd
from datetime import datetime

from engine.strategies.signal_generator import SignalGenerator
from engine.signal_deduplicator import SignalDeduplicator
from data.indicators import calculate_indicators


class BacktestRunner:
    """Lightweight backtest runner that replays OHLCV candles and invokes
    the same signal generation logic used in the live engine.
    """

    def __init__(self, data_frames: Optional[Dict[str, pd.DataFrame]] = None):
        # data_frames: mapping like {"BTCUSDT|5m": DataFrame}
        self.data_frames = data_frames or {}
        self.signal_gen = SignalGenerator()
        self.dedup = SignalDeduplicator()

    @staticmethod
    def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.sort_values("timestamp").reset_index(drop=True)
            if df["timestamp"].isna().any() or df["timestamp"].duplicated().any():
                raise ValueError("invalid_or_duplicate_backtest_timestamp")
        return df

    def load_from_parquet(self, path: str) -> pd.DataFrame:
        df = pd.read_parquet(path)
        return self.normalize_df(df)

    def _key(self, asset: str, tf: str) -> str:
        return f"{asset.upper()}|{tf}"

    def register_dataframe(self, asset: str, tf: str, df: pd.DataFrame) -> None:
        self.data_frames[self._key(asset, tf)] = self.normalize_df(df)

    def register_tick_dataframe(self, asset: str, tf: str, df: pd.DataFrame) -> None:
        """Register tick-level dataframe for an asset/timeframe. Stored under key asset|tf|ticks."""
        key = f"{asset.upper()}|{tf}|ticks"
        df2 = df.copy()
        if "timestamp" in df2.columns:
            df2["timestamp"] = pd.to_datetime(df2["timestamp"], utc=True)
            df2 = df2.sort_values("timestamp").reset_index(drop=True)
        self.data_frames[key] = df2

    def get_tick_df(self, asset: str, tf: str) -> Optional[pd.DataFrame]:
        return self.data_frames.get(f"{asset.upper()}|{tf}|ticks")

    def register_orderbook_dataframe(self, asset: str, tf: str, df: pd.DataFrame) -> None:
        """Register orderbook snapshot dataframe for an asset/timeframe.

        The dataframe should contain at least `timestamp` and either `bids`/`asks` columns
        where each entry is a list of [price, size] tuples describing the book snapshot.
        Stored under key asset|tf|orderbook.
        """
        key = f"{asset.upper()}|{tf}|orderbook"
        df2 = df.copy()
        if "timestamp" in df2.columns:
            df2["timestamp"] = pd.to_datetime(df2["timestamp"], utc=True)
            df2 = df2.sort_values("timestamp").reset_index(drop=True)
        self.data_frames[key] = df2

    def get_orderbook_df(self, asset: str, tf: str) -> Optional[pd.DataFrame]:
        return self.data_frames.get(f"{asset.upper()}|{tf}|orderbook")

    def get_df(self, asset: str, tf: str) -> Optional[pd.DataFrame]:
        return self.data_frames.get(self._key(asset, tf))

    def run_backtest(
        self, assets: Iterable[str], timeframes: Iterable[str], start: datetime, end: datetime, include_ml: bool = False
    ) -> Dict[str, List[dict]]:
        from engine.wfo import WalkForwardOptimizer
        from ml.features import extract_features
        assets, timeframes = tuple(assets), tuple(timeframes)
        if include_ml:
            raise ValueError("historical_model_artifact_and_training_cutoff_required")
        out: Dict[str, List[dict]] = {a: [] for a in assets}
        for asset in assets:
            for tf in timeframes:
                df = self.get_df(asset, tf)
                if df is None or df.empty:
                    continue
                # filter window
                mask = (df["timestamp"] >= pd.to_datetime(start, utc=True)) & (
                    df["timestamp"] <= pd.to_datetime(end, utc=True)
                )
                window = df.loc[mask]
                if window.empty or len(window) < 60:
                    continue
                # iterate over rows, starting after warmup
                for idx in range(50, len(window)):
                    slice_df = window.iloc[: idx + 1]
                    # Provider candles use opening timestamps; OHLC features
                    # become available only when that candle closes.
                    decision_time = slice_df.iloc[-1]["timestamp"] + pd.Timedelta(
                        minutes=WalkForwardOptimizer._timeframe_minutes(tf)
                    )
                    if decision_time > pd.to_datetime(end, utc=True):
                        continue
                    candles = slice_df.tail(300)[["timestamp", "open", "high", "low", "close", "volume"]].to_dict(
                        "records"
                    )
                    indicators = calculate_indicators(slice_df)
                    market_data = {"candles": candles, "indicators": indicators}
                    try:
                        signals = self.signal_gen.generate_signals(asset, tf, market_data)
                        for sig in signals:
                            # Map StrategySignal to dict shape similar to live flow
                            sig_dict = {
                                "asset": asset,
                                "timeframe": tf,
                                "timestamp": decision_time,
                                "decision_data_available_at": decision_time,
                                "direction": sig.direction,
                                "entry": float(sig.entry),
                                "stop_loss": float(sig.stop_loss),
                                "take_profit": sig.take_profit,
                                "score": float(sig.score),
                                "strategy_name": sig.strategy_name,
                                "strategy_group": sig.strategy_group,
                                "confidence": float(sig.confidence),
                            }
                            sig_dict["_research_features"] = extract_features(sig_dict, {tf: market_data})
                            sig_dict["_research_feature_available_at"] = decision_time
                            out[asset].append(sig_dict)
                    except Exception as exc:
                        raise RuntimeError(f"backtest_signal_generation_failed:{asset}:{tf}") from exc
        return out


"""
Backtest Engine
- Walk-forward testing
- Performance analytics
- Optimization
"""

import logging
import math
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Full backtest with walk-forward analysis and metrics."""

    def __init__(self):
        self.trades = []
        self.equity_curve = []
        self.metrics = {}

    def add_trade(
        self,
        symbol: str,
        direction: int,
        entry_time: datetime,
        entry_price: float,
        exit_time: datetime,
        exit_price: float,
        position_size: float,
        risk: float,
    ):
        """Record a completed trade."""
        price_diff = exit_price - entry_price

        if direction == 1:  # Long
            pnl = price_diff * position_size
            pnl_pct = (price_diff / entry_price) * 100
        else:  # Short
            pnl = -price_diff * position_size
            pnl_pct = -(price_diff / entry_price) * 100

        trade = {
            "symbol": symbol,
            "direction": "LONG" if direction == 1 else "SHORT",
            "entry_time": entry_time,
            "entry_price": entry_price,
            "exit_time": exit_time,
            "exit_price": exit_price,
            "size": position_size,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "risk": risk,
            "rr_ratio": pnl / risk if risk > 0 else 0,
            "win": pnl > 0,
            "hold_time": (exit_time - entry_time).total_seconds() / 3600,  # hours
        }

        self.trades.append(trade)

    def calculate_metrics(self) -> Dict:
        """Calculate all performance metrics."""
        if not self.trades:
            return {}

        df = pd.DataFrame(self.trades)

        total_trades = len(df)
        winning_trades = len(df[df["win"]])
        losing_trades = len(df[~df["win"]])

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        total_pnl = df["pnl"].sum()

        avg_win = df[df["win"]]["pnl"].mean() if winning_trades > 0 else 0
        avg_loss = df[~df["win"]]["pnl"].mean() if losing_trades > 0 else 0

        profit_factor = abs(df[df["win"]]["pnl"].sum() / df[~df["win"]]["pnl"].sum()) if losing_trades > 0 else 0

        # Drawdown analysis
        cumulative_pnl = pd.concat([pd.Series([0.0]), df["pnl"]]).cumsum()
        running_max = cumulative_pnl.cummax()
        drawdown = cumulative_pnl - running_max
        max_drawdown = drawdown.min()
        # A cash drawdown divided by average winning trade is not an equity
        # drawdown percentage. Initial capital/time-indexed equity is absent.
        max_drawdown_pct = None

        # Risk metrics
        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

        self.metrics = {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_per_trade": round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": max_drawdown_pct,
            "drawdown_percentage_reason": "initial_equity_and_time_indexed_equity_required",
            "expectancy": round(expectancy, 2),
            "avg_hold_time_hours": round(df["hold_time"].mean(), 2),
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "annualization_basis": "irregular_cash_trade_PnL_not_period_returns",
        }

        return self.metrics

    def _calculate_sharpe(self, returns: pd.Series, risk_free_rate: float = 0.0, *, periods_per_year: float | None = None) -> float | None:
        """Calculate Sharpe ratio."""
        if periods_per_year is None or len(returns) < 2:
            return None
        if not np.isfinite(periods_per_year) or periods_per_year <= 0 or not np.isfinite(returns).all():
            raise ValueError("invalid_annualization_input")

        excess_return = returns.mean() - risk_free_rate
        std_dev = returns.std()

        if std_dev == 0:
            return 0

        sharpe = (excess_return / std_dev) * np.sqrt(periods_per_year)
        return round(sharpe, 2)

    def _calculate_sortino(self, returns: pd.Series, risk_free_rate: float = 0.0, *, periods_per_year: float | None = None) -> float | None:
        """Calculate Sortino ratio (only downside volatility)."""
        if periods_per_year is None or len(returns) < 2:
            return None
        if not np.isfinite(periods_per_year) or periods_per_year <= 0 or not np.isfinite(returns).all():
            raise ValueError("invalid_annualization_input")

        excess_return = returns.mean() - risk_free_rate
        downside_std = np.sqrt(np.mean(np.minimum(returns - risk_free_rate, 0) ** 2))

        if downside_std == 0:
            return 0

        sortino = (excess_return / downside_std) * np.sqrt(periods_per_year)
        return round(sortino, 2)

    def get_summary(self) -> str:
        """Generate text summary of backtest results."""
        if not self.metrics:
            return "No trades to analyze"

        summary = f"""
╔════════════════════════════════════════╗
║         BACKTEST SUMMARY               ║
╠════════════════════════════════════════╣
║ Total Trades:        {self.metrics["total_trades"]:>20} ║
║ Wins / Losses:       {self.metrics["winning_trades"]:>7} / {self.metrics["losing_trades"]:<10} ║
║ Win Rate:            {self.metrics["win_rate"]:>19}% ║
│────────────────────────────────────────│
║ Total P&L:           ${self.metrics["total_pnl"]:>18.2f} ║
║ Avg P&L/Trade:       ${self.metrics["avg_pnl_per_trade"]:>18.2f} ║
║ Avg Win:             ${self.metrics["avg_win"]:>18.2f} ║
║ Avg Loss:            ${self.metrics["avg_loss"]:>18.2f} ║
│────────────────────────────────────────│
║ Profit Factor:       {self.metrics["profit_factor"]:>20} ║
║ Expectancy:          ${self.metrics["expectancy"]:>18.2f} ║
║ Max Drawdown:        ${self.metrics["max_drawdown"]:>18.2f} ║
║ Avg Hold Time:       {self.metrics["avg_hold_time_hours"]:>18}h ║
│────────────────────────────────────────│
║ Sharpe Ratio:        {str(self.metrics["sharpe_ratio"]):>20} ║
║ Sortino Ratio:       {str(self.metrics["sortino_ratio"]):>20} ║
╚════════════════════════════════════════╝
"""
        return summary

    def walk_forward_analysis(self, test_period_days: int = 30, optimization_period_days: int = 90) -> List[Dict]:
        """Perform walk-forward optimization analysis."""
        if not self.trades:
            return []

        df = pd.DataFrame(self.trades)
        df["exit_time"] = pd.to_datetime(df["exit_time"])

        results = []

        # Get date range
        min_date = df["exit_time"].min()
        max_date = df["exit_time"].max()

        current_date = min_date + timedelta(days=optimization_period_days)

        while current_date <= max_date:
            test_end = current_date + timedelta(days=test_period_days)
            optimization_start = current_date - timedelta(days=optimization_period_days)

            # Optimization period
            opt_trades = df[(df["exit_time"] >= optimization_start) & (df["exit_time"] < current_date)]

            # Test period
            test_trades = df[(df["exit_time"] >= current_date) & (df["exit_time"] < test_end)]

            if len(test_trades) > 0:
                opt_metrics = self._calculate_period_metrics(opt_trades)
                test_metrics = self._calculate_period_metrics(test_trades)

                results.append(
                    {
                        "period_end": current_date,
                        "test_period_end": test_end,
                        "optimization_metrics": opt_metrics,
                        "test_metrics": test_metrics,
                        "degradation": test_metrics["win_rate"] - opt_metrics["win_rate"],
                    }
                )

            current_date += timedelta(days=test_period_days)

        return results

    def _calculate_period_metrics(self, trades: pd.DataFrame) -> Dict:
        """Calculate metrics for a specific period."""
        if trades.empty:
            return {}

        total = len(trades)
        wins = len(trades[trades["win"]])
        win_rate = (wins / total * 100) if total > 0 else 0

        return {
            "trades": total,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(trades["pnl"].sum(), 2),
            "avg_pnl": round(trades["pnl"].mean(), 2),
        }

    def export_trades(self, filepath: str):
        """Export trades to CSV."""
        if not self.trades:
            logger.warning("No trades to export")
            return

        df = pd.DataFrame(self.trades)
        df.to_csv(filepath, index=False)
        logger.info(f"Exported {len(df)} trades to {filepath}")

    def reset(self):
        """Clear all trade data."""
        self.trades = []
        self.equity_curve = []
        self.metrics = {}


class OptimizationEngine:
    """Parameter optimization using walk-forward analysis."""

    def __init__(self):
        self.results = []

    def optimize_parameters(self, backtest_fn, param_ranges: Dict[str, List], metric: str = "expectancy_r", *, record_trial=None, max_trials: int = 1000) -> Dict:
        """Find optimal parameter values by testing all combinations."""
        if record_trial is None:
            return {"enabled": False, "reason": "durable_research_trial_recorder_required", "best_params": None}
        if not isinstance(max_trials, int) or not 1 <= max_trials <= 10000:
            raise ValueError("invalid_optimization_compute_budget")
        count = math.prod(len(values) for values in param_ranges.values())
        if not param_ranges or count == 0 or count > max_trials:
            raise ValueError("optimization_trial_budget_exceeded")
        self.results = []
        best_params = None
        best_score = -np.inf

        # Generate all parameter combinations
        param_combinations = self._generate_combinations(param_ranges)

        for trial_number, params in enumerate(param_combinations):
            # Run backtest with these parameters
            experiment_id = record_trial("STARTED", trial_number, params, None)
            if not experiment_id:
                raise ValueError("durable_trial_id_required_before_objective")
            try:
                result = backtest_fn(params)
                score = float(result[metric])
                if not math.isfinite(score):
                    raise ValueError("invalid_optimization_metric")
            except Exception:
                record_trial("FAILED", trial_number, params, {"experiment_id": experiment_id})
                raise
            record_trial("COMPLETED", trial_number, params, {"experiment_id": experiment_id, "score": score, "result": result})

            if score > best_score:
                best_score = score
                best_params = params

            self.results.append({"params": params, "score": score, "result": result})

        return {"enabled": True, "best_params": best_params, "best_score": best_score, "all_results": self.results,
                "production_activation_allowed": False, "selection_bias_adjustment_required": True}

    def _generate_combinations(self, param_ranges: Dict[str, List]) -> List[Dict]:
        """Generate all combinations of parameter values."""
        keys = param_ranges.keys()
        values = param_ranges.values()

        combinations = []

        # Simple nested loop for all combinations
        import itertools

        for combo in itertools.product(*values):
            combination_dict = dict(zip(keys, combo))
            combinations.append(combination_dict)

        return combinations
