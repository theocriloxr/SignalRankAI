"""Conservative research fill replay shared by the legacy WFO runner.

This spot-unit simulation is not broker certification. Quotes after the
decision determine entry; books consume the correct side and known size.
Stops precede targets in ambiguous OHLC bars. Costs debit both notionals.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable

import pandas as pd

from engine.risk_manager import RiskManager
from engine.risk_advice import finite_number

FILL_POLICY_VERSION = "wfo_conservative_fills_v4"


def fixed_bar_duration(timeframe: str) -> pd.Timedelta:
    """Provider OHLC timestamps are opens; unknown durations cannot imply closes."""
    match = re.fullmatch(r"([1-9][0-9]{0,4})(m|h|d|w)?", timeframe.strip()) if isinstance(timeframe, str) else None
    if match is None:
        raise ValueError("research_timeframe_must_have_fixed_positive_duration")
    minutes = int(match.group(1)) * {"m": 1, "h": 60, "d": 1440, "w": 10080}[match.group(2) or "m"]
    try:
        duration = pd.Timedelta(minutes=minutes)
    except (OverflowError, ValueError) as exc:
        raise ValueError("research_timeframe_duration_overflow") from exc
    if not isinstance(duration, pd.Timedelta):
        raise ValueError("research_timeframe_duration_invalid")
    return duration


def simulate_signals(
    signals: Iterable[dict[str, Any]], df_map: dict[str, pd.DataFrame], *,
    test_start, test_end, account_equity: float, commission_pct: float,
    slippage_pct: float, train_predictor=None,
) -> list[dict]:
    equity, commission, slippage = (finite_number(value) for value in (account_equity, commission_pct, slippage_pct))
    if (equity is None or equity <= 0 or commission is None or not 0 <= commission < 1
            or slippage is None or not 0 <= slippage < 1):
        raise ValueError("invalid_backtest_execution_cost_or_equity")
    account_equity, commission_pct, slippage_pct = equity, commission, slippage
    window_start, window_end = pd.to_datetime(test_start, utc=True), pd.to_datetime(test_end, utc=True)
    if (not isinstance(window_start, pd.Timestamp) or not isinstance(window_end, pd.Timestamp)
            or pd.isna(window_start) or pd.isna(window_end) or window_start >= window_end):
        raise ValueError("invalid_backtest_execution_window")
    results = []
    risk_manager = RiskManager(account_equity)
    for signal in signals:
        key = f"{signal.get('asset')}|{signal.get('timeframe')}"
        frame = df_map.get(key)
        if frame is None or frame.empty or signal.get("timestamp") is None:
            continue
        decision = pd.to_datetime(signal["timestamp"], utc=True)
        if not isinstance(decision, pd.Timestamp) or pd.isna(decision):
            raise ValueError("invalid_backtest_decision_timestamp")
        lower, upper = max(decision, window_start), window_end
        direction = str(signal.get("direction") or "").upper()
        if direction not in {"LONG", "SHORT", "BUY", "SELL"}:
            continue
        long = direction in {"LONG", "BUY"}
        entry, stop = float(signal.get("entry") or 0), float(signal.get("stop_loss") or 0)
        targets = signal.get("take_profit") or signal.get("targets") or []
        if not targets or not all(math.isfinite(value) and value > 0 for value in (entry, stop)):
            continue
        if (long and stop >= entry) or (not long and stop <= entry):
            continue
        if train_predictor is not None:
            probability = float(train_predictor(signal))
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("invalid_backtest_model_probability")
            if probability < 0.5:
                continue
        risk_pct = min(1.0, max(0.0, float(risk_manager.get_dynamic_risk_pct(signal))))
        risk_budget = account_equity * risk_pct / 100
        requested = risk_manager.calculate_position_size(signal, account_equity)
        if not math.isfinite(requested) or requested <= 0:
            continue
        def target_price(item: Any) -> float:
            value = item.get("price") if isinstance(item, dict) else item
            if value is None:
                raise ValueError("target_price_missing")
            return float(value)
        target_prices = [target_price(item) for item in targets]
        if not all(math.isfinite(price) and (price > entry if long else 0 < price < entry) for price in target_prices):
            continue
        target_prices = sorted(target_prices, reverse=not long)
        # Preserve supplied per-target allocations in their price order.
        ordered_targets = sorted(targets, key=target_price, reverse=not long)
        allocations = [float(item.get("exit_percent", 0)) / 100 if isinstance(item, dict) else 1 / len(targets) for item in ordered_targets]
        if not all(math.isfinite(value) and value >= 0 for value in allocations):
            raise ValueError("invalid_target_allocation")
        if sum(allocations) == 0:
            allocations = [1 / len(targets)] * len(targets)
        if sum(allocations) > 1 + 1e-9:
            raise ValueError("target_allocations_exceed_position")

        source = df_map.get(key + "|orderbook")
        mode = "orderbook"
        if source is None:
            source, mode = df_map.get(key + "|ticks"), "ticks"
        if source is None:
            source, mode = frame, "ohlc"
        # Strictly after the decision: no same-decision or earlier price replay.
        timestamps = pd.to_datetime(source["timestamp"], utc=True)
        if timestamps.isna().any():
            raise ValueError("invalid_backtest_execution_timestamp")
        availability = timestamps + fixed_bar_duration(signal["timeframe"]) if mode == "ohlc" else timestamps
        after_decision = (timestamps > lower) & (timestamps <= upper)
        excluded_unclosed = int((after_decision & (availability > upper)).sum())
        eligible = after_decision & (availability <= upper)
        events = source.loc[eligible, :].copy()
        events["timestamp"] = timestamps.loc[eligible]
        events["_research_execution_available_at"] = availability.loc[eligible]
        events = events.sort_values(by="timestamp", kind="mergesort")
        filled = remaining = pnl = fees = 0.0
        fill_entry = None
        filled_targets = [0.0] * len(target_prices)
        stop_triggered = False
        entry_attempted = False
        ambiguous = 0
        last_price = None
        execution_at = None
        last_observation_at = None
        stop_exit = stop * (1 - slippage_pct if long else 1 + slippage_pct)

        def levels(value) -> list[list[float]]:
            parsed = [[float(item[0]), float(item[1])] for item in (value or [])]
            if not all(math.isfinite(price) and math.isfinite(size) and price > 0 and size > 0 for price, size in parsed):
                raise ValueError("invalid_orderbook_level")
            return parsed

        def debit_exit(price: float, quantity: float) -> None:
            nonlocal pnl, remaining, fees
            if fill_entry is None:
                raise RuntimeError("exit_before_entry")
            exit_price = price * (1 - slippage_pct if long else 1 + slippage_pct)
            fee = exit_price * quantity * commission_pct
            pnl += ((exit_price - fill_entry) if long else (fill_entry - exit_price)) * quantity - fee
            fees += fee
            remaining -= quantity

        for event in events.to_dict(orient="records"):
            last_observation_at = event["_research_execution_available_at"].isoformat()
            if mode == "orderbook":
                asks, bids = sorted(levels(event.get("asks"))), sorted(levels(event.get("bids")), reverse=True)
                entry_levels, exit_levels = (asks, bids) if long else (bids, asks)
                if not entry_levels or not exit_levels:
                    continue
                start_price, market_price = entry_levels[0][0], exit_levels[0][0]
                capacity = sum(size for _, size in entry_levels)
                high = low = market_price
            elif mode == "ticks":
                start_price = market_price = float(event["price"])
                raw_size = next((event.get(name) for name in ("size", "qty", "volume") if event.get(name) is not None), 0)
                capacity = max(0.0, float(raw_size if raw_size is not None else 0))
                high = low = market_price
                exit_levels = [[market_price, capacity]]
            else:
                start_price, market_price = float(event["open"]), float(event["close"])
                high, low = float(event["high"]), float(event["low"])
                capacity = max(0.0, float(event.get("volume") or 0))
                exit_levels = [[market_price, capacity]]
            if not all(math.isfinite(value) and value > 0 for value in (start_price, market_price, high, low)) or not math.isfinite(capacity):
                raise ValueError("invalid_execution_observation")
            if mode == "ohlc" and (low > high or not low <= start_price <= high or not low <= market_price <= high):
                raise ValueError("impossible_execution_ohlc")
            last_price = market_price
            if not entry_attempted:
                entry_attempted = True
                # Limit orders need evidence of a crossing; no fill outside the
                # observed range. Queues remain unverified, so no optimistic
                # fill is awarded merely because a candle touched a limit.
                if str(signal.get("order_type") or "market").lower() != "market":
                    break
                worst_quote = (max(price for price, _ in entry_levels) if long else min(price for price, _ in entry_levels)) if mode == "orderbook" else start_price
                adverse_entry = worst_quote * (1 + slippage_pct if long else 1 - slippage_pct)
                # The loss budget includes adverse execution at BOTH ends and
                # commission on both notionals. A later market gap can still
                # exceed that modeled budget and must remain visible in PnL.
                cost_per_unit = abs(adverse_entry - stop_exit) + commission_pct * (adverse_entry + stop_exit)
                if not math.isfinite(cost_per_unit) or cost_per_unit <= 0 or adverse_entry <= 0:
                    raise ValueError("invalid_backtest_stop_cost")
                filled = min(requested, capacity, risk_budget / cost_per_unit,
                             account_equity * 0.1 / adverse_entry)
                if filled * cost_per_unit > risk_budget or filled * adverse_entry > account_equity * 0.1:
                    filled = math.nextafter(filled, 0.0)
                if filled <= 0:
                    break
                if mode == "orderbook":
                    consumed = notional = 0.0
                    for price, size in entry_levels:
                        quantity = min(filled - consumed, size)
                        notional += price * quantity
                        consumed += quantity
                        if consumed >= filled:
                            break
                    start_price = notional / filled
                fill_entry = start_price * (1 + slippage_pct if long else 1 - slippage_pct)
                # A gap past the intended stop invalidates entry geometry.
                if (long and fill_entry <= stop) or (not long and fill_entry >= stop):
                    filled = 0
                    break
                remaining = filled
                entry_fee = fill_entry * filled * commission_pct
                pnl, fees = -entry_fee, entry_fee
                execution_at = event["timestamp"].isoformat()
                if mode in {"ticks", "orderbook"}:
                    continue  # Entry snapshot liquidity cannot be reused for exits.
                capacity = max(0.0, capacity - filled)
            if remaining <= 1e-12:
                break
            hit_stop = low <= stop if long else high >= stop
            hit_targets = [high >= price if long else low <= price for price in target_prices]
            if hit_stop and any(hit_targets) and mode == "ohlc":
                ambiguous += 1
            stop_triggered |= hit_stop
            if stop_triggered:
                if mode == "ohlc":
                    stop_price = min(stop, start_price) if long else max(stop, start_price)
                    debit_exit(stop_price, min(remaining, capacity))
                else:
                    for price, size in exit_levels:
                        debit_exit(price, min(remaining, size))
                        if remaining <= 1e-12:
                            break
            else:
                for index, target in enumerate(target_prices):
                    if not hit_targets[index]:
                        continue
                    outstanding = max(0.0, filled * allocations[index] - filled_targets[index])
                    if mode == "ohlc":
                        quantity = min(outstanding, remaining, capacity)
                        debit_exit(target, quantity)
                        capacity -= quantity
                        filled_targets[index] += quantity
                    else:
                        for level in exit_levels:
                            price, size = level
                            if (long and price < target) or (not long and price > target):
                                continue
                            quantity = min(outstanding, remaining, size)
                            debit_exit(target, quantity)  # Limit exit never earns favorable slippage.
                            level[1] -= quantity
                            outstanding -= quantity
                            filled_targets[index] += quantity
                            if outstanding <= 1e-12 or remaining <= 1e-12:
                                break
            if remaining <= 1e-12:
                break
        closed = filled > 0 and remaining <= 1e-12
        unrealized = remaining * ((last_price - fill_entry) if long else (fill_entry - last_price)) if fill_entry is not None and last_price else 0
        modeled_stop_risk = filled * (abs(fill_entry - stop_exit)
            + commission_pct * (fill_entry + stop_exit)) if fill_entry is not None else 0.0
        return_value = pnl / account_equity
        if not all(math.isfinite(value) for value in (pnl, unrealized, return_value, fees,
                                                     filled, remaining, risk_budget, modeled_stop_risk)):
            raise ValueError("backtest_execution_arithmetic_overflow")
        results.append({"pnl": pnl, "unrealized_pnl": unrealized, "return": return_value,
                        "win": pnl > 0 if closed else None, "n_trades": int(closed),
                        "win_count": int(closed and pnl > 0), "loss_count": int(closed and pnl <= 0),
                        "requested_quantity": requested, "filled_quantity": filled,
                        "remaining_quantity": remaining, "fill_entry": fill_entry,
                        "entry_execution_at": execution_at, "fee_cost": fees,
                        "last_observation_available_at": last_observation_at,
                        "excluded_unclosed_candles": excluded_unclosed,
                        "risk_budget": risk_budget,
                        "modeled_stop_risk": modeled_stop_risk,
                        "risk_budget_breached": -pnl > risk_budget + max(1e-10, risk_budget * 1e-12),
                        "same_bar_ambiguities": ambiguous, "fill_policy_version": FILL_POLICY_VERSION,
                        "status": "CLOSED" if closed else "OPEN" if filled else "NOT_FILLED",
                        "evidence_class": "simulation", "source": mode,
                        "limitations": ["spot_unit_sizing_only", "instrument_specific_costs_unverified",
                                        "queue_and_capacity_calibration_unverified",
                                        "portfolio_aggregation_unverified", "gap_losses_not_bounded_by_stop",
                                        "fixed_duration_bar_calendar_unverified"]})
    return results
