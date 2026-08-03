"""Production integrity helpers for signal freshness, identity and public claims.

The functions in this module are deliberately deterministic and side-effect free so
that the delivery, paper, performance, copy-trading and live-execution paths use the
same policy rather than maintaining slightly different interpretations.
"""
from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except Exception:
        value = float(default)
    if minimum is not None:
        value = max(float(minimum), value)
    if maximum is not None:
        value = min(float(maximum), value)
    return value


def _as_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def canonical_direction(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"buy", "bull", "bullish", "long"}:
        return "long"
    if raw in {"sell", "bear", "bearish", "short"}:
        return "short"
    return raw or "unknown"


def canonical_timeframe(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "")
    aliases = {
        "60m": "1h", "1hr": "1h", "1hour": "1h",
        "240m": "4h", "4hr": "4h", "4hour": "4h",
        "24h": "1d", "1day": "1d", "daily": "1d",
    }
    return aliases.get(raw, raw or "1h")


def canonical_strategy(value: Any) -> str:
    return " ".join(str(value or "unknown").strip().lower().split()) or "unknown"


def signal_thesis_scope(signal: Mapping[str, Any]) -> str:
    """Return the stable semantic scope used for locks and near-entry comparison."""
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    direction = canonical_direction(signal.get("direction"))
    strategy = canonical_strategy(signal.get("strategy_name") or signal.get("strategy"))
    return f"{asset}|{direction}|{strategy}"


def semantic_entry_tolerance_pct() -> float:
    return _env_float("SIGNAL_SEMANTIC_ENTRY_TOLERANCE_PCT", 0.003, 0.0001, 0.05)


def semantic_entry_gap(first: Any, second: Any) -> float | None:
    try:
        first_f = float(first)
        second_f = float(second)
    except Exception:
        return None
    if not math.isfinite(first_f) or not math.isfinite(second_f) or first_f <= 0 or second_f <= 0:
        return None
    return abs(first_f - second_f) / max(abs(first_f), abs(second_f), 1e-9)


def semantic_entries_equivalent(first: Any, second: Any, *, tolerance: float | None = None) -> bool:
    gap = semantic_entry_gap(first, second)
    threshold = semantic_entry_tolerance_pct() if tolerance is None else max(0.0001, min(0.05, float(tolerance)))
    return gap is not None and gap <= threshold


_DEFAULT_MAX_AGE_SECONDS = {
    "1m": 120,
    "3m": 180,
    "5m": 300,
    "15m": 600,
    "30m": 900,
    "1h": 1800,
    "2h": 2700,
    "4h": 5400,
    "6h": 7200,
    "8h": 9000,
    "12h": 10800,
    "1d": 21600,
}


def max_signal_age_seconds(timeframe: Any, *, purpose: str = "delivery") -> int:
    """Return the maximum accepted signal age for an execution purpose.

    Purpose-specific environment variables can override the shared default, e.g.
    ``PAPER_MAX_SIGNAL_AGE_1H_SECONDS`` or ``LIVE_MAX_SIGNAL_AGE_15M_SECONDS``.
    """
    tf = canonical_timeframe(timeframe)
    default = int(_DEFAULT_MAX_AGE_SECONDS.get(tf, 1800))
    prefix = str(purpose or "delivery").strip().upper()
    tf_key = tf.upper().replace("M", "M").replace("H", "H").replace("D", "D")
    specific = os.getenv(f"{prefix}_MAX_SIGNAL_AGE_{tf_key}_SECONDS")
    generic = os.getenv(f"{prefix}_MAX_SIGNAL_AGE_SECONDS")
    raw = specific if specific not in (None, "") else generic
    if raw not in (None, ""):
        try:
            default = int(raw)
        except Exception:
            pass
    return max(30, min(7 * 24 * 3600, int(default)))


def signal_age_seconds(generated_at: datetime | None, *, now: datetime | None = None) -> float | None:
    generated = _as_utc_naive(generated_at)
    if generated is None:
        return None
    current = _as_utc_naive(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    return max(0.0, (current - generated).total_seconds())


@dataclass(frozen=True, slots=True)
class FreshnessDecision:
    ok: bool
    age_seconds: float | None
    max_age_seconds: int
    reason: str


def evaluate_signal_freshness(
    *,
    timeframe: Any,
    generated_at: datetime | None,
    expires_at: datetime | None = None,
    delivered_at: datetime | None = None,
    now: datetime | None = None,
    purpose: str = "delivery",
    explicit_age_seconds: float | None = None,
) -> FreshnessDecision:
    maximum = max_signal_age_seconds(timeframe, purpose=purpose)

    # Use the historical delivery time when validating an old delivery.
    # Otherwise use the supplied `now` or the current UTC time.
    reference_time = (
        _as_utc_naive(delivered_at or now)
        or datetime.now(timezone.utc).replace(tzinfo=None)
    )

    normalized_expiry = _as_utc_naive(expires_at)

    age = explicit_age_seconds
    if age is None:
        age = signal_age_seconds(
            generated_at,
            now=reference_time,
        )

    # An explicit database expiry is authoritative even when the normal
    # timeframe age threshold has not yet been exceeded.
    if normalized_expiry is not None and reference_time >= normalized_expiry:
        return FreshnessDecision(
            False,
            float(age) if age is not None else None,
            maximum,
            "signal_expired",
        )

    if age is None:
        if _env_bool(
            f"{str(purpose).upper()}_REQUIRE_GENERATED_AT",
            True,
        ):
            return FreshnessDecision(
                False,
                None,
                maximum,
                "generated_at_missing",
            )

        return FreshnessDecision(
            True,
            None,
            maximum,
            "generated_at_unavailable_allowed",
        )

    if float(age) > float(maximum):
        return FreshnessDecision(
            False,
            float(age),
            maximum,
            "signal_stale",
        )

    return FreshnessDecision(
        True,
        float(age),
        maximum,
        "fresh",
    )

def _entry_band(entry: Any) -> str:
    try:
        price = float(entry)
    except Exception:
        price = 0.0
    if not math.isfinite(price) or price <= 0:
        return "0"
    band_pct = _env_float("SIGNAL_THESIS_ENTRY_BAND_PCT", 0.003, 0.0001, 0.05)
    # Use logarithmic relative-price buckets. ``price / (price * pct)`` is a
    # constant and therefore cannot distinguish materially repriced theses.
    # Log buckets preserve percentage scale across BTC, FX and penny assets.
    base = 1.0 + band_pct
    return str(int(math.floor(math.log(price) / math.log(base))))


def signal_thesis_fingerprint(signal: Mapping[str, Any]) -> str:
    """Fingerprint a trade idea while ignoring tiny repricing and delivery IDs.

    Timeframe is intentionally omitted by default so the same directional thesis
    cannot spam a user merely by switching between 15m and 1h. Set
    ``THESIS_FINGERPRINT_INCLUDE_TIMEFRAME=1`` only after a documented policy review.
    """
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    direction = canonical_direction(signal.get("direction"))
    strategy = canonical_strategy(signal.get("strategy_name") or signal.get("strategy"))
    regime = str(signal.get("regime") or signal.get("market_regime") or "unknown").lower().strip()
    entry = signal.get("entry") or signal.get("close_price")
    # Regime and timeframe are intentionally excluded by default. Both can
    # oscillate between adjacent engine cycles while the user-visible trade idea
    # (asset, direction, strategy and entry band) remains unchanged.
    parts = [asset, direction, strategy, _entry_band(entry)]
    if _env_bool("THESIS_FINGERPRINT_INCLUDE_REGIME", False):
        parts.append(regime)
    if _env_bool("THESIS_FINGERPRINT_INCLUDE_TIMEFRAME", False):
        parts.append(canonical_timeframe(signal.get("timeframe")))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def wilson_lower_bound(successes: int, total: int, *, z: float = 1.96) -> float:
    """Wilson lower confidence bound for a Bernoulli success rate."""
    n = max(0, int(total))
    if n <= 0:
        return 0.0
    k = max(0, min(n, int(successes)))
    p = k / n
    denom = 1.0 + (z * z) / n
    centre = p + (z * z) / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)
    return max(0.0, min(1.0, (centre - margin) / denom))


@dataclass(frozen=True, slots=True)
class PublicClaimDecision:
    allowed: bool
    reason: str
    observed_win_rate: float
    lower_bound: float
    sample_size: int
    terminal_coverage: float
    unique_theses: int


def evaluate_public_win_rate_claim(
    *,
    wins: int,
    losses: int,
    delivered: int,
    resolved: int,
    unique_theses: int,
    target_rate: float | None = None,
) -> PublicClaimDecision:
    target = float(target_rate if target_rate is not None else _env_float("PUBLIC_WIN_RATE_CLAIM_TARGET", 0.60, 0.0, 1.0))
    sample = max(0, int(wins) + int(losses))
    observed = int(wins) / sample if sample else 0.0
    lower = wilson_lower_bound(int(wins), sample)
    coverage = int(resolved) / int(delivered) if int(delivered) > 0 else 0.0
    min_sample = int(_env_float("PUBLIC_CLAIM_MIN_TERMINAL_SAMPLE", 200, 10, 100000))
    min_unique = int(_env_float("PUBLIC_CLAIM_MIN_UNIQUE_THESES", 100, 5, 100000))
    min_coverage = _env_float("PUBLIC_CLAIM_MIN_TERMINAL_COVERAGE", 0.95, 0.5, 1.0)

    if sample < min_sample:
        reason = f"terminal_sample_below_{min_sample}"
    elif int(unique_theses) < min_unique:
        reason = f"unique_theses_below_{min_unique}"
    elif coverage < min_coverage:
        reason = f"terminal_coverage_below_{min_coverage:.2f}"
    elif lower < target:
        reason = f"confidence_lower_bound_below_{target:.2f}"
    else:
        reason = "claim_statistically_supported"
    return PublicClaimDecision(
        allowed=reason == "claim_statistically_supported",
        reason=reason,
        observed_win_rate=observed,
        lower_bound=lower,
        sample_size=sample,
        terminal_coverage=coverage,
        unique_theses=int(unique_theses),
    )




def calibration_evidence_valid(signal: Mapping[str, Any]) -> bool:
    """Validate held-out calibration evidence attached to a persisted signal.

    A boolean flag alone is insufficient: the artifact must carry enough held-out
    observations and pass Brier/ECE thresholds. This prevents a raw model score
    from being relabelled as a public win probability.
    """
    if signal.get("ml_probability_calibrated") is None:
        return False
    if not str(signal.get("ml_calibration_version") or "").strip():
        return False
    if not bool(signal.get("ml_calibration_validated", False)):
        return False
    try:
        rows = int(signal.get("ml_calibration_validation_rows") or 0)
    except Exception:
        rows = 0
    minimum_rows = int(_env_float("ML_MIN_CALIBRATION_VALIDATION_ROWS", 100, 20, 10000000))
    if rows < minimum_rows:
        return False
    metrics_required = _env_bool("ML_PUBLIC_CALIBRATION_METRICS_REQUIRED", True)
    if not metrics_required:
        return True
    try:
        brier = float(signal.get("ml_calibration_brier"))
        ece = float(signal.get("ml_calibration_ece"))
    except Exception:
        return False
    max_brier = _env_float("ML_MAX_CALIBRATION_BRIER", 0.25, 0.0, 1.0)
    max_ece = _env_float("ML_MAX_CALIBRATION_ECE", 0.10, 0.0, 1.0)
    return math.isfinite(brier) and math.isfinite(ece) and brier <= max_brier and ece <= max_ece


@dataclass(frozen=True, slots=True)
class ProbabilityDisplay:
    probability: float | None
    calibrated: bool
    label: str
    version: str | None


def probability_for_public_display(signal: Mapping[str, Any]) -> ProbabilityDisplay:
    calibrated_raw = signal.get("ml_probability_calibrated")
    version = str(signal.get("ml_calibration_version") or "").strip() or None
    calibrated = (
        calibrated_raw is not None
        and version is not None
        and calibration_evidence_valid(signal)
    )
    if calibrated:
        try:
            value = max(0.0, min(1.0, float(calibrated_raw)))
        except Exception:
            value = None
        return ProbabilityDisplay(value, value is not None, "Calibrated win probability", version)

    raw = signal.get("ml_probability_raw")
    if raw is None:
        raw = signal.get("ml_probability")
    try:
        raw_value = max(0.0, min(1.0, float(raw))) if raw is not None else None
    except Exception:
        raw_value = None
    if _env_bool("ML_PROBABILITY_DISPLAY_REQUIRES_CALIBRATION", True):
        return ProbabilityDisplay(None, False, "Model score (uncalibrated)", None)
    return ProbabilityDisplay(raw_value, False, "Model score (uncalibrated)", None)


__all__ = [
    "FreshnessDecision",
    "ProbabilityDisplay",
    "PublicClaimDecision",
    "calibration_evidence_valid",
    "canonical_direction",
    "canonical_strategy",
    "canonical_timeframe",
    "evaluate_public_win_rate_claim",
    "evaluate_signal_freshness",
    "max_signal_age_seconds",
    "probability_for_public_display",
    "semantic_entries_equivalent",
    "semantic_entry_gap",
    "semantic_entry_tolerance_pct",
    "signal_age_seconds",
    "signal_thesis_fingerprint",
    "signal_thesis_scope",
    "wilson_lower_bound",
]
