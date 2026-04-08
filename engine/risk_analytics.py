from __future__ import annotations

import math
import random
from typing import Any


def sharpe_ratio(returns: list[float], risk_free_rate: float = 0.0) -> float:
    if not returns:
        return 0.0
    n = len(returns)
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / max(1, n - 1)
    std = math.sqrt(max(variance, 0.0))
    if std <= 0:
        return 0.0
    return (mean_r - risk_free_rate) / std


def sortino_ratio(returns: list[float], target_return: float = 0.0) -> float:
    if not returns:
        return 0.0
    n = len(returns)
    mean_r = sum(returns) / n
    downside = [min(0.0, r - target_return) for r in returns]
    downside_var = sum(d ** 2 for d in downside) / max(1, n - 1)
    downside_dev = math.sqrt(max(downside_var, 0.0))
    if downside_dev <= 0:
        return 0.0
    return (mean_r - target_return) / downside_dev


def monte_carlo_monthly_projection(
    starting_capital: float,
    risk_pct_per_trade: float,
    win_rate: float,
    avg_win_r: float,
    avg_loss_r: float,
    trades_per_month: int = 30,
    runs: int = 1000,
) -> dict[str, Any]:
    start = max(float(starting_capital), 1.0)
    risk_pct = max(0.0001, float(risk_pct_per_trade) / 100.0)
    wr = min(0.9999, max(0.0001, float(win_rate)))
    win_r = max(0.0001, float(avg_win_r))
    loss_r = max(0.0001, float(avg_loss_r))

    ending_values: list[float] = []
    ruin_count = 0

    for _ in range(max(1, int(runs))):
        bal = start
        for _t in range(max(1, int(trades_per_month))):
            risk_amt = bal * risk_pct
            if random.random() < wr:
                bal += risk_amt * win_r
            else:
                bal -= risk_amt * loss_r
            if bal <= 0:
                ruin_count += 1
                bal = 0.0
                break
        ending_values.append(bal)

    ending_values.sort()
    n = len(ending_values)
    p05 = ending_values[max(0, int(0.05 * (n - 1)))]
    p50 = ending_values[max(0, int(0.50 * (n - 1)))]
    p95 = ending_values[max(0, int(0.95 * (n - 1)))]

    return {
        "runs": n,
        "start": round(start, 2),
        "p05": round(p05, 2),
        "p50": round(p50, 2),
        "p95": round(p95, 2),
        "ruin_probability_pct": round((ruin_count / n) * 100.0, 2),
    }
