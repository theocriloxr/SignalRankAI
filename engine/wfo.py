from datetime import datetime, timedelta
from typing import Iterable, Dict, Any
import pandas as pd
import os
from pathlib import Path

from engine.backtest import BacktestRunner
from engine.risk_manager import RiskManager
from typing import Callable, Iterable, Dict, Any
from ml.features import extract_features

try:
    import xgboost as xgb
except Exception:
    xgb = None

import numpy as np
import math


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
            orderbook_df = df_map.get(f"{asset}|{tf}|orderbook")
            tick_df = df_map.get(f"{asset}|{tf}|ticks")
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
            # If tick data exists, prefer tick-level fill simulation
            # Prefer orderbook-based fills when available
            if orderbook_df is not None and 'bids' in orderbook_df.columns and 'asks' in orderbook_df.columns:
                sig_ts = pd.to_datetime(sig.get('timestamp') or rows['timestamp'].iloc[0])
                snaps = orderbook_df[(orderbook_df['timestamp'] >= sig_ts) & (orderbook_df['timestamp'] <= pd.to_datetime(test_end))]
                for _, srow in snaps.iterrows():
                    asks = srow.get('asks') or []
                    bids = srow.get('bids') or []
                    # For market buy orders we consume asks (lowest price first)
                    if direction == 'long':
                        levels = sorted(asks, key=lambda x: float(x[0]))
                    else:
                        levels = sorted(bids, key=lambda x: -float(x[0]))
                    remaining_at_snapshot = None
                    for lvl in levels:
                        level_price = float(lvl[0])
                        level_size = float(lvl[1])
                        if remaining_units <= 0:
                            break
                        fill_qty = min(remaining_units, level_size if level_size > 0 else remaining_units)
                        if fill_qty <= 0:
                            continue
                        exec_price = level_price * (1 + slippage_pct if direction == 'long' else 1 - slippage_pct)
                        trade_pnl = (exec_price - entry) * fill_qty if direction == 'long' else (entry - exec_price) * fill_qty
                        trade_pnl -= abs(trade_pnl) * commission_pct
                        pnl += trade_pnl
                        remaining_units -= fill_qty
                        # reduce the level size so subsequent fills in same snapshot are aware
                        lvl[1] = max(0.0, level_size - fill_qty) if isinstance(lvl, list) else level_size - fill_qty
                        win_flags.append(True if fill_qty > 0 else False)
                    if remaining_units <= 0:
                        break
            elif tick_df is not None and 'price' in tick_df.columns:
                sig_ts = pd.to_datetime(sig.get('timestamp') or rows['timestamp'].iloc[0])
                ticks = tick_df[(tick_df['timestamp'] >= sig_ts) & (tick_df['timestamp'] <= pd.to_datetime(test_end))]
                for _, trow in ticks.iterrows():
                    price = float(trow.get('price') or trow.get('price'))
                    # available liquidity at this tick (try several common fields)
                    tick_size = None
                    for key in ('size', 'qty', 'volume'):
                        if key in trow and trow.get(key) is not None:
                            try:
                                tick_size = float(trow.get(key))
                                break
                            except Exception:
                                tick_size = None
                    # default to an effectively infinite tick size if not provided
                    if tick_size is None or tick_size <= 0:
                        tick_size = remaining_units

                    # check TP levels using available tick liquidity (may partially fill)
                    for j, tp in enumerate(tp_prices):
                        if remaining_units <= 0:
                            break
                        hit_tp = (price >= tp) if direction == 'long' else (price <= tp)
                        if hit_tp:
                            qty_pct = tp_alloc[j] if j < len(tp_alloc) else 1.0
                            target_qty = units * qty_pct
                            # we can only fill up to tick_size on this tick
                            fill_qty = min(remaining_units, tick_size, target_qty)
                            if fill_qty <= 0:
                                continue
                            exec_price = price * (1 + slippage_pct if direction == 'long' else 1 - slippage_pct)
                            trade_pnl = (exec_price - entry) * fill_qty if direction == 'long' else (entry - exec_price) * fill_qty
                            trade_pnl -= abs(trade_pnl) * commission_pct
                            pnl += trade_pnl
                            remaining_units -= fill_qty
                            # reduce tick_size consumed
                            tick_size -= fill_qty
                            # if we partially filled target_qty, leave remainder for later ticks
                            win_flags.append(True if fill_qty > 0 else False)
                    # check SL only if still have remaining_units
                    if remaining_units > 0:
                        hit_sl = (price <= stop) if direction == 'long' else (price >= stop)
                        if hit_sl:
                            fill_qty = min(remaining_units, tick_size)
                            if fill_qty > 0:
                                exec_price = price * (1 - slippage_pct if direction == 'long' else 1 + slippage_pct)
                                trade_pnl = (exec_price - entry) * fill_qty if direction == 'long' else (entry - exec_price) * fill_qty
                                trade_pnl -= abs(trade_pnl) * commission_pct
                                pnl += trade_pnl
                                win_flags.append(False)
                                remaining_units -= fill_qty
                                if remaining_units <= 0:
                                    break
                    if remaining_units <= 0:
                        break
            else:
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

    # ---------------- ML training helpers ----------------
    def _label_signals(self, signals: Iterable[Dict[str, Any]], df_map: Dict[str, pd.DataFrame], lookahead_minutes: int = 1440) -> Dict[int, int]:
        """Label signals as win(1) or loss(0) by scanning forward for TP/SL within lookahead window."""
        labeled = {}
        for idx, sig in enumerate(signals):
            asset = sig.get("asset")
            tf = sig.get("timeframe")
            df = df_map.get(f"{asset}|{tf}")
            label = 0
            if df is None:
                labeled[idx] = label
                continue
            entry = float(sig.get('entry') or 0.0)
            stop = float(sig.get('stop_loss') or 0.0)
            tps = sig.get('take_profit') or sig.get('targets') or []
            if not tps or entry <= 0:
                labeled[idx] = label
                continue
            tp = float(tps[0].get('price') if isinstance(tps[0], dict) else tps[0])
            rows = df[(df['timestamp'] >= pd.to_datetime(sig.get('timestamp') or df['timestamp'].iloc[0])) & (df['timestamp'] <= pd.to_datetime(sig.get('timestamp') or df['timestamp'].iloc[0]) + pd.Timedelta(minutes=lookahead_minutes))]
            for _, row in rows.iterrows():
                high = float(row['high'])
                low = float(row['low'])
                dirn = str(sig.get('direction') or 'long').lower()
                hit_tp = (high >= tp) if dirn == 'long' else (low <= tp)
                hit_sl = (low <= stop) if dirn == 'long' else (high >= stop)
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
        """Train a lightweight XGBoost model on the provided train_signals and return a predictor(sig)->prob.

        Falls back to a constant predictor when xgboost isn't available or training fails.
        """
        if xgb is None:
            def _const(sig):
                return 0.5
            return _const

        # Build labelled dataset using quick labeling
        flat = list(train_signals or [])
        if not flat:
            return lambda s: 0.5

        labels = self._label_signals(flat, df_map)
        X = []
        y = []
        for i, sig in enumerate(flat):
            try:
                feat = extract_features(sig, df_map.get(f"{sig.get('asset')}|{sig.get('timeframe')}", {}))
                if not isinstance(feat, dict):
                    continue
                X.append([float(v) for v in feat.values()])
                y.append(int(labels.get(i, 0)))
            except Exception:
                continue

        if not X or len(set(y)) < 2:
            return lambda s: 0.5

        try:
            dtrain = xgb.DMatrix(np.array(X, dtype=np.float32), label=np.array(y, dtype=np.float32))
            params = {"objective": "binary:logistic", "eval_metric": "logloss", "verbosity": 0}
            bst = xgb.train(params, dtrain, num_boost_round=50)

            # capture feature order
            feat_cols = list(feat.keys())

            def _predictor(sig: Dict[str, Any]) -> float:
                try:
                    fdict = extract_features(sig, df_map.get(f"{sig.get('asset')}|{sig.get('timeframe')}", {}))
                    vec = [float(fdict.get(k, 0.0)) for k in feat_cols]
                    dm = xgb.DMatrix(np.array([vec], dtype=np.float32))
                    p = float(bst.predict(dm)[0])
                    return max(0.0, min(1.0, p))
                except Exception:
                    return 0.5
            # Persist trained model to ML_MODEL_PATH if configured
            try:
                from ml.model_registry import save_model_payload, compute_model_hash_from_b64
                import base64
                model_path = os.getenv('ML_MODEL_PATH') or (Path(__file__).parent.parent / 'ml' / 'model.json')
                # serialize booster raw bytes
                raw = bst.save_raw() if hasattr(bst, 'save_raw') else None
                if raw is None:
                    # attempt save to bytes buffer
                    from io import BytesIO
                    buf = BytesIO()
                    bst.save_model(buf)
                    raw = buf.getvalue()
                model_b64 = base64.b64encode(raw).decode('ascii')
                artifact_hash = compute_model_hash_from_b64(model_b64)
                meta = {
                    'version': os.getenv('ML_MODEL_VERSION', 'wfo-trained'),
                    'trained_at': datetime.utcnow().isoformat(),
                    'xgboost_version': getattr(xgb, '__version__', '') if xgb is not None else '',
                    'artifact_hash_sha256': artifact_hash,
                }
                try:
                    save_model_payload(Path(str(model_path)), bst, feat_cols, meta)
                except Exception:
                    pass
            except Exception:
                pass

            return _predictor
        except Exception:
            return lambda s: 0.5

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
