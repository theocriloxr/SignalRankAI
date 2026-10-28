"""Causal replay backtest of the order-block ABC strategy (strategies/zone_rejection.py).

Reads ``{SYMBOL}_{1d,4h,15m}.json`` candle files (epoch-ms open times) from a
directory, replays every closed 15m bar in time order and gives the strategy
only what was knowable then: closed 15m bars, closed 4h/1d bars, and forming
4h/1d bars rebuilt from the 15m bars seen so far (a historical daily candle
already contains the whole day's high and low). Trades are simulated forward on
15m bars: a bar touching both stop and target counts as a loss, positions are
closed at market after ``--max-hold-bars``, one position per symbol at a time,
and a round-trip cost (``--cost-pct`` of entry) is charged in R. Results are
reported for the first 70% of the period (in-sample) and the rest
(out-of-sample) separately; the strategy has no fitted parameters, so the split
shows stability over time rather than tuning leakage.

    python scripts/backtest_zone_rejection.py DATA_DIR BTCUSDT ETHUSDT --cost-pct 0.10
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategies.zone_rejection import ZoneConfig, zone_rejection_strategies  # noqa: E402

MS = {"15m": 900_000, "4h": 14_400_000, "1d": 86_400_000}
WINDOW = {"15m": 160, "4h": 160, "1d": 90}
ON = {"ZONE_REJECTION_STRATEGY_ENABLED": "1"}


def load(directory: Path, symbol: str) -> dict[str, list[dict]]:
    data = {}
    for tf in ("1d", "4h", "15m"):
        rows = json.loads((directory / f"{symbol}_{tf}.json").read_text(encoding="utf-8"))
        data[tf] = sorted(rows, key=lambda r: r["timestamp"])
    return data


def forming_bar(m15: list[dict], start_ms: int, now_ms: int) -> dict | None:
    """Aggregate the closed 15m bars inside [start_ms, now_ms) into a partial HTF bar."""
    bars = [b for b in m15 if start_ms <= b["timestamp"] and b["timestamp"] + MS["15m"] <= now_ms]
    if not bars:
        return None
    return {"timestamp": start_ms, "open": bars[0]["open"], "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars), "close": bars[-1]["close"], "volume": sum(b["volume"] for b in bars)}


def market_at(data: dict[str, list[dict]], stamps: dict[str, list[int]], now_ms: int) -> dict:
    market = {}
    m15_end = bisect_right(stamps["15m"], now_ms - MS["15m"])  # bars closed by now
    m15 = data["15m"][max(0, m15_end - WINDOW["15m"]):m15_end]
    market["15m"] = {"candles": m15}
    for tf in ("4h", "1d"):
        period_start = now_ms - (now_ms % MS[tf])
        closed_end = bisect_right(stamps[tf], period_start - MS[tf])
        candles = list(data[tf][max(0, closed_end - WINDOW[tf]):closed_end])
        day_slice = data["15m"][bisect_right(stamps["15m"], period_start - 1):m15_end]
        partial = forming_bar(day_slice, period_start, now_ms)
        if partial:
            candles.append(partial)
        market[tf] = {"candles": candles}
    return market


def simulate(signal: dict, future: list[dict], cost_pct: float, max_hold: int) -> dict:
    entry, stop, target = signal["entry"], signal["stop_loss"], signal["take_profit"]
    short = signal["direction"] == "SHORT"
    risk = abs(stop - entry)
    cost_r = (entry * cost_pct / 100.0) / risk
    for held, bar in enumerate(future[:max_hold], start=1):
        hit_stop = bar["high"] >= stop if short else bar["low"] <= stop
        hit_target = bar["low"] <= target if short else bar["high"] >= target
        if hit_stop:  # includes bars touching both: counted as a loss
            return {"r": -1.0 - cost_r, "exit": "stop", "bars": held}
        if hit_target:
            return {"r": abs(target - entry) / risk - cost_r, "exit": "target", "bars": held}
    last = future[min(len(future), max_hold) - 1]["close"] if future else entry
    moved = (entry - last) if short else (last - entry)
    return {"r": moved / risk - cost_r, "exit": "time", "bars": min(len(future), max_hold)}


def stats(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0}
    rs = [t["r"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    mean = sum(rs) / len(rs)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rs) / (len(rs) - 1)) if len(rs) > 1 else 0.0
    return {
        "trades": len(rs), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(rs), 4), "expectancy_r": round(mean, 4),
        "expectancy_r_95ci_low": round(mean - 1.96 * sd / math.sqrt(len(rs)), 4) if len(rs) > 1 else None,
        "total_r": round(sum(rs), 3), "max_drawdown_r": round(max_dd, 3),
        "profit_factor": round(sum(wins) / -sum(losses), 3) if losses and sum(losses) < 0 else None,
        "exits": {k: sum(1 for t in trades if t["exit"] == k) for k in ("target", "stop", "time")},
        "avg_bars_held": round(sum(t["bars"] for t in trades) / len(trades), 1),
    }


def run_symbol(data: dict[str, list[dict]], cost_pct: float, max_hold: int, config: ZoneConfig) -> list[dict]:
    stamps = {tf: [b["timestamp"] for b in rows] for tf, rows in data.items()}
    m15 = data["15m"]
    warmup = 90 * MS["1d"]
    start_ms = stamps["15m"][0] + warmup
    trades, busy_until = [], -1
    for i, bar in enumerate(m15):
        now_ms = bar["timestamp"] + MS["15m"]
        if now_ms < start_ms or i <= busy_until or i + 1 >= len(m15):
            continue
        now = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
        for signal in zone_rejection_strategies("SYMBOL", market_at(data, stamps, now_ms),
                                                environment=ON, config=config, now=now):
            outcome = simulate(signal, m15[i + 1:], cost_pct, max_hold)
            trades.append({"time": now.isoformat(), "direction": signal["direction"],
                           "rr_planned": signal["rr_ratio"], **outcome})
            busy_until = i + outcome["bars"]
            break
    return trades


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--cost-pct", type=float, default=0.10, help="round-trip cost as % of entry")
    parser.add_argument("--max-hold-bars", type=int, default=672, help="15m bars (672 = 7 days)")
    parser.add_argument("--in-sample-fraction", type=float, default=0.7)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"strategy": "order-block-abc-v1", "cost_pct_round_trip": args.cost_pct,
              "max_hold_bars_15m": args.max_hold_bars, "symbols": {}}
    for symbol in args.symbols:
        data = load(args.data_dir, symbol)
        trades = run_symbol(data, args.cost_pct, args.max_hold_bars, ZoneConfig())
        first, last = data["15m"][0]["timestamp"], data["15m"][-1]["timestamp"]
        cut = first + (last - first) * args.in_sample_fraction
        cut_iso = datetime.fromtimestamp(cut / 1000, tz=timezone.utc).isoformat()
        report["symbols"][symbol] = {
            "period": [datetime.fromtimestamp(first / 1000, tz=timezone.utc).isoformat(),
                       datetime.fromtimestamp(last / 1000, tz=timezone.utc).isoformat()],
            "split_at": cut_iso,
            "all": stats(trades),
            "in_sample": stats([t for t in trades if t["time"] < cut_iso]),
            "out_of_sample": stats([t for t in trades if t["time"] >= cut_iso]),
            "trades": trades,
        }
        print(symbol, json.dumps(report["symbols"][symbol]["all"]), flush=True)
    if args.output:
        args.output.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
