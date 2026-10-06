"""Research statistics with explicit units and bounded, reproducible computation.

DSR follows Bailey/López de Prado (2014). Its inputs are
unannualized Sharpe ratios of equally spaced excess returns. Irregular trade R
is descriptive evidence, never automatically treated as a daily return series.
"""
from __future__ import annotations

import math
import random
from itertools import combinations
from statistics import NormalDist, mean, median, stdev
from typing import Sequence

METHOD_VERSION = "research-statistics-v1"
MAXIMUM_CSCV_SAMPLE_VISITS = 2_000_000


def _values(values: Sequence[float], minimum: int = 2) -> list[float]:
    if not minimum <= len(values) <= 100_000:
        raise ValueError("invalid_research_sample")
    if any(isinstance(value, bool) for value in values):
        raise ValueError("boolean_research_observation")
    parsed = [float(value) for value in values]
    if not all(math.isfinite(value) for value in parsed):
        raise ValueError("invalid_research_sample")
    return parsed


def deflated_sharpe(
    excess_returns: Sequence[float], *, raw_trial_count: int,
    trial_sharpe_variance: float, periods_per_year: float,
    annualization_basis: str, threshold: float = 0.95,
) -> dict:
    values = _values(excess_returns, 30)
    if not isinstance(raw_trial_count, int) or isinstance(raw_trial_count, bool) or raw_trial_count < 1:
        raise ValueError("invalid_raw_trial_count")
    if not annualization_basis.strip() or not math.isfinite(periods_per_year) or periods_per_year <= 0:
        raise ValueError("explicit_annualization_basis_required")
    if not math.isfinite(trial_sharpe_variance) or trial_sharpe_variance < 0 or not 0.5 < threshold < 1:
        raise ValueError("invalid_dsr_policy")
    sigma = stdev(values)
    if sigma <= 0:
        raise ValueError("constant_return_series")
    n = len(values)
    avg = mean(values)
    sr = avg / sigma
    # Population central moments: kurtosis is Pearson, not excess kurtosis.
    m2 = sum((value - avg) ** 2 for value in values) / n
    skew = sum((value - avg) ** 3 for value in values) / n / m2 ** 1.5
    kurtosis = sum((value - avg) ** 4 for value in values) / n / m2 ** 2
    normal = NormalDist()
    expected_max = 0.0
    if raw_trial_count > 1:
        if trial_sharpe_variance <= 0:
            raise ValueError("nonzero_trial_variance_required_for_multiple_tests")
        gamma = 0.5772156649015329
        expected_max = math.sqrt(trial_sharpe_variance) * (
            (1 - gamma) * normal.inv_cdf(1 - 1 / raw_trial_count)
            + gamma * normal.inv_cdf(1 - 1 / (raw_trial_count * math.e))
        )
    variance_factor = 1 - skew * sr + (kurtosis - 1) / 4 * sr * sr
    if variance_factor <= 0:
        raise ValueError("invalid_sharpe_sampling_variance")
    probability = normal.cdf((sr - expected_max) * math.sqrt(n - 1) / math.sqrt(variance_factor))
    lag1 = sum((values[i] - avg) * (values[i - 1] - avg) for i in range(1, n)) / (n * m2)
    # The IID DSR formula is not a serial-dependence correction. Keep the
    # calculated statistic visible while withholding qualification if correlated.
    dependence_verified = abs(lag1) <= 1.96 / math.sqrt(n)
    return {
        "raw_sharpe": sr, "annualized_sharpe": sr * math.sqrt(periods_per_year),
        "annualization_basis": annualization_basis, "periods_per_year": periods_per_year,
        "n_observations": n, "raw_trial_count": raw_trial_count,
        "effective_trial_count": raw_trial_count, "trial_count_method": "raw_count_no_dependence_discount",
        "skew": skew, "kurtosis": kurtosis, "lag1_autocorrelation": lag1,
        "expected_max_sharpe_from_noise": expected_max,
        "deflated_sharpe_probability": probability, "threshold": threshold,
        "serial_dependence_screen_passed": dependence_verified,
        "pass_fail": probability >= threshold and dependence_verified,
        "method_version": METHOD_VERSION, "evidence_class": "research",
    }


def probability_backtest_overfitting(matrix: Sequence[Sequence[float]], *, blocks: int = 8) -> dict:
    """CSCV rank-based PBO; rows are common times, columns are ALL candidates.

    This selection diagnostic does not replace chronological validation. Full
    equally sized partitions are required; no rows or unsuccessful trials may
    be dropped silently. Both partition count and matrix work are bounded.
    """
    if type(blocks) is not int or blocks not in {4, 6, 8, 10, 12} or len(matrix) < blocks * 2 or len(matrix) % blocks:
        raise ValueError("invalid_cscv_partition")
    width = len(matrix[0])
    partitions = math.comb(blocks, blocks // 2)
    sample_visits = len(matrix) * width * partitions
    # Reject from shape metadata before allocating/copying the sample matrix.
    if sample_visits > MAXIMUM_CSCV_SAMPLE_VISITS:
        raise ValueError("cscv_compute_budget_exceeded")
    if not 2 <= width <= 256 or any(len(row) != width for row in matrix):
        raise ValueError("unaligned_trial_matrix")
    rows = [_values(row) for row in matrix]
    size = len(rows) // blocks
    all_blocks = set(range(blocks))
    ranks: list[float] = []

    def scores(selected: set[int]) -> list[float]:
        samples = [[rows[i][j] for b in selected for i in range(b * size, (b + 1) * size)] for j in range(width)]
        if any(stdev(sample) == 0 for sample in samples):
            raise ValueError("constant_cscv_trial")
        return [mean(sample) / stdev(sample) for sample in samples]

    for selected_tuple in combinations(range(blocks), blocks // 2):
        selected = set(selected_tuple)
        inside, outside = scores(selected), scores(all_blocks - selected)
        best = max(inside)
        winners = [j for j, score in enumerate(inside) if math.isclose(score, best, rel_tol=1e-12, abs_tol=1e-12)]
        # Average ties instead of choosing a favorable candidate index.
        candidate_ranks = []
        for winner in winners:
            below = sum(value < outside[winner] and not math.isclose(value, outside[winner], abs_tol=1e-12) for value in outside)
            equal = sum(math.isclose(value, outside[winner], rel_tol=1e-12, abs_tol=1e-12) for value in outside)
            candidate_ranks.append((below + (equal + 1) / 2) / (width + 1))
        ranks.append(mean(candidate_ranks))
    return {"pbo": sum(rank <= 0.5 for rank in ranks) / len(ranks),
            "partitions": len(ranks), "trial_count": width, "observations": len(rows),
            "blocks": blocks, "sample_visits": sample_visits,
            "maximum_sample_visits": MAXIMUM_CSCV_SAMPLE_VISITS,
            "method_version": "cscv-v2", "evidence_class": "research"}


def profit_factor(returns_r: Sequence[float]) -> float | None:
    """Gross wins / gross losses; an unobserved denominator is unavailable."""
    values = _values(returns_r, 1)
    wins = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if not math.isfinite(wins) or not math.isfinite(losses):
        raise ValueError("profit_factor_overflow")
    result = wins / losses if losses else None
    if result is not None and not math.isfinite(result):
        raise ValueError("profit_factor_overflow")
    return result


def return_diagnostics(returns_r: Sequence[float]) -> dict:
    values = _values(returns_r, 1)
    equity = peak = depth = 0.0
    duration = longest = 0
    for value in values:
        equity += value
        peak = max(peak, equity)
        depth = max(depth, peak - equity)
        duration = duration + 1 if equity < peak else 0
        longest = max(longest, duration)
    losses = -sum(value for value in values if value < 0)
    tail = sorted(values)[:max(1, math.ceil(len(values) * 0.05))]
    return {"sample_size": len(values), "expectancy_r": mean(values), "median_r": median(values),
            "total_r": sum(values), "profit_factor": profit_factor(values),
            "profit_factor_reason": None if losses else "no_observed_losses",
            "max_drawdown_r": depth, "max_drawdown_duration_observations": longest,
            "open_drawdown_duration_observations": duration, "expected_shortfall_5pct_r": mean(tail),
            "annualized_sharpe": None, "annualization_basis": "irregular_trade_R_not_time_returns"}


def block_bootstrap_survival(
    returns_r: Sequence[float], *, risk_fraction: float, block_size: int,
    horizon: int, runs: int = 1000, seed: int = 0, ruin_equity_fraction: float = 0.5,
    drawdown_limit: float = 0.1,
) -> dict:
    values = _values(returns_r, 20)
    if not (0 < risk_fraction < 1 and 0 < ruin_equity_fraction < 1 and 0 < drawdown_limit < 1):
        raise ValueError("invalid_survival_risk_policy")
    if not 2 <= block_size <= len(values) or not 1 <= runs <= 10_000 or not 1 <= horizon <= 10_000:
        raise ValueError("invalid_survival_compute_budget")
    if horizon * runs > 2_000_000:
        raise ValueError("survival_compute_budget_exceeded")
    rng = random.Random(seed)
    drawdowns, loss_streaks = [], []
    ruins = breaches = 0
    for _ in range(runs):
        balance = peak = 1.0
        dd = 0.0
        streak = longest = 0
        path: list[float] = []
        while len(path) < horizon:
            start = rng.randrange(len(values) - block_size + 1)
            path.extend(values[start:start + block_size])
        ruined = False
        for value in path[:horizon]:
            balance = max(0.0, balance * (1 + risk_fraction * value))
            peak = max(peak, balance)
            dd = max(dd, 1 - balance / peak)
            streak = streak + 1 if value < 0 else 0
            longest = max(longest, streak)
            ruined |= balance <= ruin_equity_fraction
        ruins += ruined
        breaches += dd >= drawdown_limit
        drawdowns.append(dd)
        loss_streaks.append(longest)
    return {"risk_of_ruin": ruins / runs, "drawdown_breach_probability": breaches / runs,
            "mean_max_drawdown": mean(drawdowns), "p95_max_drawdown": sorted(drawdowns)[math.ceil(runs * 0.95) - 1],
            "p95_loss_streak": sorted(loss_streaks)[math.ceil(runs * 0.95) - 1],
            "risk_fraction": risk_fraction, "ruin_equity_fraction": ruin_equity_fraction,
            "drawdown_limit": drawdown_limit, "block_size": block_size,
            "horizon": horizon, "runs": runs, "seed": seed,
            "method_version": "moving_block_bootstrap_v1", "evidence_class": "simulation",
            "limitations": ["conditional_on_observed_R", "no_unobserved_gap_or_liquidity_model"]}
