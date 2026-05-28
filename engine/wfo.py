from datetime import datetime, timedelta
from typing import Iterable, Dict, Any
import pandas as pd

from engine.backtest import BacktestRunner
from engine.risk_manager import RiskManager
from typing import Callable, Iterable, Dict, Any


def _month_ranges(start: datetime, end: datetime):
    cur = datetime(start.year, start.month, 1)
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
        # Richer simulator: supports partial TP ladders, commission, slippage,
        # position sizing via RiskManager (ATR/Kelly hooks), and optional ML filter.
        rm = RiskManager(account_equity)
        results = []
        for sig in signals:
            asset = sig.get("asset")
            tf = sig.get("timeframe")
            df = df_map.get(f"{asset}|{tf}")
            if df is None:
                continue
            rows = df[(df['timestamp'] >= pd.to_datetime(test_start)) & (df['timestamp'] <= pd.to_datetime(test_end))]
            if rows.empty:
                continue
            entry = float(sig.get('entry') or 0.0)
            stop = float(sig.get('stop_loss') or 0.0)
            tps = sig.get('take_profit') or sig.get('targets') or []
            if not tps or entry <= 0:
                continue
            direction = str(sig.get('direction') or 'long').lower()
            # Optionally apply ML predictor to filter signals or weight position
            ml_prob = None
            if train_predictor is not None:
                try:
                    ml_prob = float(train_predictor(sig) or 0.0)
                except Exception:
                    ml_prob = None

            # Position sizing: use risk manager's dynamic pct or Kelly if provided in signal
            if 'kelly_win_rate' in sig and 'kelly_win_loss' in sig:
                # Kelly fraction: w - (1-w)/r
                w = float(sig.get('kelly_win_rate') or 0.0)
                r = float(sig.get('kelly_win_loss') or 1.0)
                try:
                    kelly_fraction = max(0.0, w - (1.0 - w) / max(r, 1e-9))
                except Exception:
                    kelly_fraction = 0.0
                position_risk_pct = float(kelly_fraction * 100.0)
            else:
                position_risk_pct = rm.get_dynamic_risk_pct(sig)

            # compute size in units (not dollars) as: (equity * pct) / risk_distance
            risk_dist = abs(entry - stop) if abs(entry - stop) > 1e-9 else 0.0
            if risk_dist <= 0:
                continue
            risk_amount = account_equity * (position_risk_pct / 100.0)
            units = risk_amount / risk_dist
            # enforce sensible bounds
            units = max(0.0, min(units, account_equity * 0.2))

            # simulate per-candle hits, supporting partial TPs
            tp_prices = [float(tp.get('price') if isinstance(tp, dict) else tp) for tp in tps]
            tp_alloc = [float(tp.get('exit_percent', 0.0)) / 100.0 if isinstance(tp, dict) else 1.0 for tp in tps]
            if not tp_alloc or sum(tp_alloc) == 0:
                tp_alloc = [1.0]
            remaining_units = units
            pnl = 0.0
            win_flags = []
            for idx in rows.index:
                row = rows.loc[idx]
                high = float(row['high'])
                low = float(row['low'])
                # check TP levels
                for j, tp in enumerate(tp_prices):
                    if remaining_units <= 0:
                        break
                    hit_tp = (high >= tp) if direction == 'long' else (low <= tp)
                    if hit_tp:
                        qty_pct = tp_alloc[j] if j < len(tp_alloc) else 1.0
                        qty = units * qty_pct
                        # apply slippage/commission
                        exec_price = tp * (1 + slippage_pct if direction == 'long' else 1 - slippage_pct)
                        trade_pnl = (exec_price - entry) * qty if direction == 'long' else (entry - exec_price) * qty
                        trade_pnl -= abs(trade_pnl) * commission_pct
                        pnl += trade_pnl
                        remaining_units -= qty
                        win_flags.append(True)
                # check SL only if still have remaining_units
                if remaining_units > 0:
                    hit_sl = (low <= stop) if direction == 'long' else (high >= stop)
                    if hit_sl:
                        exec_price = stop * (1 - slippage_pct if direction == 'long' else 1 + slippage_pct)
                        trade_pnl = (exec_price - entry) * remaining_units if direction == 'long' else (entry - exec_price) * remaining_units
                        trade_pnl -= abs(trade_pnl) * commission_pct
                        pnl += trade_pnl
                        win_flags.append(False)
                        remaining_units = 0
                        break
                if remaining_units <= 0:
                    break

            # normalize returns per-dollar-equity
            results.append({'n_trades': len(win_flags), 'pnl': pnl, 'win_count': sum(1 for w in win_flags if w), 'loss_count': sum(1 for w in win_flags if not w)})

        return results

    def run(
        self,
        assets: Iterable[str],
        timeframes: Iterable[str],
        train_months: int = 3,
        test_months: int = 1,
        start: datetime = None,
        end: datetime = None,
        train_callback: Callable[[Iterable[Dict[str, Any]], Dict[str, pd.DataFrame]], Callable[[Dict[str, Any]], float] | None] | None = None,
    ):
        if start is None or end is None:
            raise ValueError("start and end datetimes must be provided")
        # Build monthly anchors
        months = list(_month_ranges(start, end))
        df_map = {}
        for asset in assets:
            for tf in timeframes:
                key = f"{asset}|{tf}"
                df = self.runner.get_df(asset, tf)
                if df is not None:
                    df_map[key] = df

        results = []
        # sliding windows
        for i in range(0, len(months) - (train_months + test_months) + 1):
            train_start = months[i][0]
            train_end = months[i + train_months - 1][1]
            test_start = months[i + train_months][0]
            test_end = months[i + train_months + test_months - 1][1]

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
                    predictor = train_callback(flat_train, df_map)
                except Exception:
                    predictor = None

            # evaluation: run backtest on test window
            test_signals = self.runner.run_backtest(assets, timeframes, test_start, test_end, include_ml=False)
            # flatten signals
            flat = []
            for a, lst in test_signals.items():
                for s in lst:
                    flat.append(s)
            sim = self._simulate_pnl(flat, df_map, test_start, test_end, account_equity=10000.0, train_predictor=predictor)
            wins = sum(1 for r in sim if r.get('win'))
            total = len(sim)
            avg = sum(r.get('return', 0.0) for r in sim) / total if total > 0 else 0.0
            win_rate = wins / total if total > 0 else 0.0
            results.append({
                'train_start': train_start,
                'train_end': train_end,
                'test_start': test_start,
                'test_end': test_end,
                'n_signals': total,
                'win_rate': win_rate,
                'avg_return': avg,
            })
        return results
