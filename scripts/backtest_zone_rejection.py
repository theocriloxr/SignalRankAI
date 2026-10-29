"""Causal replay backtest of the order-block ABC strategy (strategies/zone_rejection.py).

Reads ``{SYMBOL}_{1d,4h,15m}.json`` candle files (epoch-ms open times) from a
directory, replays every closed 15m bar in time order and gives the strategy
only what was knowable then: closed 15m bars, closed 4h/1d bars, and forming
4h/1d bars rebuilt from the 15m bars seen so far (a historical daily candle
already contains the whole day's high and low). Trades are simulated forward on
15m bars: a bar touching both stop and target counts as a loss, positions are
closed at market after ``--max-hold-bars`` and one position per symbol is open
at a time. Results are reported for the first 70% of the period (in-sample) and
the rest (out-of-sample) separately; the strategy has no fitted parameters, so
the split shows stability over time rather than tuning leakage.

Execution (``--cost-model realistic``, the default since 29 Oct 2026), following
the conventions of engine/backtest_execution.py:

- The signal is known only when its bar closes, so entry is a market order at
  the next bar's open, paying half the quoted spread plus slippage.
- An open already past the stop (or past the target) cancels the trade
  ("no_fill"): the setup no longer exists.
- Stops fill at the stop, or at the open when the bar gaps through it, minus
  half the spread and slippage; a loss can exceed 1R.
- Targets are limit orders: they fill only when price trades through the target
  by half the spread (a touch is not a fill), at the target, with no price
  improvement.
- Taker fees on market and stop fills, maker fees on target fills, and optional
  perpetual funding for the time held are charged on both notionals.
- R is the planned risk (|signal entry - stop|), which is how a position would
  be sized, so slippage and fees show as real losses.

``--cost-model flat`` keeps the 28 Oct model (fill at the signal price, a
round-trip ``--cost-pct``) for comparison.

    python scripts/backtest_zone_rejection.py DATA_DIR BTCUSDT ETHUSDT --taker-fee-bps 5 --spread-bps 2
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from bisect import bisect_right
from dataclasses import asdict, dataclass
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


@dataclass(frozen=True)
class CostModel:
    """Execution costs in basis points of notional. Defaults suit liquid crypto majors."""

    taker_fee_bps: float = 5.0
    maker_fee_bps: float = 2.0
    spread_bps: float = 2.0  # full quoted spread; half is paid on every market or stop fill
    slippage_bps: float = 3.0  # extra adverse move on market and stop fills
    funding_bps_per_8h: float = 0.0  # perpetual funding, always charged as a cost
    bar_minutes: int = 15


def simulate_execution(signal: dict, future: list[dict], model: CostModel, max_hold: int) -> dict:
    """Replay one signal with next-open entry, spread, slippage, fees and gap-aware stops."""
    planned, stop, target = signal["entry"], signal["stop_loss"], signal["take_profit"]
    short = signal["direction"] == "SHORT"
    risk = abs(stop - planned)
    if not future or risk <= 0:
        return {"r": 0.0, "exit": "no_fill", "bars": 0, "filled": False}
    adverse = (model.spread_bps / 2 + model.slippage_bps) / 10_000
    half_spread = model.spread_bps / 2 / 10_000
    opening = future[0]["open"]
    entry_fill = opening * (1 - adverse) if short else opening * (1 + adverse)
    if (entry_fill >= stop) if short else (entry_fill <= stop):
        return {"r": 0.0, "exit": "no_fill", "bars": 0, "filled": False, "reason": "opened_past_stop"}
    if (opening <= target) if short else (opening >= target):
        return {"r": 0.0, "exit": "no_fill", "bars": 0, "filled": False, "reason": "opened_past_target"}
    through = target * half_spread

    def finish(kind: str, exit_fill: float, ideal_exit: float, exit_fee_bps: float, held: int) -> dict:
        move = (entry_fill - exit_fill) if short else (exit_fill - entry_fill)
        fees = (model.taker_fee_bps * entry_fill + exit_fee_bps * exit_fill) / 10_000
        funding = model.funding_bps_per_8h / 10_000 * entry_fill * (held * model.bar_minutes / 480)
        r = (move - fees - funding) / risk
        ideal = ((planned - ideal_exit) if short else (ideal_exit - planned)) / risk
        return {"r": r, "exit": kind, "bars": held, "filled": True, "entry_fill": entry_fill,
                "exit_fill": exit_fill, "fees_r": (fees + funding) / risk, "friction_r": ideal - r}

    for held, bar in enumerate(future[:max_hold], start=1):
        if bar["high"] >= stop if short else bar["low"] <= stop:  # stop first when a bar touches both
            trigger = max(stop, bar["open"]) if short else min(stop, bar["open"])  # a gap fills at the open
            exit_fill = trigger * (1 + adverse) if short else trigger * (1 - adverse)
            return finish("stop", exit_fill, stop, model.taker_fee_bps, held)
        if bar["low"] <= target - through if short else bar["high"] >= target + through:
            return finish("target", target, target, model.maker_fee_bps, held)
    held = min(len(future), max_hold)
    last = future[held - 1]["close"]
    exit_fill = last * (1 + adverse) if short else last * (1 - adverse)
    return finish("time", exit_fill, last, model.taker_fee_bps, held)


def simulate(signal: dict, future: list[dict], cost_pct: float, max_hold: int) -> dict:
    """The 28 Oct flat model: fill at the signal price, round-trip ``cost_pct`` of entry."""
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
    not_filled = sum(1 for t in trades if not t.get("filled", True))
    trades = [t for t in trades if t.get("filled", True)]
    if not trades:
        return {"trades": 0, **({"not_filled": not_filled} if not_filled else {})}
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
        "not_filled": not_filled,
        **({"avg_fees_r": round(sum(t["fees_r"] for t in trades) / len(trades), 4),
            "avg_friction_r": round(sum(t["friction_r"] for t in trades) / len(trades), 4)}
           if all("fees_r" in t for t in trades) else {}),
    }


def run_symbol(data: dict[str, list[dict]], cost_pct: float, max_hold: int, config: ZoneConfig,
               model: CostModel | None = None) -> list[dict]:
    """``model`` selects realistic execution; ``None`` keeps the flat ``cost_pct`` model."""
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
            future = m15[i + 1:]
            outcome = (simulate_execution(signal, future, model, max_hold) if model is not None
                       else simulate(signal, future, cost_pct, max_hold))
            trades.append({"time": now.isoformat(), "direction": signal["direction"],
                           "rr_planned": signal["rr_ratio"], **outcome})
            busy_until = i + outcome["bars"]  # an unfilled signal does not block the next one
            break
    return trades


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--cost-model", choices=("realistic", "flat"), default="realistic")
    parser.add_argument("--cost-pct", type=float, default=0.10, help="flat model only: round-trip cost as %% of entry")
    defaults = CostModel()
    parser.add_argument("--taker-fee-bps", type=float, default=defaults.taker_fee_bps)
    parser.add_argument("--maker-fee-bps", type=float, default=defaults.maker_fee_bps)
    parser.add_argument("--spread-bps", type=float, default=defaults.spread_bps, help="full quoted spread")
    parser.add_argument("--slippage-bps", type=float, default=defaults.slippage_bps)
    parser.add_argument("--funding-bps-per-8h", type=float, default=defaults.funding_bps_per_8h,
                        help="perpetuals: funding charged as a cost while a position is open")
    parser.add_argument("--max-hold-bars", type=int, default=672, help="15m bars (672 = 7 days)")
    parser.add_argument("--in-sample-fraction", type=float, default=0.7)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    model = None if args.cost_model == "flat" else CostModel(
        taker_fee_bps=args.taker_fee_bps, maker_fee_bps=args.maker_fee_bps, spread_bps=args.spread_bps,
        slippage_bps=args.slippage_bps, funding_bps_per_8h=args.funding_bps_per_8h)
    report = {"strategy": "order-block-abc-v1",
              "cost_model": {"name": "flat", "cost_pct_round_trip": args.cost_pct} if model is None
              else {"name": "realistic", **asdict(model)},
              "max_hold_bars_15m": args.max_hold_bars, "symbols": {}}
    for symbol in args.symbols:
        data = load(args.data_dir, symbol)
        trades = run_symbol(data, args.cost_pct, args.max_hold_bars, ZoneConfig(), model)
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
