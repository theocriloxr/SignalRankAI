"""Owner decisions of 24 Oct 2026 (docs/release/requirements_conflicts.md):
keep current cooldown semantics, current duplicate detection and current
XAUTUSDT handling. Changing any of these needs a new recorded owner decision."""
from core.asset_registry import resolve_asset_spec
from core.production_integrity import max_signal_age_seconds
from engine.signal_deduplicator import _entry_bucket, compute_signal_fingerprint
from engine.signal_lock import LOCK_TTL_SECONDS
from services.asset_repeat_policy import DEFAULT_ASSET_REPEAT_LOCK_HOURS


def test_cooldown_and_freshness_semantics_stay_current(monkeypatch):
    for name in ("DELIVERY_MAX_SIGNAL_AGE_SECONDS", "DELIVERY_MAX_SIGNAL_AGE_15M_SECONDS",
                 "DELIVERY_MAX_SIGNAL_AGE_1H_SECONDS", "DELIVERY_MAX_SIGNAL_AGE_4H_SECONDS",
                 "DELIVERY_MAX_SIGNAL_AGE_1D_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    assert {tf: max_signal_age_seconds(tf) for tf in ("15m", "1h", "4h", "1d")} == {
        "15m": 600, "1h": 1800, "4h": 5400, "1d": 21600}
    assert {tf: LOCK_TTL_SECONDS[tf] for tf in ("15m", "1h", "4h", "1d")} == {
        "15m": 3600, "1h": 7200, "4h": 14400, "1d": 21600}
    assert DEFAULT_ASSET_REPEAT_LOCK_HOURS == 4.0


def test_duplicate_detection_keeps_current_persistence_semantics(monkeypatch):
    """The authoritative near-duplicate suppression is the 0.3 % logarithmic thesis
    band plus the 0.3 % semantic entry tolerance applied when signals are stored."""
    from core.production_integrity import semantic_entries_equivalent, signal_thesis_fingerprint

    monkeypatch.delenv("SIGNAL_THESIS_ENTRY_BAND_PCT", raising=False)
    monkeypatch.delenv("SIGNAL_SEMANTIC_ENTRY_TOLERANCE_PCT", raising=False)
    monkeypatch.delenv("THESIS_FINGERPRINT_INCLUDE_TIMEFRAME", raising=False)
    base = {"asset": "EURUSD", "direction": "long", "strategy_name": "trend_pullback"}
    same = signal_thesis_fingerprint({**base, "entry": 1.0870, "timeframe": "1h"})
    assert same == signal_thesis_fingerprint({**base, "entry": 1.0872, "timeframe": "15m"})
    assert same != signal_thesis_fingerprint({**base, "entry": 1.0950, "timeframe": "1h"})
    assert semantic_entries_equivalent(100, 100.25) and not semantic_entries_equivalent(100, 100.35)


def test_engine_redis_prefilter_is_recorded_as_is():
    """Known quirk kept by owner decision: for prices >= 1 the engine-local Redis
    pre-filter bucket equals the entry (6 significant digits); below 1 it rounds to
    0.001. Durable dedup above remains authoritative."""
    assert _entry_bucket(100.04) == "100.04" and _entry_bucket(1.08415) == "1.08415"
    assert _entry_bucket(0.5004) == _entry_bucket(0.5)
    base = {"asset": "EURUSD", "direction": "long", "timeframe": "1h"}
    assert compute_signal_fingerprint({**base, "entry": 1.08412}) != compute_signal_fingerprint({**base, "entry": 1.08415})


def test_xautusdt_keeps_continuous_tokenised_commodity_handling():
    spec = resolve_asset_spec("XAUTUSDT")
    assert (spec.asset_class, spec.subtype, spec.session_calendar, spec.continuous) == (
        "crypto", "tokenised_commodity", "crypto_24_7", True)
