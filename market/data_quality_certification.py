"""Asset-aware, fail-closed candle certification before signal generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from core.asset_classes import AssetClass, canonical_asset_class
from engine.adaptive.data_quality import assess_candle_quality, candle_timestamp, normalise_candles


@dataclass(frozen=True, slots=True)
class MarketDataCertification:
    usable: bool
    quarantined: bool
    asset_class: str
    timeframe: str
    score: float
    reasons: tuple[str, ...]
    session_gap_count: int
    timezone_error_count: int
    corporate_action_adjusted: bool | None
    contract_metadata_valid: bool | None
    feed_type: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}


def _is_expected_closure(previous_ms: int, current_ms: int, asset_class: AssetClass) -> bool:
    if asset_class is AssetClass.CRYPTO:
        return False
    previous = datetime.fromtimestamp(previous_ms / 1000, tz=timezone.utc)
    current = datetime.fromtimestamp(current_ms / 1000, tz=timezone.utc)
    if asset_class in {AssetClass.EQUITY, AssetClass.INDEX} and previous.date() != current.date():
        return True
    elapsed_hours = (current - previous).total_seconds() / 3600.0
    # FX and commodity feeds legitimately skip the Friday-close to Sunday-open
    # interval. Keep this bounded so a week-long outage is never normalized as
    # a routine closure merely because it crosses a Saturday.
    if elapsed_hours <= 80.0:
        cursor = previous.date()
        while cursor <= current.date():
            if cursor.weekday() == 5:
                return True
            cursor = cursor.fromordinal(cursor.toordinal() + 1)
    # Many FX and futures feeds omit a short rollover/maintenance window. A
    # bounded overnight gap is expected; an equivalent intraday hole is not.
    if (
        asset_class in {AssetClass.FOREX, AssetClass.COMMODITY}
        and previous.date() != current.date()
        and elapsed_hours <= 8.0
    ):
        return True
    return False


def certify_market_candles(
    candles: Iterable[Mapping[str, Any]],
    *,
    asset_class: object,
    timeframe: str,
    provider: str = "unknown",
    data_age_seconds: float | None = None,
    metadata: Mapping[str, Any] | None = None,
    minimum_candles: int = 30,
) -> MarketDataCertification:
    canonical = canonical_asset_class(asset_class)
    rows = normalise_candles(candles)
    base = assess_candle_quality(
        rows,
        timeframe=timeframe,
        provider=provider,
        data_age_seconds=data_age_seconds,
        minimum_candles=minimum_candles,
    )
    meta = dict(metadata or {})
    reasons = [reason for reason in base.reasons if not reason.startswith("gaps:")]
    expected_ms = _SECONDS.get(str(timeframe).lower(), 3600) * 1000
    session_gap_count = 0
    timezone_errors = 0
    previous: int | None = None
    for row in rows:
        timestamp = candle_timestamp(row)
        if timestamp is None:
            timezone_errors += 1
            continue
        if timestamp > int(datetime.now(timezone.utc).timestamp() * 1000) + expected_ms:
            timezone_errors += 1
        if previous and timestamp - previous > expected_ms * 1.8 and not _is_expected_closure(previous, timestamp, canonical):
            session_gap_count += max(1, round((timestamp - previous) / expected_ms) - 1)
        previous = timestamp
    if session_gap_count:
        reasons.append(f"unexpected_session_gaps:{session_gap_count}")
    if timezone_errors:
        reasons.append(f"timezone_errors:{timezone_errors}")

    corporate_adjusted: bool | None = None
    contract_valid: bool | None = None
    feed_type = str(meta.get("feed_type") or "").strip().lower() or None
    if canonical is AssetClass.EQUITY:
        corporate_adjusted = bool(meta.get("split_adjusted") and meta.get("dividend_adjusted"))
        if meta.get("corporate_actions_required") and not corporate_adjusted:
            reasons.append("unadjusted_corporate_actions")
    elif canonical is AssetClass.COMMODITY and str(meta.get("instrument_type") or "").lower() in {"future", "futures", "continuous_future"}:
        contract_valid = bool(meta.get("contract_expiry") and meta.get("roll_method"))
        if not contract_valid:
            reasons.append("missing_contract_roll_metadata")
    elif canonical is AssetClass.INDEX:
        if feed_type is None:
            provider_name = str(provider or "").strip().lower()
            if any(token in provider_name for token in ("yahoo", "yfinance")):
                feed_type = "cash_index"
            elif any(token in provider_name for token in ("metaapi", "oanda", "broker")):
                feed_type = "cfd"
        if feed_type not in {"cash_index", "cfd", "future", "continuous_future"}:
            reasons.append("ambiguous_index_feed_type")
    elif canonical is AssetClass.CRYPTO and meta.get("exchange_outage"):
        reasons.append("exchange_outage")
    elif canonical is AssetClass.FOREX and meta.get("quote_conversion_required") and not meta.get("quote_conversion_rate"):
        reasons.append("missing_quote_currency_conversion")

    fatal_prefixes = (
        "insufficient_candles", "stale_candles", "impossible_ohlc", "missing_prices",
        "duplicates", "unexpected_session_gaps", "timezone_errors", "unadjusted_corporate_actions",
        "missing_contract_roll_metadata", "ambiguous_index_feed_type", "exchange_outage",
        "missing_quote_currency_conversion",
    )
    fatal = any(reason.startswith(fatal_prefixes) for reason in reasons)
    score = max(0.0, base.score - min(0.5, 0.03 * session_gap_count + 0.1 * timezone_errors))
    return MarketDataCertification(
        usable=bool(base.usable and not fatal),
        quarantined=fatal,
        asset_class=canonical.value,
        timeframe=str(timeframe).lower(),
        score=round(score, 4),
        reasons=tuple(reasons),
        session_gap_count=session_gap_count,
        timezone_error_count=timezone_errors,
        corporate_action_adjusted=corporate_adjusted,
        contract_metadata_valid=contract_valid,
        feed_type=feed_type,
    )
