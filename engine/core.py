#!/usr/bin/env python3
"""
Refactored and fixed main engine loop for SignalRankAI.
- Cleans up control flow and indentation errors
- Adds robust exception handling and logging
- Implements a clear per-asset pipeline: fetch -> indicators -> strategies -> normalize/dedupe -> consensus -> risk/ML -> scoring -> advanced filters -> store -> deliver
- Handles both async/sync provider functions safely
- Contains safe fallbacks for optional modules

Drop this in your repo, review provider/function names if your codebase differs slightly (e.g. method names), and run.
"""

import os
import time
import asyncio
import logging
import threading
import inspect
import json
import pathlib
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List
from datetime import datetime, timedelta as _timedelta, timezone

logger = logging.getLogger(__name__)

# Hard blacklist for zombie stablecoins that persist in database
# These have minimal volatility and should never be traded
HARD_BLACKLIST = ["USDCUSDT", "USDTPERF", "DAIUSDT", "FDUSDUSDT", "USDTUSDC", "TUSDUSDT"]

# Core engine pieces
from signalrank_telegram.tier_delivery import TierDeliveryManager
from engine.signal_analytics import signal_analytics

# Data layer
from data.fetcher import is_crypto, is_binance_blocked, market_closed_reason, is_fx, is_stock
try:
    from data.fetcher import is_commodity
except Exception:
    def is_commodity(asset: Any) -> bool:  # type: ignore
        return False
from data.market_data import fetch_market_data_cached
from data.pair_discovery import get_all_trending_pairs, get_trending_stock_tickers, get_all_tradable_assets
from data.indicators import calculate_indicators
from data.news import get_news_sentiment

# Engine pieces
from engine.regime import detect_market_regime
from engine.risk_manager import RiskManager, CorrelationManager
from engine.exit_manager import ExitManager, PartialExitTracker
from engine.filters import SignalFilter, MarketRegimeFilter, SlippageControl
from engine.backtest import BacktestEngine, OptimizationEngine
from strategies import run_all_strategies
from engine.consensus import apply_consensus_filter
from engine.risk import calculate_dynamic_risk, risk_check
from engine.scoring import calculate_signal_score as score_signal, calculate_confluence

# Portfolio Exposure Manager (Capital Protection)
# Limits open trades per asset class + direction
try:
    from engine.correlation_filter import exposure_manager
except Exception:
    class _DummyExposureManager:
        async def is_trade_allowed(self, session, asset_class, direction):
            return True
    exposure_manager = _DummyExposureManager()
from db.pg_compat import get_all_user_ids_compat, store_signal_compat
from db.repository import persist_decision_log, persist_signal
from engine.signal_deduplicator import MLRejectionTracker
from engine.ranking import rank_signals
from signalrank_telegram.bot import dispatch_signals_async
from core.redis_state import state
from config import OWNER_IDS, ADMIN_IDS

# Optional advanced features (graceful fallback if missing)
try:
    from data.market_data import detect_order_blocks as _detect_order_blocks
except Exception:
    def _detect_order_blocks(candles, lookback=100) -> bool:  # type: ignore
        return False

# Institutional Grade Derivatives Microstructure (Squeeze Detector)
try:
    from engine.derivatives import SqueezeDetector, get_squeeze_bias
except Exception:
    class SqueezeDetector:
        async def get_squeeze_bias(self, asset: str) -> str:
            return "NEUTRAL"
    async def get_squeeze_bias(asset: str) -> str:
        return "NEUTRAL"

# Institutional Grade Market Circuit Breaker (Flash Crash Protection)
try:
    from engine.market_circuit_breaker import MarketCircuitBreaker, check_market_health
except Exception:
    class MarketCircuitBreaker:
        async def check_market_health(self) -> bool:
            return True
    async def check_market_health() -> bool:
        return True

# Golden Loop: Gemini Chief Risk Officer (CRO) with technical context
try:
    from services.gemini_ml import gemini_confluence_check_with_tech_context as _gemini_cro_check
except Exception:
    async def _gemini_cro_check(signal, news_headlines, tech_context) -> bool:  # type: ignore
        return True

try:
    from services.economic_calendar import is_no_trade_zone_sync as _is_no_trade_zone_sync, get_macro_news_context
except Exception:
    def _is_no_trade_zone_sync(symbol: str, buffer_minutes: int = 30) -> bool:  # type: ignore
        return False
    async def get_macro_news_context(now=None):  # type: ignore
        return {}

try:
    from engine.mtf_analysis import MultiTimeframeAnalyzer
except Exception:
    class MultiTimeframeAnalyzer:
        def __init__(self):
            pass
        def get_htf_bias(self, *a, **k):
            return {}
        def validate_against_htf(self, *a, **k):
            return True, ''
        def get_mtf_confluence(self, *a, **k):
            return 0

try:
    from engine.signal_context import SignalContext, SignalCooldownManager, OneBiasPerTimeframe
except Exception:
    class SignalContext:
        def wait_for_candle_close(self, candles, tf):
            return True
        def calculate_entry_zone(self, entry, atr, dir):
            return {'low': entry, 'high': entry}
        def calculate_signal_expiration(self, tf):
            return None
        def detect_trading_session(self):
            return '24x7'
    class SignalCooldownManager:
        def can_send_signal(self, *a, **k):
            return True, ''
        def record_signal(self, *a, **k):
            pass
    class OneBiasPerTimeframe:
        def can_add_signal(self, *a, **k):
            return True, ''
        def set_bias(self, *a, **k):
            pass

try:
    from engine.advanced_filters import SmartFilterSuite
except Exception:
    class SmartFilterSuite:
        def run_all_filters(self, signal, market_filter_data, session):
            return True, []

try:
    from engine.tier_notifications import TierNotificationManager
except Exception:
    class TierNotificationManager:
        def notify(self, *a, **k):
            pass

try:
    from engine.ultra_quality_filter import ultra_quality
except Exception:
    class _UltraStub:
        def apply_ultra_filter(self, s):
            return True, None, 100
        def calculate_dynamic_position_size(self, *a, **k):
            return 1.0, {'method': 'stub'}
    ultra_quality = _UltraStub()

try:
    from utils.async_runner import run_sync
except Exception:
    def run_sync(coro):
        return asyncio.get_event_loop().run_until_complete(coro)

_ml_rejection_tracker = MLRejectionTracker()

# Threshold optimizer for auto-adjusting ML confidence thresholds
_threshold_optimizer = None
try:
    from engine.threshold_optimizer import get_threshold_optimizer, refresh_thresholds
    _threshold_optimizer = get_threshold_optimizer()
except Exception as e:
    logger.warning(f"[engine] threshold_optimizer import failed: {e}, using fallback")
    # Fallback threshold optimizer that uses env var
    class _FallbackThresholdOptimizer:
        def get_threshold(self) -> float:
            return float(os.getenv('ML_PROB_THRESHOLD', '0.55') or 0.55)
        async def analyze_and_adjust(self, force: bool = False):
            return None
        def get_config(self):
            from datetime import datetime
            return type('Config', (), {
                'ml_prob_threshold': self.get_threshold(),
                'min_score_threshold': 60.0,
                'confluence_min': 0.0,
                'last_updated': datetime.utcnow(),
                'source': 'env',
            })()
    _threshold_optimizer = _FallbackThresholdOptimizer()
# Track threshold refresh intervals
_last_threshold_refresh: datetime | None = None
_threshold_refresh_interval_hours: int = 6
_last_macro_snapshot_at: datetime | None = None
_macro_snapshot_cache: dict[str, float] | None = None
try:
    _macro_snapshot_refresh_seconds: int = max(
        300,
        int((os.getenv("MACRO_SNAPSHOT_REFRESH_SECONDS") or "900").strip()),
    )
except Exception:
    _macro_snapshot_refresh_seconds = 900


@dataclass(slots=True)
class _GateHeatmapState:
    empty_cycles: dict[str, int] = field(default_factory=dict)
    gate_counts: dict[str, Counter[str]] = field(default_factory=dict)


_diagnostic_state = _GateHeatmapState()


def _provider_source_name(tf_data: dict[str, Any] | None) -> str:
    source = str((tf_data or {}).get("source") or "").strip().lower()
    if source in {"yfinance", "tradingview", "tradingview_connector", "tradingview_legacy"}:
        return source
    return source


def _record_gate_failure(asset: str, gate: str, reason: str | None = None) -> None:
    asset_key = str(asset or "").upper().strip() or "UNKNOWN"
    gate_key = str(gate or "unknown").strip().lower() or "unknown"
    bucket = _diagnostic_state.gate_counts.setdefault(asset_key, Counter())
    bucket[gate_key] += 1
    if reason:
        bucket[f"{gate_key}:{reason[:48]}"] += 1


def _maybe_log_heatmap(asset: str, cycle_no: int, signals_generated: int) -> None:
    asset_key = str(asset or "").upper().strip() or "UNKNOWN"
    if signals_generated > 0:
        _diagnostic_state.empty_cycles[asset_key] = 0
        return
    empty_cycles = int(_diagnostic_state.empty_cycles.get(asset_key, 0) + 1)
    _diagnostic_state.empty_cycles[asset_key] = empty_cycles
    if empty_cycles < 3:
        return
    gates = _diagnostic_state.gate_counts.get(asset_key) or Counter()
    heatmap = {gate: count for gate, count in gates.most_common(12)}
    logger.warning(
        "[engine][diagnostic_heatmap] asset=%s cycle=%s empty_cycles=%s heatmap=%s",
        asset_key,
        cycle_no,
        empty_cycles,
        heatmap,
    )
    _diagnostic_state.empty_cycles[asset_key] = 0
    _diagnostic_state.gate_counts[asset_key] = Counter()

    # Persist a compact diagnostic record for post-mortem aggregation.
    try:
        diag_dir = pathlib.Path(os.getenv('ENGINE_DIAGNOSTIC_DIR', '.diagnostics'))
        diag_dir.mkdir(parents=True, exist_ok=True)
        out_file = diag_dir / 'heatmap_log.jsonl'
        record = {
            'ts': datetime.utcnow().isoformat(),
            'asset': asset_key,
            'cycle': cycle_no,
            'empty_cycles': empty_cycles,
            'heatmap': heatmap,
        }
        with out_file.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.debug('[engine] failed to persist diagnostic heatmap')


async def _gemini_review_signal(signal: Dict[str, Any], candles: list[dict[str, Any]], news_sentiment: float | None) -> tuple[bool, float | None, str]:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return True, None, "gemini_disabled_no_key"
    if _env_bool("GEMINI_SIGNAL_REVIEW_ENABLED", True) is False:
        return True, None, "gemini_disabled"

    model = (os.getenv("GEMINI_SIGNAL_REVIEW_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-1.5-flash").strip()
    payload = {
        "prompt": "Review this trade. Is this a high-probability institutional move or a retail trap? Rate 1-10. Only approve if > 8.",
        "technical_signal": {
            "asset": signal.get("asset"),
            "timeframe": signal.get("timeframe"),
            "direction": signal.get("direction"),
            "strategy_name": signal.get("strategy_name"),
            "strategy_group": signal.get("strategy_group"),
            "entry": signal.get("entry"),
            "stop_loss": signal.get("stop_loss"),
            "take_profit": signal.get("take_profit"),
            "score": signal.get("score"),
            "confidence": signal.get("confidence"),
            "rr_ratio": signal.get("rr_ratio"),
            "regime": signal.get("regime"),
            "news_sentiment": news_sentiment,
        },
        "recent_ohlcv": candles[-50:],
        "indicators": {
            k: signal.get(k)
            for k in (
                "rsi", "macd_trend", "macd_hist", "trend_ema", "trend_sma",
                "adx_trend", "volume_ratio", "atr_rel", "atr_regime", "relative_volume",
                "mtf_4h_trend", "mtf_1d_trend", "imp_poc", "imp_h4_ema200", "imp_h1_ema50",
            )
        },
    }
    body = json.dumps({
        "contents": [{"parts": [{"text": json.dumps(payload)}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 160},
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    def _do_request() -> tuple[bool, float | None, str]:
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            timeout_s = max(3, int(os.getenv("GEMINI_SIGNAL_REVIEW_TIMEOUT_SEC", "10") or 10))
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            lower = raw.lower()
            score: float | None = None
            for token in ("\"score\":", "score:", "rating:"):
                if token in lower:
                    try:
                        after = lower.split(token, 1)[1]
                        num = ""
                        for ch in after:
                            if ch.isdigit() or ch == ".":
                                num += ch
                            elif num:
                                break
                        if num:
                            score = float(num)
                            break
                    except Exception:
                        pass
            if score is None:
                for digit in range(10, 0, -1):
                    if f"{digit}" in lower:
                        score = float(digit)
                        break
            if score is None:
                return True, None, "gemini_unparsed_allow"
            return (score > 8.0), score, "gemini_ok"
        except urllib.error.HTTPError as exc:
            logger.warning("[engine] gemini review http_error=%s", getattr(exc, "code", "?"))
            return True, None, f"gemini_http_{getattr(exc, 'code', 'error')}"
        except Exception as exc:
            logger.debug("[engine] gemini review failed: %s", exc)
            return True, None, "gemini_failed_allow"

    return await asyncio.to_thread(_do_request)


def _log_decision(decision: str, sig: Dict[str, Any], reason: str | None = None, meta: Dict[str, Any] | None = None) -> None:
    try:
        _meta = dict(meta or {})
        # Persist enough signal context for downstream rejected-signal outcome tracking.
        _meta.setdefault("direction", sig.get("direction"))
        _meta.setdefault("entry", sig.get("entry"))
        _meta.setdefault("stop_loss", sig.get("stop_loss") or sig.get("stop"))
        _meta.setdefault("take_profit", sig.get("take_profit") or sig.get("targets"))
        _meta.setdefault("score", sig.get("score"))
        _meta.setdefault("ml_probability", sig.get("ml_probability"))
        _meta.setdefault("strategy_name", sig.get("strategy_name"))
        _meta.setdefault("strategy_group", sig.get("strategy_group"))
        run_sync(
            persist_decision_log(
                sig.get("signal_id"),
                sig.get("asset"),
                sig.get("timeframe"),
                decision,
                reason=reason,
                meta=_meta,
            )
        )
        # Persist rejection immediately for ML outcome tracking so the
        # adaptive learning pipeline can observe engine-rejected candidates
        # without waiting for decision_log backfill.
        try:
            if decision in ("rejected", "skipped"):
                try:
                    features = dict(_meta or {})
                    from engine.signal_deduplicator import MLRejectionTracker

                    # Best-effort synchronous persist
                    run_sync(
                        _ml_rejection_tracker.persist_rejection(
                            asset=sig.get("asset"),
                            timeframe=sig.get("timeframe"),
                            direction=sig.get("direction") or _meta.get("direction"),
                            entry_price=sig.get("entry") or _meta.get("entry"),
                            stop_loss=sig.get("stop_loss") or _meta.get("stop_loss"),
                            take_profit_levels=sig.get("take_profit") or _meta.get("take_profit"),
                            ml_probability=_meta.get("ml_probability"),
                            rejection_reason=str(reason or _meta.get("reason") or "rejected")[:128],
                            features=features,
                            rejection_type="engine",
                        )
                    )
                    # Also persist a shadow copy to signals table for offline analysis
                    try:
                        shadow_payload = dict(sig or {})
                        shadow_payload["status"] = "shadow_rejected"
                        run_sync(persist_signal(shadow_payload), timeout=10.0)
                    except Exception:
                        logger.debug("[engine] persist shadow signal failed", exc_info=True)
                except Exception:
                    logger.debug("[engine] persist_rejection best-effort failed", exc_info=True)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[engine] Failed to publish analytics event: {e}")
        pass

try:
    from engine.advanced_exit_manager import advanced_exit
except Exception:
    class _ExitStub:
        def calculate_smart_stops(self, *a, **k):
            return {'stop_loss': None, 'tp1': None, 'tp2': None, 'tp3': None}
        def calculate_partial_exit_targets(self, *a, **k):
            return []
        def get_exit_plan_summary(self, *a, **k):
            return 'stub'
    advanced_exit = _ExitStub()

# Global stats tracker for Pulse reporting (fixes "Total Scanned: 0")
from engine.stats_manager import stats

# Misc
logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _primary_take_profit(signal: Dict[str, Any]) -> float | None:
    raw_tp = signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels")
    if isinstance(raw_tp, (list, tuple)):
        for item in raw_tp:
            try:
                if isinstance(item, dict):
                    candidate = item.get("price") or item.get("tp") or item.get("target")
                else:
                    candidate = item
                value = float(candidate)
                if value > 0:
                    return value
            except Exception:
                continue
        return None
    try:
        value = float(raw_tp)
        return value if value > 0 else None
    except Exception:
        return None


def _signal_roi_score(signal: Dict[str, Any]) -> float:
    rr = _safe_float(
        signal.get("roi")
        or signal.get("expected_roi")
        or signal.get("rr_ratio")
        or signal.get("rr_estimate")
        or signal.get("risk_reward"),
        default=0.0,
    )
    if rr > 0:
        return rr

    entry = _safe_float(signal.get("entry") or signal.get("close_price"))
    stop = _safe_float(signal.get("stop_loss") or signal.get("stop"))
    target = _primary_take_profit(signal)
    if entry <= 0 or stop <= 0 or target is None:
        return 0.0
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0:
        return 0.0
    return reward / risk


def _signal_variant_key(signal: Dict[str, Any]) -> tuple[str, str]:
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    direction = str(signal.get("direction") or signal.get("side") or "long").lower().strip()
    return asset, direction


def _asset_class_key(asset: str) -> str:
    sym = str(asset or "").upper().strip()
    if is_crypto(sym):
        return "crypto"
    if is_fx(sym):
        return "fx"
    if is_commodity(sym):
        return "commodity"
    if is_stock(sym):
        return "stock"
    return "other"


def _latest_candle_timestamp(candles: Any) -> datetime | None:
    if not isinstance(candles, list) or not candles:
        return None
    last = candles[-1]
    if not isinstance(last, dict):
        return None
    raw = last.get("timestamp") or last.get("time") or last.get("t") or last.get("datetime")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo else raw
    try:
        if isinstance(raw, (int, float)):
            if float(raw) > 10_000_000_000:
                return datetime.utcfromtimestamp(float(raw) / 1000.0)
            return datetime.utcfromtimestamp(float(raw))
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.replace(tzinfo=None)
    except Exception:
        return None


def _counts_from_active_trades(active_trades: dict[str, dict[str, Any]] | None) -> tuple[dict[str, int], dict[str, int]]:
    asset_counts: dict[str, int] = {}
    class_counts: dict[str, int] = {}
    for payload in (active_trades or {}).values():
        if not isinstance(payload, dict):
            continue
        signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else payload
        asset_name = str((signal or {}).get("asset") or (signal or {}).get("symbol") or "").upper().strip()
        if not asset_name:
            continue
        asset_counts[asset_name] = int(asset_counts.get(asset_name, 0) + 1)
        asset_class = _asset_class_key(asset_name)
        class_counts[asset_class] = int(class_counts.get(asset_class, 0) + 1)
    return asset_counts, class_counts


def _collapse_signal_variants(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only the strongest variant per asset+direction to avoid spammy micro-updates."""
    best_by_key: Dict[tuple[str, str], Dict[str, Any]] = {}
    for signal in signals or []:
        key = _signal_variant_key(signal)
        incumbent = best_by_key.get(key)
        if incumbent is None:
            best_by_key[key] = signal
            continue

        candidate_rank = (
            _signal_roi_score(signal),
            _safe_float(signal.get("score")),
            _safe_float(signal.get("ml_probability")),
        )
        incumbent_rank = (
            _signal_roi_score(incumbent),
            _safe_float(incumbent.get("score")),
            _safe_float(incumbent.get("ml_probability")),
        )
        if candidate_rank > incumbent_rank:
            best_by_key[key] = signal

    return list(best_by_key.values())


# Background outage alert job
def start_outage_alert_job():
    def _job():
        import requests as _requests
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        while True:
            try:
                unhealthy = []
                try:
                    from data.fetcher import get_unhealthy_providers
                    unhealthy = get_unhealthy_providers()
                except Exception:
                    unhealthy = []
                if unhealthy and bot_token:
                    from data.fetcher import should_alert_provider_outage
                    for name, mins in unhealthy:
                        if not should_alert_provider_outage(name, mins):
                            continue
                        msg = f"🚨 Provider outage: {name} has been down for {mins:.1f} minutes."
                        for admin_id in (OWNER_IDS or []):
                            try:
                                _requests.post(
                                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                    json={"chat_id": admin_id, "text": msg},
                                    timeout=10,
                                )
                            except Exception:
                                logger.exception("Failed to send outage message")
                time.sleep(120)
            except Exception:
                logger.exception("outage alert job failed")
                time.sleep(120)

    t = threading.Thread(target=_job, daemon=True)
    t.start()


def _rebuild_stale_signal(sig: Dict[str, Any], live_price: float) -> Dict[str, Any] | None:
    """Return a refreshed copy of *sig* rebased onto *live_price*.

    Keeps the original direction, strategy vote, score, ATR, and regime.
    Recomputes entry/SL/TP so the signal is immediately valid at the current
    market price.

    SL distance priority:
      1. ATR-based (2 × ATR) — same multiplier the engine used originally.
      2. Preserve original relative %-distance if ATR is unavailable.
    TP is set at SL_distance × DEFAULT_RR (default 2.0).

    Returns None when a safe SL/TP cannot be computed.
    """
    try:
        if not live_price or live_price <= 0:
            return None

        direction = str(sig.get('direction') or 'long').lower()
        atr_val   = float(sig.get('atr') or 0)
        orig_entry = float(sig.get('entry') or 0)
        orig_sl    = float(sig.get('stop_loss') or sig.get('stop') or 0)
        rr         = float(os.getenv('DEFAULT_RR', '2.0'))

        # Determine SL distance
        if atr_val > 0:
            sl_dist = 2.0 * atr_val
        elif orig_entry > 0 and orig_sl > 0:
            sl_dist = abs(orig_entry - orig_sl)   # preserve relative %
        else:
            return None  # cannot compute a sensible SL

        if direction == 'long':
            new_sl = live_price - sl_dist
            new_tp = live_price + sl_dist * rr
        else:
            new_sl = live_price + sl_dist
            new_tp = live_price - sl_dist * rr

        if new_sl <= 0 or new_tp <= 0:
            return None

        now = datetime.utcnow()
        refreshed = dict(sig)               # shallow copy — keeps score, votes, etc.
        refreshed.pop('signal_id', None)    # DB assigns a fresh UUID
        refreshed['entry']                  = live_price
        refreshed['stop_loss']              = new_sl
        refreshed['take_profit']            = new_tp
        refreshed['created_at']             = now
        refreshed['expires_at']             = now + _timedelta(minutes=30)
        refreshed['refreshed_from']         = str(sig.get('signal_id') or '')
        refreshed['price_updated']          = True
        refreshed['entry_price_refreshed']  = True
        return refreshed
    except Exception as _e:
        logger.debug(f"[engine] _rebuild_stale_signal failed: {_e}")
        return None


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    raw = raw.strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _short_err(e: Exception, limit: int = 180) -> str:
    try:
        s = f"{type(e).__name__}: {e}"
    except Exception:
        s = "Exception"
    s = (s or "").replace("\n", " ").replace("\r", " ").strip()
    if len(s) > int(limit):
        return s[: int(limit) - 3] + "..."
    return s


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        xs = str(x or "").strip()
        if not xs or xs in seen:
            continue
        seen.add(xs)
        out.append(xs)
    return out


def _normalize_asset_symbol(symbol: str) -> str:
    s = str(symbol or "").upper().strip()
    if s == "MATICUSDT":
        return "POLUSDT"
    return s


def _rotate_slice(items: List[str], start: int, size: int) -> List[str]:
    if size <= 0:
        return []
    if len(items) <= size:
        return list(items)
    n = len(items)
    s = int(start) % n
    e = s + int(size)
    if e <= n:
        return items[s:e]
    return items[s:] + items[: (e - n)]


async def _fetch_market_data_for_assets(asset_to_timeframes: Dict[str, List[str]]) -> Dict[str, Dict]:
    concurrency = max(1, _env_int("MARKET_CACHE_FETCH_CONCURRENCY", 8))
    per_asset_timeout_default = 120.0 if is_binance_blocked() else 45.0
    per_asset_timeout = float(_env_float("MARKET_FETCH_TIMEOUT_SECONDS", per_asset_timeout_default))
    sem = asyncio.Semaphore(concurrency)

    async def _one(asset: str, tfs: List[str]):
        async with sem:
            try:
                started = time.time()
                data = await fetch_market_data_cached(asset, tfs)
                elapsed = time.time() - started
                if elapsed > max(5.0, per_asset_timeout):
                    logger.warning(
                        "[engine] candle_fetch asset=%s status=slow elapsed=%.2fs",
                        asset,
                        elapsed,
                    )
                if not data or not any(data.values()):
                    logger.warning("[WARN] All providers failed for %s, skipping...", asset)
                    return asset, {}
                # Ensure indicators are present per timeframe
                for tf, tf_data in (data or {}).items():
                    try:
                        if not tf_data.get('indicators'):
                            tf_candles = tf_data.get('candles', [])
                            tf_data['indicators'] = calculate_indicators(tf_candles)
                    except Exception:
                        logger.exception("indicator calc failed")
                return asset, (data or {})
            except Exception:
                logger.exception(f"[engine] candle_fetch failed for {asset}")
                return asset, {}

    tasks = [_one(a, tfs) for a, tfs in (asset_to_timeframes or {}).items()]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return {asset: data for asset, data in results}


# Minimal helper: safe await-or-call for maybe-async functions
async def _maybe_await(func, *a, **k):
    try:
        res = func(*a, **k)
        if asyncio.iscoroutine(res):
            return await res
        return res
    except TypeError:
        # Some callables might be awaiting incompatible; try calling synchronously
        return func(*a, **k)


# Engine-level pre-storage score gate.
# Must be <= the lowest tier delivery gate (PREMIUM = 70) so every stored
# signal can reach at least one tier.  Signals scored 65-69 waste cooldown
# slots and DB space while being unreachable by any tier; raising this to 70
# prevents that.  Set PREMIUM_SCORE_THRESHOLD in env to override.
# LOWERED from 55 to 48 to allow more signals through (fixes "Zero Signal" issue)
# Based on log analysis and drift threshold adjustment
DEFAULT_MIN_SCORE_THRESHOLD = _env_float("PREMIUM_SCORE_THRESHOLD", 48)
_runtime_min_score_threshold = float(DEFAULT_MIN_SCORE_THRESHOLD)
_runtime_confluence_min = _env_float("CONFLUENCE_GATE_MIN", 0.0)


def _refresh_runtime_thresholds(force: bool = False) -> None:
    """Refresh runtime thresholds from adaptive optimizer with env fallback."""
    global _last_threshold_refresh, _runtime_min_score_threshold, _runtime_confluence_min
    now_dt = datetime.utcnow()
    if not force and _last_threshold_refresh is not None:
        elapsed_h = (now_dt - _last_threshold_refresh).total_seconds() / 3600.0
        if elapsed_h < float(_threshold_refresh_interval_hours):
            return
    try:
        cfg = None
        refresh_fn = globals().get("refresh_thresholds")
        if callable(refresh_fn):
            _run_sync_sig = inspect.signature(run_sync)
            if "timeout" in _run_sync_sig.parameters:
                cfg = run_sync(refresh_fn(force=force), timeout=20.0)
            else:
                cfg = run_sync(refresh_fn(force=force))

        if cfg is not None:
            # Allow an explicit env-var override to take precedence over DB-driven thresholds.
            # Set PREMIUM_SCORE_THRESHOLD_FORCE=1 to prevent DB from overwriting runtime env values.
            _force_env_override = bool((os.getenv("PREMIUM_SCORE_THRESHOLD_FORCE") or "").strip())

            if not _force_env_override:
                previous_min_score = _runtime_min_score_threshold
                previous_confluence = _runtime_confluence_min
                _runtime_min_score_threshold = float(
                    getattr(cfg, "min_score_threshold", _runtime_min_score_threshold) or _runtime_min_score_threshold
                )
                _runtime_confluence_min = float(
                    getattr(cfg, "confluence_min", _runtime_confluence_min) or _runtime_confluence_min
                )
                os.environ["PREMIUM_SCORE_THRESHOLD"] = str(_runtime_min_score_threshold)
                os.environ["CONFLUENCE_GATE_MIN"] = str(_runtime_confluence_min)
                os.environ["ML_PROB_THRESHOLD"] = str(
                    float(getattr(cfg, "ml_prob_threshold", _env_float("ML_PROB_THRESHOLD", 0.55)) or 0.55)
                )
                logger.info(
                    "[engine] thresholds refreshed | min_score=%.1f->%.1f confluence=%.1f->%.1f ml_prob=%.3f",
                    previous_min_score,
                    _runtime_min_score_threshold,
                    previous_confluence,
                    _runtime_confluence_min,
                    float(getattr(cfg, "ml_prob_threshold", _env_float("ML_PROB_THRESHOLD", 0.55)) or 0.55),
                )
            else:
                logger.info("[engine] PREMIUM_SCORE_THRESHOLD_FORCE set; preserving env vars over DB thresholds")
        else:
            _runtime_min_score_threshold = _env_float("PREMIUM_SCORE_THRESHOLD", _runtime_min_score_threshold)
            _runtime_confluence_min = _env_float("CONFLUENCE_GATE_MIN", _runtime_confluence_min)
            logger.debug(
                "[engine] threshold refresh used env fallback | min_score=%.1f confluence=%.1f ml_prob=%.3f",
                _runtime_min_score_threshold,
                _runtime_confluence_min,
                _env_float("ML_PROB_THRESHOLD", 0.55),
            )

        _last_threshold_refresh = now_dt
    except Exception as e:
        logger.debug(f"[engine] runtime threshold refresh failed: {e}")


def _current_min_score_threshold() -> float:
    return _env_float("PREMIUM_SCORE_THRESHOLD", _runtime_min_score_threshold)


def _current_ml_prob_threshold() -> float:
    try:
        if _threshold_optimizer is not None and hasattr(_threshold_optimizer, "get_threshold"):
            return float(_threshold_optimizer.get_threshold() or _env_float("ML_PROB_THRESHOLD", 0.55))
    except Exception:
        pass
    return _env_float("ML_PROB_THRESHOLD", 0.55)


def load_tradable_assets() -> List[str]:
    raw = (os.getenv("TRADABLE_ASSETS") or "").strip()
    if not raw:
        # If get_all_tradable_assets exists, use it as default
        try:
            all_assets = get_all_tradable_assets() or {}
            if isinstance(all_assets, dict):
                merged: list[str] = []
                for _, items in all_assets.items():
                    for a in (items or []):
                        merged.append(str(a))
                return [a for a in merged if a]
            return [str(a) for a in list(all_assets) if a]
        except Exception:
            return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def main_loop(DRY_RUN: bool = False):
    start_outage_alert_job()

    # Outcome tracker ownership is worker-only in monolith runtime.
    logger.info("[engine] RealtimeOutcomeTracker disabled (owned by worker loop)")

    account_equity = 10000.0
    risk_manager = RiskManager(account_equity)
    correlation_manager = CorrelationManager()
    exit_manager = ExitManager()
    partial_exit_tracker = PartialExitTracker()
    signal_filter = SignalFilter()

    mtf_analyzer = MultiTimeframeAnalyzer()
    signal_context = SignalContext()
    cooldown_manager = SignalCooldownManager()
    bias_manager = OneBiasPerTimeframe()
    advanced_filters = SmartFilterSuite()
    tier_notifier = TierNotificationManager()

    fx_enabled = _env_bool('FX_ENABLED', True)
    stocks_enabled = _env_bool('STOCKS_ENABLED', True)
    _running_on_railway = bool((os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
    _tf_default = '1h,4h,24h'
    def _norm_tf(tf: str) -> str:
        _tf = str(tf or "").strip().lower()
        if _tf == "24h":
            return "1d"
        return _tf
    _allowed_tfs = {"1m", "5m", "15m", "1h", "4h", "1d"}
    def _normalize_tf_list(raw: str | None) -> list[str]:
        out: list[str] = []
        for tf in (raw or "").split(','):
            norm = _norm_tf(tf)
            if norm:
                out.append(norm)
        return out


    async def _fetch_macro_snapshot() -> Dict[str, float]:
        """Fetch macro context once per cycle for all assets."""
        global _last_macro_snapshot_at, _macro_snapshot_cache
        now_dt = datetime.utcnow()
        if _macro_snapshot_cache is not None and _last_macro_snapshot_at is not None:
            elapsed = (now_dt - _last_macro_snapshot_at).total_seconds()
            if elapsed < float(_macro_snapshot_refresh_seconds):
                return dict(_macro_snapshot_cache)

        macro: Dict[str, float] = {}
        try:
            from services.economic_calendar import get_macro_news_context
            news_ctx = await get_macro_news_context()
            macro.update({
                "minutes_since_high_impact_news": float(news_ctx.get("minutes_since_high_impact_news") or 0.0) if news_ctx.get("minutes_since_high_impact_news") is not None else 0.0,
                "minutes_until_high_impact_news": float(news_ctx.get("minutes_until_high_impact_news") or 0.0) if news_ctx.get("minutes_until_high_impact_news") is not None else 0.0,
                "news_event_impact_score": float(news_ctx.get("news_event_impact_score") or 0.0),
            })
        except Exception:
            pass

        async def _macro_tf(asset: str, timeframe: str = "1d") -> Dict[str, Any]:
            try:
                data = await fetch_market_data_cached(asset, [timeframe])
                tf_data = (data or {}).get(timeframe) or {}
                candles = tf_data.get("candles") or []
                closes = [float(c.get("close") or 0.0) for c in candles if isinstance(c, dict)]
                if len(closes) < 2:
                    return {}
                first = closes[0]
                last = closes[-1]
                trend = ((last - first) / first) if first else 0.0
                return {"trend": float(trend), "last": float(last), "source": tf_data.get("source") or ""}
            except Exception:
                return {}

        dxy = await _macro_tf("DXY", "1d")
        vix = await _macro_tf("VIX", "1d")
        us10 = await _macro_tf("US10Y", "1d")
        us02 = await _macro_tf("US02Y", "1d")

        macro.update({
            "dxy_trend": float(dxy.get("trend") or 0.0),
            "vix_trend": float(vix.get("trend") or 0.0),
            "us10y_trend": float(us10.get("trend") or 0.0),
            "yield_spread": float((float(us10.get("last") or 0.0) - float(us02.get("last") or 0.0)) if us10.get("last") is not None and us02.get("last") is not None else 0.0),
            "btc_corr": 0.0,
            "spx_trend": 0.0,
        })
        _macro_snapshot_cache = dict(macro)
        _last_macro_snapshot_at = now_dt
        return macro
    def _resolve_timeframes(env_key: str) -> list[str]:
        raw = os.getenv(env_key, _tf_default)
        parsed = _normalize_tf_list(raw)
        filtered = [tf for tf in parsed if tf in _allowed_tfs]
        if filtered:
            return filtered
        if parsed:
            logger.warning("[engine] %s=%s filtered out by allowlist; falling back to %s", env_key, raw, _tf_default)
            return [tf for tf in _normalize_tf_list(_tf_default) if tf in _allowed_tfs]
    crypto_timeframes = _resolve_timeframes('CRYPTO_TIMEFRAMES')
    fx_timeframes = _resolve_timeframes('FX_TIMEFRAMES')
    stock_timeframes = _resolve_timeframes('STOCK_TIMEFRAMES')
    commodity_timeframes = _resolve_timeframes('COMMODITY_TIMEFRAMES')

    cycle_no = 0

        # Round-robin queue — covers every open asset exactly once per round
        # before any asset is repeated.  Persists across cycles; new assets
        # discovered mid-run are appended to the current round's tail.
    from engine.cycle_queue import AssetCycleQueue
    _cycle_queue = AssetCycleQueue()

        # Per-class rotating cursor used to guarantee at least one analyzed asset
        # from each open class on every cycle.
    _class_cursor = {
            "crypto": 0,
            "fx": 0,
            "stock": 0,
            "commodity": 0,
        }

    # Keep the main loop simple and robust
    last_heartbeat = time.time()
        
        # PHASE 1 FIX: Don't reset stats each cycle - they should accumulate!
        # stats.reset() is only called once at startup, not every cycle
        # The Pulse reporter reads cumulative stats across all cycles
        
        # === PHASE 3 FIX: Circuit Breaker Health Check ===
        # Initialize circuit breaker to check market health before starting
    circuit_breaker = MarketCircuitBreaker()
    

    while True:
            cycle_no += 1
            cycle_sleep_seconds = 30
            now = time.time()
        # Heartbeat log every 30 seconds
            if now - last_heartbeat > 30:
                logger.info(f"[engine] heartbeat: cycle={cycle_no} running")
                print(f"[engine] heartbeat: cycle={cycle_no} running", flush=True)
                last_heartbeat = now

            # === PHASE 3 FIX: Circuit Breaker Health Check ===
            # Check market health before starting the cycle - if flash crash detected, skip this cycle
            try:
                import asyncio
                is_healthy = asyncio.get_event_loop().run_until_complete(circuit_breaker.check_market_health())
                logger.info(f"[engine] Market Health Check: is_healthy={is_healthy}")
                if not is_healthy:
                    logger.warning("[engine] Circuit breaker activated - skipping cycle due to market flash crash")
                    time.sleep(max(5, cycle_sleep_seconds))
                    continue
            except Exception as cb_err:
                logger.debug(f"[engine] Circuit breaker check failed (allow continue): {cb_err}")

            # Pull dynamic thresholds from adaptive ML/Gemini optimizer on schedule.
            _refresh_runtime_thresholds(force=(cycle_no == 1))

            # Acquire assets list — ALWAYS merge manually-configured (saved) assets
            # with DB-managed assets and discovered trending pairs so nothing pinned is missed.
            _saved_assets = [
                _normalize_asset_symbol(x.strip())
                for x in (os.getenv("TRADABLE_ASSETS") or "").split(",")
                if x.strip()
            ]
            _managed_assets: List[str] = []
            try:
                from db.session import get_session
                from db.pg_features import get_active_managed_assets
                from utils.async_runner import run_sync as _run_sync
                async def _fetch_managed():
                    async with get_session() as _session:
                        return await get_active_managed_assets(_session)
                _managed_assets = [
                    _normalize_asset_symbol(s) for s in (list(_run_sync(_fetch_managed()) or []))
                ]
            except Exception:
                pass
            _discovered_assets: List[str] = []
            try:
                _discovered_assets = [
                    _normalize_asset_symbol(s) for s in (list(get_all_trending_pairs() or []))
                ]
            except Exception:
                pass
            assets = _dedupe_preserve_order(_managed_assets + _saved_assets + _discovered_assets)
            if not assets:
                logger.info(f"[engine] cycle={cycle_no} skipped=no_assets")
                time.sleep(max(5, cycle_sleep_seconds))
                continue

            # Filter by market closed
            open_assets = []
            closed_notes = []
            for a in assets:
                try:
                    reason = market_closed_reason(a)
                    if reason:
                        closed_notes.append((a, reason))
                    else:
                        open_assets.append(a)
                except Exception:
                    open_assets.append(a)
            if closed_notes and _env_bool("ENGINE_CYCLE_LOG", True):
                msg = ", ".join([f"{p}:{r}" for p, r in closed_notes])
                logger.info(f"[engine] cycle={cycle_no} market_closed skip={msg}")

            # Partition
            crypto_assets = [a for a in open_assets if is_crypto(a)]
            fx_assets = [a for a in open_assets if is_fx(a)]
            stock_assets = [a for a in open_assets if is_stock(a)]
            commodity_assets = [a for a in open_assets if is_commodity(a)]
            fx_enabled = _env_bool('FX_ENABLED', True)
            stocks_enabled = _env_bool('STOCKS_ENABLED', True)
            if not fx_enabled:
                fx_assets = []
            if not stocks_enabled:
                stock_assets = []

            # ── Round-robin queue: cover every open asset once per round ──────────
            # Interleave asset classes so each batch has natural diversity
            # (e.g. batch of 10 gets ~3 crypto, 2 FX, 3 stocks, 2 commodities).
            _all_open: list[str] = []
            _cat_iters = [
                iter(c)
                for c in [crypto_assets, fx_assets, stock_assets, commodity_assets]
                if c
            ]
            while _cat_iters:
                _next_iters = []
                for _it in _cat_iters:
                    try:
                        _a = next(_it)
                        if _a not in _all_open:
                            _all_open.append(_a)
                        _next_iters.append(_it)
                    except StopIteration:
                        pass
                _cat_iters = _next_iters

            _universe_cap = max(1, _env_int("ENGINE_UNIVERSE_CAP", 20))
            _all_open = _all_open[:_universe_cap]
            # Feed the queue; refresh_universe only rebuilds once per hour
            # (CYCLE_UNIVERSE_REFRESH_INTERVAL env var) unless this is wakeup #1.
            _cycle_queue.refresh_universe(_all_open, force=(cycle_no == 1))

            # Pop this batch from the queue.
            _running_on_railway = bool((os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
            _default_cycle_batch = 20 if _running_on_railway else 20
            CYCLE_BATCH_SIZE = _env_int("CYCLE_BATCH_SIZE", _default_cycle_batch)
            CYCLE_BATCH_SIZE = min(CYCLE_BATCH_SIZE, _universe_cap)
            assets = _cycle_queue.pop_batch(CYCLE_BATCH_SIZE)

            # Guarantee class coverage: at least one asset per OPEN class each cycle.
            # If a class market is closed (no open assets in that class), it is skipped.
            def _asset_class(_a: str) -> str:
                if is_crypto(_a):
                    return "crypto"
                if is_fx(_a):
                    return "fx"
                if is_commodity(_a):
                    return "commodity"
                return "stock"

            _open_by_class = {
                "crypto": list(crypto_assets),
                "fx": list(fx_assets),
                "stock": list(stock_assets),
                "commodity": list(commodity_assets),
            }
            _required_classes = [k for k, v in _open_by_class.items() if v]

            if _required_classes and CYCLE_BATCH_SIZE < len(_required_classes):
                logger.warning(
                    "[engine] CYCLE_BATCH_SIZE=%d smaller than open classes=%d; cannot guarantee full class coverage",
                    CYCLE_BATCH_SIZE,
                    len(_required_classes),
                )

        # Count selected assets by class.
            _selected_counts: dict[str, int] = {k: 0 for k in _open_by_class.keys()}
            for _a in assets:
                _selected_counts[_asset_class(_a)] = _selected_counts.get(_asset_class(_a), 0) + 1

            # Inject one rotating anchor per missing open class.
            _injected: list[str] = []
            for _cls in _required_classes:
                if _selected_counts.get(_cls, 0) > 0:
                    continue

                _pool = _open_by_class.get(_cls) or []
                _cand = None
                for _ in range(len(_pool)):
                    _idx = _class_cursor.get(_cls, 0) % len(_pool)
                    _class_cursor[_cls] = _class_cursor.get(_cls, 0) + 1
                    _try = _pool[_idx]
                    if _try not in assets:
                        _cand = _try
                        break

                if _cand is None:
                    continue

                if len(assets) < CYCLE_BATCH_SIZE:
                    assets.append(_cand)
                else:
                    # Replace from an overrepresented class first.
                    _replace_idx = None
                    for i in range(len(assets) - 1, -1, -1):
                        _existing_cls = _asset_class(assets[i])
                        if _selected_counts.get(_existing_cls, 0) > 1:
                            _replace_idx = i
                            _selected_counts[_existing_cls] -= 1
                            break
                    if _replace_idx is not None:
                        assets[_replace_idx] = _cand
                    else:
                        # No safe replacement available this cycle.
                        continue

                _selected_counts[_cls] = _selected_counts.get(_cls, 0) + 1
                _injected.append(_cand)

            # Prevent injected anchors from reappearing later this round.
            if _injected:
                try:
                    _cycle_queue.remove_from_queue(_injected)
                except Exception:
                    pass

            cycle_assets = len(assets)

            if not assets:
                logger.info(f"[engine] cycle={cycle_no} skipped=empty_queue")
                time.sleep(max(5, cycle_sleep_seconds))
                continue

            if _env_bool("ENGINE_CYCLE_LOG", True):
                logger.info(
                    f"[engine] {_cycle_queue.round_progress} "
                    f"batch={cycle_assets} wakeup={cycle_no} classes={_selected_counts}"
                )

            # Build timeframes map
            asset_to_tfs: Dict[str, List[str]] = {}
            for asset in assets:
                if is_crypto(asset):
                    tfs = crypto_timeframes
                elif is_fx(asset):
                    tfs = fx_timeframes
                elif is_stock(asset):
                    tfs = stock_timeframes
                elif is_commodity(asset):
                    tfs = commodity_timeframes
                else:
                    tfs = stock_timeframes
                asset_to_tfs[asset] = list(tfs)

            # Dynamic cycle sleep based on smallest timeframe
            _TF_SLEEP_MAP = {"1h": 30, "4h": 30, "1d": 30}
            env_sleep = _env_int("ENGINE_CYCLE_SLEEP_SECONDS", 0)
            if env_sleep > 0:
                cycle_sleep_seconds = env_sleep
            else:
                cycle_sleep_seconds = 30

    # Graceful degradation slice
            degraded_assets = set()
            asset_to_tfs_degraded = {a: (tfs[:1] if a in degraded_assets else tfs) for a, tfs in asset_to_tfs.items()}

            # Fetch market data (async)
            try:
                from utils.async_runner import run_sync
                fetch_timeout_s = max(30.0, float(_env_float("ENGINE_MARKET_FETCH_TIMEOUT_SECONDS", 180.0) or 180.0))
                all_market_data = run_sync(
                    _fetch_market_data_for_assets(asset_to_tfs_degraded),
                    timeout=fetch_timeout_s,
                )
            except Exception:
                logger.exception("Market data fetch failed or timed out")
                all_market_data = {}

            try:
                macro_snapshot = run_sync(_fetch_macro_snapshot(), timeout=30.0)
            except Exception:
                macro_snapshot = {}

            scored_signals_all: List[Dict] = []
            max_candidate_score = None
            # Fix 2: cycle-level set prevents duplicate asset+timeframe signals in the same batch
            _cycle_cooldown: set = set()
            pipeline_stats = {
                "strategy_signals": 0,
            "normalized": 0,
            "consensus": 0,
            "selected": 0,
            "unique": 0,
            "strict_candidates": 0,
            "risk_passed": 0,
            "final_signals": 0,
            "stored": 0,
            "skipped_open_limit_asset": 0,
            "skipped_open_limit_class": 0,
            "skipped_cycle_cooldown": 0,
            "skipped_db_cooldown": 0,
            "skipped_confluence_block": 0,
            "skipped_portfolio_exposure": 0,
            "store_failed": 0,
        }

            open_limit_per_asset = max(1, _env_int("OPEN_SIGNALS_MAX_PER_ASSET", 20))
            open_limit_per_class = max(1, _env_int("OPEN_SIGNALS_MAX_PER_CLASS", 20))
            open_counts_by_asset: dict[str, int] = {}
            open_counts_by_class: dict[str, int] = {}
            try:
                from db.session import get_session as _get_s_open
                from db.models import Signal as _OpenSig
                from sqlalchemy import select as _sel_open, func as _func_open

                async def _load_open_signal_counts() -> list[tuple[str, int]]:
                    async with _get_s_open() as _os:
                        rows = (await _os.execute(
                            _sel_open(_OpenSig.asset, _func_open.count(_OpenSig.signal_id))
                            .where(
                                _OpenSig.expired.is_(False),
                                _OpenSig.archived.is_(False),
                            )
                            .group_by(_OpenSig.asset)
                        )).fetchall()
                        return [(str(r[0] or "").upper().strip(), int(r[1] or 0)) for r in rows]

                _open_rows = run_sync(_load_open_signal_counts(), timeout=20.0)
                for _asset_name, _count in _open_rows:
                    if not _asset_name:
                        continue
                    open_counts_by_asset[_asset_name] = int(_count)
                    _cls = _asset_class_key(_asset_name)
                    open_counts_by_class[_cls] = int(open_counts_by_class.get(_cls, 0) + int(_count))
            except Exception as _open_count_err:
                logger.debug(f"[engine] open signal count preload failed: {_open_count_err}")

            try:
                if state.has_redis_sync():
                    active_trades = state.get_active_trades_sync() or {}
                    if active_trades:
                        open_counts_by_asset, open_counts_by_class = _counts_from_active_trades(active_trades)
                        logger.info(
                            "[engine] open counts reconciled from Redis active trades: assets=%s classes=%s",
                            len(open_counts_by_asset),
                            len(open_counts_by_class),
                        )
                    elif open_counts_by_asset or open_counts_by_class:
                        async def _expire_open_signals() -> int:
                            from db.session import get_session as _get_s_expire
                            from db.models import Signal as _SignalExpire
                            from sqlalchemy import update as _update_expire

                            async with _get_s_expire() as _session:
                                result = await _session.execute(
                                    _update_expire(_SignalExpire)
                                    .where(
                                        _SignalExpire.expired.is_(False),
                                        _SignalExpire.archived.is_(False),
                                    )
                                    .values(expired=True)
                                )
                                await _session.commit()
                                return int(getattr(result, "rowcount", 0) or 0)

                        expired_rows = run_sync(_expire_open_signals(), timeout=20.0)
                        logger.warning(
                            "[engine] redis active trades empty; expired %s stale DB open signals before open-limit gate",
                            expired_rows,
                        )
                        open_counts_by_asset.clear()
                        open_counts_by_class.clear()
            except Exception as _redis_reconcile_err:
                logger.debug(f"[engine] redis/db open-signal reconciliation failed: {_redis_reconcile_err}")

    # Per-asset pipeline
            for asset in assets:
                # HARD_BLACKLIST check: skip zombie stablecoins
                _norm_asset = _normalize_asset_symbol(asset)
                if _norm_asset in HARD_BLACKLIST:
                    logger.warning(f"[engine] HARDBLACKLIST: skipping zombie stablecoin {asset}")
                    _record_gate_failure(asset, "hard_blacklist", "zombie_stablecoin")
                    continue
                    
                logger.info(f"[engine] pipeline: starting asset={asset}")
                try:
                    market_data = all_market_data.get(asset, {})
                    if isinstance(market_data, dict):
                        market_data["_macro"] = dict(macro_snapshot or {})

                    # Basic safety: ensure we have at least one TF with candles
                    has_candles = any((tf_data.get('candles') for tf_data in market_data.values())) if isinstance(market_data, dict) else False
                    if not has_candles:
                        logger.warning(f"[engine] No market data for asset={asset}")
                        _record_gate_failure(asset, "market_data", "no_candles")
                        _maybe_log_heatmap(asset, cycle_no, 0)
                        continue

                    # Check data age for each timeframe
                    # Data is considered stale if older than 2x the timeframe interval
                    # (e.g., 1h candles stale after 2 hours, allows for provider delays)
                    from core.tier_constants import CANDLE_STALENESS_MULTIPLIER
                    _TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}
                    stale_data = False
                    for tf, tf_data in market_data.items():
                        if isinstance(tf_data, dict):
                            data_age = tf_data.get("data_age_seconds")
                            tf_interval = _TF_SECONDS.get(tf, 3600)
                            max_age = tf_interval * CANDLE_STALENESS_MULTIPLIER
                            source_name = _provider_source_name(tf_data)
                            if data_age is not None and data_age > 60 and source_name in {"yfinance", "tradingview", "tradingview_connector", "tradingview_legacy"}:
                                logger.warning(
                                    "[engine] latency_warning asset=%s tf=%s source=%s age=%ss threshold=60s action=warn_only",
                                    asset,
                                    tf,
                                    source_name,
                                    data_age,
                                )
                                tf_data["latency_warning"] = True
                            elif data_age is not None and data_age > max_age:
                                logger.warning(f"[engine] Stale data for {asset} {tf}: age={data_age}s > max={max_age}s, skipping")
                                _record_gate_failure(asset, "stale_data", f"{tf}:{data_age:.0f}s>{max_age:.0f}s")
                                _maybe_log_heatmap(asset, cycle_no, 0)
                                stale_data = True
                                break
                    if stale_data:
                        continue

                    # Economic calendar no-trade-zone gate (60-min buffer around high-impact events)
                    try:
                        if _is_no_trade_zone_sync(asset, buffer_minutes=60):
                            logger.info(f"[engine] no_trade_zone gate: skipping asset={asset} (high-impact event within 60 min)")
                            _record_gate_failure(asset, "macro", "no_trade_zone_60m")
                            _maybe_log_heatmap(asset, cycle_no, 0)
                            continue
                    except Exception:
                        pass

    # Detect regime
                    try:
                        regime = detect_market_regime(market_data)
                    except Exception:
                        regime = None

                    # === PHASE 1 FIX: Increment stats.scanned for each asset analyzed ===
                    stats.scanned += 1
                    
                    # === PHASE 1 FIX: Check regime and track vetoes ===
                    if regime is None or regime == "neutral" or regime == "unknown":
                        stats.vetoed_regime += 1
                        
                    # News sentiment (non-critical)
                    try:
                        news_sent = get_news_sentiment(asset)
                        market_data['news_sentiment'] = news_sent
                    except Exception:
                        market_data['news_sentiment'] = None

    # Run strategies -> returns list of signals (each is a dict)
                    try:
                        strategy_signals = run_all_strategies(asset, market_data, regime) or []
                        if not strategy_signals:
                            # Debug: log why no signals (indicator values that failed)
                            ind = (market_data.get(list(market_data.keys())[0]) or {}).get('indicators', {}) if market_data else {}
                            logger.debug(
                                f"[engine] No strategy signals for {asset}. "
                                f"regime={regime}, ema_fast={ind.get('ema_fast')}, ema_slow={ind.get('ema_slow')}, "
                                f"rsi={ind.get('rsi')}, adx={ind.get('adx')}, "
                                f"supertrend={ind.get('supertrend_signal')}, "
                                f"close={ind.get('close_price')}, sma_20={ind.get('sma_20')}"
                            )
                    except Exception:
                        logger.exception(f"Strategies failed for {asset}")
                        strategy_signals = []

                    pipeline_stats["strategy_signals"] += len(strategy_signals)
                    if not strategy_signals:
                        # DEBUG: Log what's happening - regime, available TFs, indicators keys
                        _tf_list = list(market_data.keys()) if market_data else []
                        _ind_keys = list(market_data.get(list(market_data.keys())[0], {}).get('indicators', {}).keys()) if market_data else []
                        logger.info(f"[engine] No strategy signals for {asset} regime={regime} tfs={_tf_list} ind_sample={_ind_keys[:5]}")
                        _record_gate_failure(asset, "strategy_generation", "no_strategy_signals")
                        _maybe_log_heatmap(asset, cycle_no, 0)
                        continue

                    # DEBUG: Log strategy signal details
                    logger.info(f"[engine] strategy_signals generated for {asset}: count={len(strategy_signals)}")
                    for _si, _sig in enumerate(strategy_signals[:3]):  # Log first 3
                        logger.info(f"[engine]   sig[{_si}]: {_sig.get('strategy_name')} dir={_sig.get('direction')} conf={_sig.get('confidence')}")

                    # Normalize & dedupe (using SignalController if available)
                    try:
                        from engine.signal_controller import SignalController
                        controller = SignalController()
                        normalized = controller.normalize_signals(strategy_signals)
                    except Exception:
                        normalized = strategy_signals
                    pipeline_stats["normalized"] += len(normalized)

                    # Consensus filter - NO FALLBACK IN PROD
                    try:
                        consensus_signals = apply_consensus_filter(normalized)
                        _block_on_empty_consensus = _env_bool(
                            "CONSENSUS_BLOCK_ON_EMPTY",
                            _env_bool("PROD_MODE", False),
                        )
                        if not consensus_signals and _block_on_empty_consensus:
                            logger.warning(f"Consensus empty for {asset} - blocking (PROD policy)")
                            continue  # Skip asset entirely
                    except Exception as e:
                        logger.error(f"Consensus failed for {asset}: {e}")
                        consensus_signals = []
                    pipeline_stats["consensus"] += len(consensus_signals)

                    # Pick best direction per pair/timeframe
                    try:
                        if 'controller' in locals():
                            selected_signals = controller.pick_best_direction_per_pair(consensus_signals)
                        else:
                            selected_signals = consensus_signals
                    except Exception:
                        selected_signals = consensus_signals
                    pipeline_stats["selected"] += len(selected_signals)

                    # Compute fingerprints & unique
                    try:
                        from db.pg_features import compute_signal_fingerprint
                        unique_signals = []
                        seen = set()
                        for sig in selected_signals:
                            try:
                                tf = sig.get('timeframe') or (list(market_data.keys())[0] if market_data else None)
                                tf_data = market_data.get(tf, {}) if tf else {}
                                candles = tf_data.get('candles', []) if isinstance(tf_data, dict) else []
                                if not sig.get('candle_timestamp'):
                                    candle_timestamp = _latest_candle_timestamp(candles)
                                    if candle_timestamp is not None:
                                        sig['candle_timestamp'] = candle_timestamp
                                fp = compute_signal_fingerprint(sig)
                            except Exception:
                                fp = None
                            sig['fingerprint'] = fp
                            if fp and fp in seen:
                                _log_decision("skipped", sig, reason="duplicate_fingerprint", meta={"fingerprint": fp})
                                continue
                            if fp:
                                seen.add(fp)
                            unique_signals.append(sig)
                        selected_signals = unique_signals
                    except Exception as e:
                        logger.debug(f"[engine] Failed to deduplicate signals: {e}")
                        pass
                    pipeline_stats["unique"] += len(selected_signals)

                    # Validate/strict gates
                    strict_candidates = []
                    for sig in selected_signals:
                        try:
                            # Enrich signal with indicator context for confluence scoring
                            tf = sig.get('timeframe') or (list(market_data.keys())[0] if market_data else None)
                            tf_data = market_data.get(tf, {}) if tf else {}
                            ind = tf_data.get('indicators', {}) if isinstance(tf_data, dict) else {}

                            if isinstance(ind, dict):
                                sig.setdefault('trend_ema', ind.get('trend_ema', 0))
                                sig.setdefault('trend_sma', ind.get('trend_sma', 0))
                                sig.setdefault('rsi', ind.get('rsi', 50))
                                sig.setdefault('macd_trend', ind.get('macd_trend', 0))
                                sig.setdefault('volume_ratio', ind.get('volume_ratio', 1.0))
                                sig.setdefault('nearest_support', ind.get('nearest_support', 0))
                                sig.setdefault('nearest_resistance', ind.get('nearest_resistance', 0))
                                sig.setdefault('close_price', ind.get('close_price', sig.get('entry', 0)))
                                sig.setdefault('adx_trend', ind.get('adx_trend', 'weak'))
                                sig.setdefault('regime', ind.get('regime', regime))
                                if sig.get('volatility') is None:
                                    sig['volatility'] = float(ind.get('atr_percent', 0) or ind.get('bollinger', {}).get('width', 0) or 0)
                            # Preserve asset-class open-market context and full-strategy coverage hints.
                            sig['market_open_confirmed'] = True
                            sig['strategy_coverage_count'] = int(len(strategy_signals or []))
                            sig['news_sentiment'] = market_data.get('news_sentiment')
                            sig['asset_class_enc'] = 0.0 if _asset_class(asset) == 'crypto' else 1.0 if _asset_class(asset) == 'fx' else 2.0 if _asset_class(asset) == 'commodity' else 3.0
                            sig['dxy_trend'] = (market_data.get('_macro') or {}).get('dxy_trend', 0.0)
                            sig['vix_trend'] = (market_data.get('_macro') or {}).get('vix_trend', 0.0)
                            sig['us10y_trend'] = (market_data.get('_macro') or {}).get('us10y_trend', 0.0)
                            sig['yield_spread'] = (market_data.get('_macro') or {}).get('yield_spread', 0.0)
                            sig['minutes_since_high_impact_news'] = (market_data.get('_macro') or {}).get('minutes_since_high_impact_news', 0.0)
                            sig['minutes_until_high_impact_news'] = (market_data.get('_macro') or {}).get('minutes_until_high_impact_news', 0.0)
                            sig['news_event_impact_score'] = (market_data.get('_macro') or {}).get('news_event_impact_score', 0.0)

                            # preview score (even if it doesn't pass validation/gates)
                            try:
                                preview_score = float(score_signal(sig)) if score_signal else 0
                                sig['_preview_score'] = preview_score
                                if max_candidate_score is None or preview_score > max_candidate_score:
                                    max_candidate_score = preview_score
                            except Exception as e:
                                logger.debug(f"[engine] Failed to compute preview score: {e}")
                                pass

                            # basic validation (structure)
                            from engine.signal_validator import validate_signal
                            ok, reason = validate_signal(sig)
                            if not ok:
                                sig['rejection_reason'] = f"validation:{reason}"
                                _record_gate_failure(asset, "trend", reason)
                                _log_decision("skipped", sig, reason=sig['rejection_reason'])
                                continue
                            # risk gate
                            account_state = type('AccountState', (), {'drawdown': 0.0})()
                            try:
                                active_trades = state.get_active_trades_sync() or {}
                                active_positions = []
                                for payload in (active_trades or {}).values():
                                    try:
                                        sym = str(payload.get("symbol") or payload.get("asset") or "").upper().strip()
                                        if sym:
                                            active_positions.append(sym)
                                    except Exception:
                                        continue
                                if active_positions:
                                    sig["active_positions"] = list(dict.fromkeys(active_positions))
                            except Exception:
                                pass
                            if not risk_check(sig, account_state):
                                sig['rejection_reason'] = 'risk/volatility'
                                _record_gate_failure(asset, "risk", sig['rejection_reason'])
                                _log_decision("skipped", sig, reason=sig['rejection_reason'])
                                continue
                            # confluence (only enforce if threshold configured or score available)
                            conf = calculate_confluence(sig)
                            if conf is not None:
                                conf_raw = str(os.getenv("CONFLUENCE_GATE_MIN") or "").strip()
                                conf_min = float(conf_raw) if conf_raw else None
                                if conf_min is not None and conf < conf_min:
                                    sig['rejection_reason'] = f'confluence {conf:.1f}%'
                                    _record_gate_failure(asset, "trend", sig['rejection_reason'])
                                    _log_decision("skipped", sig, reason=sig['rejection_reason'], meta={"confluence": conf})
                                    continue
                            # News confirmation gate (all supported classes: FX/crypto/commodities/stocks).
                            # Strong opposing sentiment blocks signal; aligned sentiment gets a light confidence bonus.
                            try:
                                from core.tier_constants import STRONG_SENTIMENT_THRESHOLD
                                _news = float(market_data.get('news_sentiment') or 0.0)
                                _dir = str(sig.get('direction') or '').lower().strip()
                                _thr = float(STRONG_SENTIMENT_THRESHOLD or 2)
                                _oppose = (_news >= _thr and _dir == 'short') or (_news <= -_thr and _dir == 'long')
                                if _oppose:
                                    sig['rejection_reason'] = f"news_conflict sentiment={_news:.2f}"
                                    _record_gate_failure(asset, "news", sig['rejection_reason'])
                                    _log_decision("skipped", sig, reason=sig['rejection_reason'], meta={"news_sentiment": _news})
                                    continue
                                if ((_news >= _thr and _dir == 'long') or (_news <= -_thr and _dir == 'short')):
                                    try:
                                        sig['confidence'] = min(1.0, float(sig.get('confidence') or 0.0) + 0.05)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            strict_candidates.append(sig)
                        except Exception:
                            logger.exception("candidate gating failed")

                    pipeline_stats["strict_candidates"] += len(strict_candidates)
                    if not strict_candidates:
                        continue

    # ML advisory (non-blocking)
                    try:
                        from ml.inference import MLFilter
                        from ml.features import extract_features
                        ml_filter = MLFilter()
                    except Exception:
                        ml_filter = None

                    risk_passed = []
                    for sig in strict_candidates:
                        approved = True
                        prob = None
                        features = {}
                        try:
                            if ml_filter and getattr(ml_filter, 'active', False):
                                features = extract_features(sig, market_data)
                                threshold = _current_ml_prob_threshold()
                                approved, prob = ml_filter.ml_filter(features, threshold=threshold)
                        except Exception:
                            approved, prob = True, None

                        # NEW: Log ML prediction to database for drift analysis
                        # Must happen BEFORE decision to ensure all predictions recorded
                        if prob is not None and sig.get('signal_id'):
                            try:
                                from engine.ml_logger import log_ml_prediction as _log_ml_pred
                                run_sync(
                                    _log_ml_pred(
                                        session=None,  # Will create new session inside
                                        signal_id=str(sig.get('signal_id') or ''),
                                        asset=str(sig.get('asset') or ''),
                                        timeframe=str(sig.get('timeframe') or ''),
                                        direction=str(sig.get('direction') or ''),
                                        ml_probability=float(prob),
                                        features=features if isinstance(features, dict) else {},
                                    )
                                )
                            except Exception as _ml_log_err:
                                logger.debug(f"[engine] ML prediction logging failed: {_ml_log_err}")

                        if not approved:
                            sig['ml_advisory'] = 'filtered_by_ml'
                            _log_decision("rejected", sig, reason="ml_filter", meta={"ml_probability": prob})
                            try:
                                run_sync(
                                    _ml_rejection_tracker.persist_rejection(
                                        asset=str(sig.get("asset") or ""),
                                        timeframe=str(sig.get("timeframe") or ""),
                                        direction=str(sig.get("direction") or ""),
                                        entry_price=float(sig.get("entry") or 0),
                                        stop_loss=float(sig.get("stop_loss") or 0),
                                        take_profit_levels=sig.get("take_profit") or sig.get("targets") or [],
                                        ml_probability=float(prob or 0),
                                        rejection_reason="ml_filter",
                                        features=features if isinstance(features, dict) else {},
                                    )
                                )
                            except Exception as e:
                                logger.debug(f"[engine] Failed to record ML rejection: {e}")
                                pass
                            continue
                        try:
                            ml_hard_min = float(os.getenv("ML_HARD_FILTER_MIN", "0.55") or 0.55)
                        except Exception:
                            ml_hard_min = 0.55
                        if prob is not None and float(prob) < ml_hard_min:
                            sig['ml_advisory'] = 'filtered_by_ml_hard_threshold'
                            _log_decision("rejected", sig, reason="ml_hard_filter", meta={"ml_probability": prob, "threshold": ml_hard_min})
                            continue
                        sig['ml_probability'] = prob
                        risk_passed.append(sig)

                    pipeline_stats["risk_passed"] += len(risk_passed)
                    if not risk_passed:
                        continue

                    # Scoring and advanced filters
                    final_signals = []
                    for sig in risk_passed:
                        try:
                            # enrich signal context from indicators
                            tf = sig.get('timeframe') or list(market_data.keys())[0]
                            tf_data = market_data.get(tf, {})
                            ind = tf_data.get('indicators', {})
                            candles = tf_data.get('candles', [])
                            last_close = candles[-1]['close'] if candles else None

                            # Candle-derived context features for ML/meta-modeling.
                            try:
                                _closes = [float(c.get('close')) for c in candles if isinstance(c, dict) and c.get('close') is not None]
                                _highs = [float(c.get('high')) for c in candles if isinstance(c, dict) and c.get('high') is not None]
                                _lows = [float(c.get('low')) for c in candles if isinstance(c, dict) and c.get('low') is not None]
                                _vols = [float(c.get('volume') or 0.0) for c in candles if isinstance(c, dict)]

                                def _pct(n: int) -> float:
                                    if len(_closes) <= n:
                                        return 0.0
                                    _p = float(_closes[-(n + 1)])
                                    _c = float(_closes[-1])
                                    return ((_c - _p) / _p) if _p > 0 else 0.0

                                def _atr(period: int) -> float:
                                    if len(_closes) < period + 1 or len(_highs) < period + 1 or len(_lows) < period + 1:
                                        return 0.0
                                    _trs = []
                                    for i in range(1, len(_closes)):
                                        h = float(_highs[i])
                                        l = float(_lows[i])
                                        pc = float(_closes[i - 1])
                                        _trs.append(max(h - l, abs(h - pc), abs(l - pc)))
                                    _tail = _trs[-period:] if len(_trs) >= period else _trs
                                    return (sum(_tail) / len(_tail)) if _tail else 0.0

                                _v3 = _pct(3)
                                _v5 = _pct(5)
                                _v10 = _pct(10)
                                _atr14 = _atr(14)
                                _atr50 = _atr(50)

                                sig['price_velocity_3'] = _v3
                                sig['price_velocity_5'] = _v5
                                sig['price_velocity_10'] = _v10
                                sig['price_acceleration_3_10'] = _v3 - _v10
                                sig['atr_rel'] = (_atr14 / float(_closes[-1])) if _closes and float(_closes[-1]) > 0 else 0.0
                                sig['atr_regime'] = (_atr14 / _atr50) if _atr50 > 0 else 0.0

                                if len(_vols) >= 21:
                                    _ma20v = sum(_vols[-21:-1]) / 20.0
                                    sig['relative_volume'] = (float(_vols[-1]) / _ma20v) if _ma20v > 0 else 0.0
                                else:
                                    sig['relative_volume'] = 0.0

                                def _mtf_trend(_tf: str) -> float:
                                    try:
                                        _tf_c = (market_data.get(_tf, {}) or {}).get('candles', [])
                                        _tf_close = [float(c.get('close')) for c in _tf_c if isinstance(c, dict) and c.get('close') is not None]
                                        if len(_tf_close) < 50:
                                            return 0.0
                                        _s20 = sum(_tf_close[-20:]) / 20.0
                                        _s50 = sum(_tf_close[-50:]) / 50.0
                                        if _s20 > _s50:
                                            return 1.0
                                        if _s20 < _s50:
                                            return -1.0
                                        return 0.0
                                    except Exception:
                                        return 0.0

                                sig['mtf_4h_trend'] = _mtf_trend('4h')
                                sig['mtf_1d_trend'] = _mtf_trend('1d')
                            except Exception:
                                pass

                            # Order-block proximity enrichment (best-effort)
                            if 'is_near_order_block' not in sig:
                                try:
                                    sig['is_near_order_block'] = _detect_order_blocks(candles)
                                except Exception:
                                    sig['is_near_order_block'] = False

                            # Add data freshness to signal
                            sig['data_age_seconds'] = tf_data.get('data_age_seconds', None)

                            sig.setdefault('close_price', ind.get('close_price', last_close or 0))
                            sig.setdefault('atr', ind.get('atr', sig.get('atr', 0)))

                            # score
                            score = 0
                            try:
                                score = float(score_signal(sig)) if score_signal else 0
                            except Exception:
                                score = 0
                            sig['score'] = score
                            sig.setdefault('confidence', min(1.0, score / 100.0))

                            # track highest scored candidate even if it doesn't pass final gates
                            try:
                                if max_candidate_score is None or score > max_candidate_score:
                                    max_candidate_score = score
                            except Exception as e:
                                logger.debug(f"[engine] Failed to update max candidate score: {e}")
                                pass

                            # advanced filters
                            market_filter_data = {
                                'price': sig.get('entry', sig.get('close_price', 0)),
                                'atr': sig.get('atr', 0),
                                'candles': candles,
                                'adx': ind.get('adx', 30),
                            }
                            passed_filters, rejections = advanced_filters.run_all_filters(sig, market_filter_data, None)
                            if not passed_filters:
                                sig['rejection_reason'] = ';'.join([str(r) for r in rejections or []])
                                _record_gate_failure(asset, "structure", sig['rejection_reason'])
                                _log_decision("skipped", sig, reason=sig['rejection_reason'])
                                continue

                            # ultra quality (optional)
                            if _env_bool('ULTRA_QUALITY_ENABLED', False):
                                should_trade, rejection, qscore = ultra_quality.apply_ultra_filter(sig)
                                if not should_trade:
                                    sig['rejection_reason'] = f'ultra:{rejection}'
                                    _record_gate_failure(asset, "ultra", sig['rejection_reason'])
                                    _log_decision("skipped", sig, reason=sig['rejection_reason'])
                                    continue

                            # calculate stops / tps if missing (ATR-based fallback)
                            entry = sig.get('entry', sig.get('close_price', 0))
                            sl = sig.get('stop_loss') or sig.get('stop')
                            tp = sig.get('take_profit') or sig.get('targets')
                            atr_val = float(sig.get('atr') or 0)
                            try:
                                entry_f = float(entry)
                            except Exception:
                                entry_f = 0.0
                            if (not sl or sl == entry) and atr_val > 0 and entry_f > 0:
                                direction = (sig.get('direction') or 'long').lower()
                                if direction == 'long':
                                    sl = entry_f - 2 * atr_val
                                else:
                                    sl = entry_f + 2 * atr_val
                            if (not tp or tp == entry) and atr_val > 0 and entry_f > 0 and sl and sl != entry:
                                rr = float(os.getenv('DEFAULT_RR', '2.0'))
                                try:
                                    slf = float(sl)
                                    if sig.get('direction', 'long').lower() == 'long':
                                        tp = entry_f + abs(entry_f - slf) * rr
                                    else:
                                        tp = entry_f - abs(entry_f - slf) * rr
                                except Exception as e:
                                    logger.debug(f"[engine] Failed to compute take profit level: {e}")
                                    pass

                            # Dynamic stop/target widening in high-volatility regimes.
                            try:
                                _atr_regime = float(sig.get('atr_regime') or 0.0)
                                _vol_widen_thr = float(os.getenv('VOLATILITY_WIDEN_ATR_MULT', '3.0') or 3.0)
                                if _atr_regime >= _vol_widen_thr and entry_f > 0 and sl:
                                    _sl_mult = float(os.getenv('VOLATILITY_WIDEN_SL_MULT', '1.25') or 1.25)
                                    _tp_mult = float(os.getenv('VOLATILITY_WIDEN_TP_MULT', '1.15') or 1.15)
                                    _dir = str(sig.get('direction') or 'long').lower()
                                    _slf = float(sl)
                                    _risk = abs(entry_f - _slf)
                                    if _risk > 0:
                                        if _dir == 'long':
                                            sl = entry_f - (_risk * _sl_mult)
                                        else:
                                            sl = entry_f + (_risk * _sl_mult)

                                    if isinstance(tp, (list, tuple)):
                                        _tp_new = []
                                        for _tpv in tp:
                                            try:
                                                _tpf = float(_tpv)
                                                _dist = abs(_tpf - entry_f)
                                                if _dir == 'long':
                                                    _tp_new.append(entry_f + (_dist * _tp_mult))
                                                else:
                                                    _tp_new.append(entry_f - (_dist * _tp_mult))
                                            except Exception:
                                                continue
                                        if _tp_new:
                                            tp = _tp_new
                                    elif tp is not None:
                                        _tpf = float(tp)
                                        _dist = abs(_tpf - entry_f)
                                        tp = (entry_f + (_dist * _tp_mult)) if _dir == 'long' else (entry_f - (_dist * _tp_mult))
                            except Exception:
                                pass
                            # Normalize take_profit: list-of-dicts (StrategySignal) → list of price floats
                            if isinstance(tp, (list, tuple)):
                                _tp_normalized = []
                                for _tp_item in tp:
                                    try:
                                        if isinstance(_tp_item, dict):
                                            _p = _tp_item.get('price') or _tp_item.get('tp') or _tp_item.get('target')
                                            if _p is not None:
                                                _tp_normalized.append(float(_p))
                                        else:
                                            _tp_normalized.append(float(_tp_item))
                                    except (TypeError, ValueError):
                                        pass
                                if _tp_normalized:
                                    tp = [p for p in _tp_normalized if p > 0]

                            # Sanity-check TP ordering vs entry/SL/direction.
                            # Long:  SL < entry < TP1 <= TP2 <= TP3
                            # Short: SL > entry > TP1 >= TP2 >= TP3
                            try:
                                _dir = str(sig.get('direction') or 'long').lower().strip()
                                _entry = float(entry_f)
                                _sl = float(sl) if sl is not None else 0.0
                                _tp_list: list[float] = []
                                if isinstance(tp, (list, tuple)):
                                    _tp_list = [float(x) for x in tp if x is not None]
                                elif tp is not None:
                                    _tp_list = [float(tp)]

                                if _tp_list and _entry > 0 and _sl > 0:
                                    if _dir == 'long':
                                        _tp_list = sorted([x for x in _tp_list if x > _entry])
                                        if not (_sl < _entry):
                                            _tp_list = []
                                    else:
                                        _tp_list = sorted([x for x in _tp_list if x < _entry], reverse=True)
                                        if not (_sl > _entry):
                                            _tp_list = []

                                tp = _tp_list if len(_tp_list) > 1 else (_tp_list[0] if _tp_list else None)
                            except Exception:
                                pass

                            if not tp:
                                sig['rejection_reason'] = 'invalid_tp_structure'
                                _record_gate_failure(asset, "structure", sig['rejection_reason'])
                                _log_decision("skipped", sig, reason=sig['rejection_reason'])
                                continue

                            sig['stop_loss'] = sl
                            sig['take_profit'] = tp

                            # ML-driven dynamic risk sizing hint (for formatters/executors).
                            try:
                                _mlp = float(sig.get('ml_probability') or 0.0)
                                if _mlp >= float(os.getenv('ML_HIGH_CONFIDENCE', '0.75') or 0.75):
                                    _risk_pct = float(os.getenv('ML_RISK_HIGH_PCT', '2.0') or 2.0)
                                elif _mlp >= float(os.getenv('ML_MEDIUM_CONFIDENCE', '0.50') or 0.50):
                                    _risk_pct = float(os.getenv('ML_RISK_MEDIUM_PCT', '1.0') or 1.0)
                                else:
                                    _risk_pct = float(os.getenv('ML_RISK_LOW_PCT', '0.5') or 0.5)
                                sig['risk_pct'] = max(0.1, min(_risk_pct, 5.0))

                                try:
                                    from engine.signal_calculations import calculate_position_size
                                    _pos = calculate_position_size(sig, account_balance=float(os.getenv('DEFAULT_ACCOUNT_BALANCE', '10000') or 10000), risk_pct=float(sig['risk_pct']))
                                    if _pos is not None:
                                        sig['position_size'] = float(_pos)
                                except Exception:
                                    pass
                            except Exception:
                                pass

                            # Final gates: score + expectancy
                            live_exp = float(sig.get('live_expectancy', 0.0) or 0.0)
                            if live_exp < 0.0:
                                # Down-weight underperforming setups first; hard-block can be re-enabled by env.
                                decay_floor = max(0.35, min(_env_float("EXPECTANCY_NEGATIVE_DECAY_FLOOR", 0.60), 1.0))
                                decay_span = max(0.01, _env_float("EXPECTANCY_NEGATIVE_DECAY_SPAN", 0.30))
                                severity = min(1.0, abs(live_exp) / decay_span)
                                mult = 1.0 - ((1.0 - decay_floor) * severity)
                                sig['expectancy_weight'] = float(mult)
                                sig['score'] = float(sig.get('score') or 0.0) * float(mult)
                                try:
                                    sig['confidence'] = max(0.01, min(1.0, float(sig.get('confidence') or 0.0) * float(mult)))
                                except Exception:
                                    pass

                            min_score_threshold = _current_min_score_threshold()
                            if sig.get('score', 0) < min_score_threshold:
                                sig['rejection_reason'] = f"score {sig.get('score',0)} < {min_score_threshold}"
                                _record_gate_failure(asset, "score", sig['rejection_reason'])
                                _log_decision("skipped", sig, reason=sig['rejection_reason'], meta={"score": sig.get("score")})
                                try:
                                    run_sync(
                                        _ml_rejection_tracker.persist_rejection(
                                            asset=str(sig.get("asset") or ""),
                                            timeframe=str(sig.get("timeframe") or ""),
                                            direction=str(sig.get("direction") or ""),
                                            entry_price=float(sig.get("entry") or 0),
                                            stop_loss=float(sig.get("stop_loss") or sig.get("stop") or 0),
                                            take_profit_levels=sig.get("take_profit") or sig.get("targets") or [],
                                            ml_probability=float(sig.get("ml_probability") or 0.0),
                                            rejection_reason=str(sig['rejection_reason']),
                                            features=dict(sig),
                                            rejection_type="final_score_gate",
                                        )
                                    )
                                except Exception as e:
                                    logger.debug(f"[engine] Failed to record score rejection: {e}")
                                continue

                            # Optional hard block remains available via env toggle.
                            if _env_bool("EXPECTANCY_HARD_BLOCK_ENABLED", False) and live_exp < 0.0:
                                sig['rejection_reason'] = f"low expectancy {live_exp:.3f}"
                                _record_gate_failure(asset, "expectancy", sig['rejection_reason'])
                                _log_decision("skipped", sig, reason=sig['rejection_reason'])
                                try:
                                    run_sync(
                                        _ml_rejection_tracker.persist_rejection(
                                            asset=str(sig.get("asset") or ""),
                                            timeframe=str(sig.get("timeframe") or ""),
                                            direction=str(sig.get("direction") or ""),
                                            entry_price=float(sig.get("entry") or 0),
                                            stop_loss=float(sig.get("stop_loss") or sig.get("stop") or 0),
                                            take_profit_levels=sig.get("take_profit") or sig.get("targets") or [],
                                            ml_probability=float(sig.get("ml_probability") or 0.0),
                                            rejection_reason=str(sig['rejection_reason']),
                                            features=dict(sig),
                                            rejection_type="expectancy_gate",
                                        )
                                    )
                                except Exception as e:
                                    logger.debug(f"[engine] Failed to record expectancy rejection: {e}")
                                continue

                            # Attach regime + timeframe-aware expiration so higher-timeframe
                            # setups are not invalidated too early.
                            sig['regime'] = regime
                            _sig_tf = str(sig.get('timeframe') or '1h').strip().lower()
                            _expiry_candles = max(1, _env_int('SIGNAL_EXPIRY_CANDLES', 2))
                            try:
                                sig['expires_at'] = signal_context.calculate_signal_expiration(
                                    _sig_tf,
                                    candles_validity=_expiry_candles,
                                )
                            except Exception:
                                from datetime import timedelta as _timedelta
                                _fallback_minutes = {
                                    '1m': 30,
                                    '5m': 90,
                                    '15m': 180,
                                    '1h': 720,
                                    '4h': 2880,
                                    '1d': 4320,
                                }.get(_sig_tf, 720)
                                sig['expires_at'] = datetime.utcnow() + _timedelta(minutes=_fallback_minutes)

                            try:
                                gemini_ok, gemini_score, gemini_reason = run_sync(
                                    _gemini_review_signal(
                                        sig,
                                        candles if isinstance(candles, list) else [],
                                        float(sig.get('news_sentiment') or 0.0) if sig.get('news_sentiment') is not None else None,
                                    ),
                                    timeout=20.0,
                                )
                                sig['gemini_review_score'] = gemini_score
                                sig['gemini_review_reason'] = gemini_reason
                                if not gemini_ok:
                                    sig['rejection_reason'] = f"gemini:{gemini_reason}"
                                    _record_gate_failure(asset, "gemini", sig['rejection_reason'])
                                    _log_decision("skipped", sig, reason=sig['rejection_reason'], meta={"gemini_score": gemini_score})
                                    try:
                                        run_sync(
                                            _ml_rejection_tracker.persist_rejection(
                                                asset=str(sig.get("asset") or ""),
                                                timeframe=str(sig.get("timeframe") or ""),
                                                direction=str(sig.get("direction") or ""),
                                                entry_price=float(sig.get("entry") or 0),
                                                stop_loss=float(sig.get("stop_loss") or sig.get("stop") or 0),
                                                take_profit_levels=sig.get("take_profit") or sig.get("targets") or [],
                                                ml_probability=float(sig.get("ml_probability") or 0.0),
                                                rejection_reason=str(sig['rejection_reason']),
                                                features=dict(sig),
                                                rejection_type="gemini_gate",
                                            )
                                        )
                                    except Exception as e:
                                        logger.debug(f"[engine] Failed to record gemini rejection: {e}")
                                    continue
                            except Exception:
                                pass

                            final_signals.append(sig)
                        except Exception:
                            logger.exception("scoring/filtering failed for signal")

                    collapsed_signals = _collapse_signal_variants(final_signals)
                    dropped_variants = max(0, len(final_signals) - len(collapsed_signals))
                    if dropped_variants:
                        logger.info(f"[engine] collapsed {dropped_variants} lower-ROI signal variants before storage")
                    final_signals = collapsed_signals

                    pipeline_stats["final_signals"] += len(final_signals)
                    # store final_signals
                    from datetime import timedelta as _timedelta  # ensure available in this scope

                    # Global kill-switch gate: block persistence / dispatch at the final stage.
                    try:
                        from engine.signal_controller import SignalController as _SignalController
                        if _SignalController().is_kill_switch_enabled():
                            logger.warning("CRITICAL: Global Kill-Switch is ACTIVE. Blocking signal delivery for asset=%s cycle=%s", asset, cycle_no)
                            pipeline_stats["skipped_kill_switch"] = int(pipeline_stats.get("skipped_kill_switch", 0) or 0) + len(final_signals)
                            continue
                    except Exception:
                        logger.debug("[engine] kill-switch final gate check failed", exc_info=True)

                    # ── Batch DB cooldown check (P11) ────────────────────────────────────────
                    # One query for all (asset, timeframe) pairs in this batch instead of
                    # one query per signal inside the loop.  Builds a set of "cooled-down"
                    # keys so the loop only does an O(1) set-lookup per signal.
                    _cd_mins = _env_int("SIGNAL_COOLDOWN_MINUTES", 30)
                    _cd_cutoff = datetime.utcnow() - _timedelta(minutes=_cd_mins)
                    _cooled_down_pairs: set[str] = set()
                    try:
                        from db.session import get_session as _get_s_cd
                        from db.models import Signal as _SigModel
                        from sqlalchemy import select as _sel_cd

                        async def _batch_cooldown_check() -> set[str]:
                            async with _get_s_cd() as _cs:
                                rows = (await _cs.execute(
                                    _sel_cd(_SigModel.asset, _SigModel.timeframe).where(
                                        _SigModel.created_at >= _cd_cutoff,
                                        _SigModel.expired.is_(False),
                                        _SigModel.archived.is_(False),
                                    ).distinct()
                                )).fetchall()
                                return {f"{r[0]}_{r[1]}" for r in rows}

                        _cooled_down_pairs = run_sync(_batch_cooldown_check(), timeout=15.0)
                    except Exception as _bcd_err:
                        logger.debug(f"[engine] batch cooldown pre-check failed, falling back to per-signal: {_bcd_err}")

                    stored_signals: list[dict] = []
                    for sig in final_signals:
                        try:
                            _asset_name = str(sig.get('asset') or sig.get('symbol') or '').upper().strip()
                            _asset_cls = _asset_class_key(_asset_name)
                            if int(open_counts_by_asset.get(_asset_name, 0)) >= int(open_limit_per_asset):
                                pipeline_stats["skipped_open_limit_asset"] += 1
                                logger.info(
                                    f"[engine] open-limit(asset): skipping {_asset_name} "
                                    f"count={open_counts_by_asset.get(_asset_name, 0)} limit={open_limit_per_asset}"
                                )
                                continue
                            if int(open_counts_by_class.get(_asset_cls, 0)) >= int(open_limit_per_class):
                                pipeline_stats["skipped_open_limit_class"] += 1
                                logger.info(
                                    f"[engine] open-limit(class): skipping {_asset_name} class={_asset_cls} "
                                    f"count={open_counts_by_class.get(_asset_cls, 0)} limit={open_limit_per_class}"
                                )
                                continue

                            _asset_tf_key = f"{sig.get('asset')}_{sig.get('timeframe')}"

                            # Fix 2: cycle-level dedup (same asset+TF already queued this batch)
                            if _asset_tf_key in _cycle_cooldown:
                                pipeline_stats["skipped_cycle_cooldown"] += 1
                                logger.info(f"[engine] cooldown(cycle): skipping duplicate {_asset_tf_key}")
                                continue

                            # DB cooldown — use pre-computed batch result (O(1) lookup)
                            if _asset_tf_key in _cooled_down_pairs:
                                pipeline_stats["skipped_db_cooldown"] += 1
                                logger.info(f"[engine] cooldown(db): active signal exists for {_asset_tf_key}, skipping")
                                continue

                            # ── Confluence Engine enrichment ───────────────────────────────────
                            try:
                                from engine.confluence_engine import run_confluence_engine
                                _tf_key  = sig.get('timeframe') or (list(market_data.keys())[0] if market_data else None)
                                _tf_data = market_data.get(_tf_key, {}) if _tf_key else {}
                                _candles = _tf_data.get('candles', []) if isinstance(_tf_data, dict) else []
                                if _candles:
                                    _conf_result = run_confluence_engine(_candles)
                                    sig['confluence_vote_count'] = _conf_result['score']
                                    sig['confluence_total']      = _conf_result['total']
                                    sig['confluence_direction']  = _conf_result['direction']
                                    sig['confluence_drivers']    = _conf_result['drivers']
                                    sig['long_votes']            = _conf_result['long_votes']
                                    sig['short_votes']           = _conf_result['short_votes']
                                    # Gate: skip if confluence direction contradicts the signal only when explicitly enabled.
                                    # By default this is advisory so a single directional disagreement does not starve signals.
                                    _conf_dir  = _conf_result['direction']
                                    _sig_dir   = str(sig.get('direction') or 'LONG').upper()
                                    _norm_sdir = 'LONG' if _sig_dir in ('LONG', 'BUY') else 'SHORT'
                                    _conf_hard_block = _env_bool('CONFLUENCE_DIRECTION_HARD_BLOCK_ENABLED', False)
                                    if _conf_dir != 'NEUTRAL' and _conf_dir != _norm_sdir:
                                        logger.info(
                                            f"[engine] confluence mismatch: signal={_norm_sdir} "
                                            f"confluence={_conf_dir} ({_conf_result['score']}/{_conf_result['total']}) "
                                            f"— {'skipping' if _conf_hard_block else 'allowing'} {sig.get('asset')}"
                                        )
                                        if _conf_hard_block:
                                            pipeline_stats["skipped_confluence_block"] += 1
                                            continue
                            except Exception as _ce:
                                logger.debug(f"[engine] confluence engine error: {_ce}")

    # ── Portfolio Exposure Manager Check ─────────────────────────────
                            # NEW: Check portfolio exposure limits before storing.
                            # This prevents over-exposure on correlated assets (e.g., 9 crypto shorts at once)
                            try:
                                _exp_enabled = _env_bool("PORTFOLIO_EXPOSURE_ENABLED", True)
                                if _exp_enabled:
                                    _direction = str(sig.get('direction') or 'long').lower().strip()
                                    # Use helper to get asset class
                                    _sig_asset_cls = _asset_class_key(_asset_name)
                                    # FIX: Use run_sync to call async function from sync context
                                    _is_allowed = run_sync(
                                        exposure_manager.is_trade_allowed(
                                            None,  # Session will be created inside if needed
                                            _sig_asset_cls,
                                            _direction,
                                        )
                                    )
                                    if not _is_allowed:
                                        pipeline_stats["skipped_portfolio_exposure"] = int(
                                            pipeline_stats.get("skipped_portfolio_exposure", 0) or 0
                                        ) + 1
                                        logger.info(
                                            f"[engine] portfolio_exposure: skipping {_asset_name} "
                                            f"class={_sig_asset_cls} direction={_direction} "
                                            "(exposure limit reached)"
                                        )
                                        continue
                            except Exception as _pex:
                                logger.debug(f"[engine] portfolio exposure check failed: {_pex}")

                            # Stamp created_at
                            # store_signal_compat sets it on the DB row but doesn't write it back
                            # to the dict; without this every is_signal_fresh() call returns False.
                            sig.setdefault('created_at', datetime.utcnow())
                            logger.info(f"[engine] storing signal: {sig.get('asset')} tf={sig.get('timeframe')} score={sig.get('score')} confluence={sig.get('confluence_vote_count', '?')}/{sig.get('confluence_total', 15)}")
                            stored_signal_id = store_signal_compat(sig)
                            if stored_signal_id:
                                sig["signal_id"] = str(stored_signal_id)
                                if _asset_name:
                                    open_counts_by_asset[_asset_name] = int(open_counts_by_asset.get(_asset_name, 0) + 1)
                                    open_counts_by_class[_asset_cls] = int(open_counts_by_class.get(_asset_cls, 0) + 1)
                                scored_signals_all.append(sig)
                                stored_signals.append(sig)
                                _cycle_cooldown.add(_asset_tf_key)
                                pipeline_stats["stored"] += 1
                                
                                # === PHASE 1 FIX: Increment delivered when signal is stored ===
                                stats.delivered += 1
                            else:
                                pipeline_stats["store_failed"] += 1
                        except Exception as e:
                            pipeline_stats["store_failed"] += 1
                            logger.exception("store_signal failed")

                            if not final_signals:
                                _maybe_log_heatmap(asset, cycle_no, 0)
                            else:
                                _maybe_log_heatmap(asset, cycle_no, len(final_signals))

                    # Track new signals as open trades
                    from core.trade_tracker import add_trade, update_trade_outcomes
                    for sig in stored_signals:
                        try:
                            add_trade(sig)
                        except Exception:
                            logger.exception("Failed to add trade for tracking")

                    # Update existing trade outcomes
                    try:
                        closed_trades = update_trade_outcomes()
                        if closed_trades:
                            logger.info(f"[engine] {len(closed_trades)} trades closed: {[(t.symbol, t.outcome) for t in closed_trades]}")
                            
                            # Notify users about trade outcomes
                            async def notify_users_about_outcomes():
                                """Send outcome notifications to users who received the signal."""
                                try:
                                    from db.session import get_session
                                    from db.models import SignalDelivery, User
                                    from sqlalchemy import select
                                    from db.pg_features import upsert_outcome
                                    
                                    async with get_session() as session:
                                        for trade in closed_trades:
                                            try:
                                                # Persist outcome so Telegram outcome jobs can track + notify reliably.
                                                try:
                                                    _sig_id = str(getattr(trade, "signal_id", "") or "")
                                                    if _sig_id:
                                                        _raw_outcome = str(getattr(trade, "outcome", "") or "").lower()
                                                        _status = "tp" if _raw_outcome.startswith("tp") else ("sl" if _raw_outcome == "sl" else _raw_outcome or "invalid")
                                                        _entry_t = getattr(trade, "entry_time", None)
                                                        _exit_t = getattr(trade, "exit_time", None)
                                                        _r = getattr(trade, "r_multiple", None)
                                                        _pct = getattr(trade, "pnl_pct", None)
                                                        _close_px = getattr(trade, "exit_price", None)
                                                        if _close_px is None:
                                                            _close_px = getattr(trade, "close_price", None)
                                                        await upsert_outcome(
                                                            session,
                                                            signal_id=_sig_id,
                                                            status=_status,
                                                            r_multiple=float(_r) if _r is not None else None,
                                                            percent=float(_pct) if _pct is not None else None,
                                                            opened_at=_entry_t,
                                                            closed_at=_exit_t,
                                                            meta={"close_price": _close_px} if _close_px is not None else None,
                                                        )
                                                        await session.commit()
                                                except Exception as _oc_persist_err:
                                                    logger.debug(f"Failed to persist outcome for signal {getattr(trade, 'signal_id', None)}: {_oc_persist_err}")

                                                # Find users who received this signal
                                                result = await session.execute(
                                                    select(SignalDelivery.user_id).where(
                                                        SignalDelivery.signal_id == trade.signal_id
                                                    )
                                                )
                                                user_ids = [row[0] for row in result.fetchall()]
                                                
                                                # Get user telegram IDs and send notifications
                                                for uid in user_ids:
                                                    try:
                                                        user_result = await session.execute(
                                                            select(User.telegram_user_id, User.tier).where(User.id == uid)
                                                        )
                                                        user_row = user_result.first()
                                                        if user_row:
                                                            telegram_id, tier = user_row
                                                            # Format outcome message
                                                            emoji = "✅" if trade.outcome in ("TP", "tp") else "🛑" if trade.outcome in ("SL", "sl") else "⚠️"
                                                            r_str = f"{trade.r_multiple:.2f}R" if hasattr(trade, 'r_multiple') and trade.r_multiple else ""
                                                            entry_val = getattr(trade, 'entry_price', None)
                                                            if entry_val is None:
                                                                entry_val = getattr(trade, 'entry', None)
                                                            close_val = getattr(trade, 'exit_price', None)
                                                            if close_val is None:
                                                                close_val = getattr(trade, 'close_price', None)
                                                            msg = (
                                                                f"{emoji} Signal Outcome\n\n"
                                                                f"Asset: {trade.symbol}\n"
                                                                f"Direction: {trade.direction.upper()}\n"
                                                                f"Outcome: {trade.outcome}\n"
                                                                f"R-Multiple: {r_str}\n"
                                                                f"Entry: {entry_val if entry_val is not None else 'N/A'}\n"
                                                                f"Close: {close_val if close_val is not None else 'N/A'}\n\n"
                                                                f"Ref: {trade.signal_id}"
                                                            )
                                                            try:
                                                                from signalrank_telegram.bot import application
                                                                if application and application.bot:
                                                                    await application.bot.send_message(chat_id=telegram_id, text=msg)
                                                            except Exception as e:
                                                                logger.debug(f"Failed to send outcome notification to user {uid}: {e}")
                                                    except Exception as e:
                                                        logger.debug(f"Failed to process user {uid} for outcome notification: {e}")
                                            except Exception as e:
                                                logger.debug(f"Failed to notify users about outcome for signal {trade.signal_id}: {e}")
                                except Exception as e:
                                    logger.warning(f"Failed to send outcome notifications: {e}")
                            
                            # main_loop is synchronous; run coroutine safely via run_sync.
                            try:
                                from utils.async_runner import run_sync as _run_sync
                                import asyncio as _asyncio

                                async def _notify_with_timeout() -> None:
                                    await _asyncio.wait_for(notify_users_about_outcomes(), timeout=30.0)

                                _run_sync(_notify_with_timeout())
                            except Exception:
                                pass
                                
                    except Exception:
                        logger.exception("Failed to update trade outcomes")

                except Exception as e:
                    logger.exception(f"[engine] pipeline error for asset={asset}")
                    continue

            # DELIVERY PHASE
            delivery_mgr = TierDeliveryManager()

            try:
                user_ids = list(get_all_user_ids_compat() or [])
            except Exception:
                user_ids = []

            # ensure owners/admins included
            for _oid in (OWNER_IDS or []):
                try:
                    oid = int(_oid)
                    if oid not in user_ids:
                        user_ids.append(oid)
                except Exception as e:
                    logger.debug(f"[engine] Failed to parse user ID from OWNER_TELEGRAM_ID: {e}")
                    pass
            for _aid in (ADMIN_IDS or []):
                try:
                    aid = int(_aid)
                    if aid not in user_ids:
                        user_ids.append(aid)
                except Exception as e:
                    logger.debug(f"[engine] Failed to parse user ID from ADMIN_IDS: {e}")
                    pass

            logger.info("[engine] delivery audience size=%s", len(user_ids))
            if not user_ids:
                logger.warning("[engine] delivery audience is empty; no users eligible for dispatch")

            async def filter_non_duplicate_signals(user_id: int, signals: List[Dict]) -> List[Dict]:
                """
                Filter out signals that were already sent to this user.
                
                Prevents sending the same signal multiple times to the user.
                Uses SignalDelivery table to check (user_id, signal_id) pairs.
                
                Args:
                    user_id: User ID
                    signals: List of signal dicts to filter
                    session: DB session
                
                Returns:
                    List of signals that haven't been sent to this user yet
                """
                if not signals:
                    return []
                
                signal_ids = [
                    str(sig.get("signal_id") or sig.get("id") or "").strip()
                    for sig in (signals or [])
                    if (sig.get("signal_id") or sig.get("id"))
                ]
                if not signal_ids:
                    return list(signals or [])

                try:
                    from db.session import get_session, is_db_configured
                    if not is_db_configured():
                        raise RuntimeError("DB not configured")
                    from db.models import SignalDelivery
                    from sqlalchemy import select

                    async with get_session() as session:
                        result = await session.execute(
                            select(SignalDelivery.signal_id).where(
                                SignalDelivery.user_id == int(user_id),
                                SignalDelivery.signal_id.in_(signal_ids),
                            )
                        )
                        already_sent = {str(row[0]) for row in (result.fetchall() or []) if row and row[0]}

                    if already_sent:
                        new_signals = [
                            s for s in signals
                            if str(s.get("signal_id") or s.get("id") or "").strip() not in already_sent
                        ]
                    else:
                        new_signals = list(signals or [])

                    if len(new_signals) < len(signals):
                        logger.info(
                            "[engine] Filtered duplicate signals for user %s: %s -> %s (skipped %s duplicates)",
                            user_id,
                            len(signals),
                            len(new_signals),
                            len(signals) - len(new_signals),
                        )
                    return new_signals
                except Exception as e:
                    logger.warning(f"[engine] Failed to filter duplicates for user {user_id}: {e}")
                    # Redis fallback: use best-effort in-memory/redis delivery cache.
                    try:
                        from core.redis_state import get_delivered_signals_sync
                        delivered = await asyncio.to_thread(get_delivered_signals_sync, int(user_id))
                        delivered = {str(x) for x in (delivered or set()) if x}
                        if delivered:
                            return [
                                s for s in (signals or [])
                                if str(s.get("signal_id") or s.get("id") or "").strip() not in delivered
                            ]
                    except Exception as redis_err:
                        logger.debug("[engine] Redis fallback dedupe failed for user %s: %s", user_id, redis_err)
                    # Return all signals if filtering fails (better to send duplicates than fail)
                    return signals

            async def deliver_all():
                dispatched_count = 0
                skipped_daily_limit = 0
                skipped_no_eligible_signals = 0
                users_seen = 0
                # session management adapted to your codebase
                try:
                    from db.session import get_session
                except Exception:
                    get_session = None

                # Pre-filter stale signals ONCE before the per-user loop.
                # Without this, each stale signal gets logged N times (once per user).
                # P7: Batch-fetch live prices for all unique assets in one concurrent
                # gather instead of one blocking HTTP call per signal.
                _live_price_cache: dict[str, float | None] = {}
                try:
                    from engine.stale_signal_validator import _get_live_price_async
                    _unique_assets = list({
                        str(_s.get("asset") or "")
                        for _s in scored_signals_all
                        if _s.get("asset")
                    })
                    if _unique_assets:
                        _price_tasks = [
                            asyncio.wait_for(_get_live_price_async(_a), timeout=5.0)
                            for _a in _unique_assets
                        ]
                        _price_results = await asyncio.gather(*_price_tasks, return_exceptions=True)
                        for _a, _pr in zip(_unique_assets, _price_results):
                            if isinstance(_pr, (int, float)) and float(_pr) > 0:
                                _live_price_cache[_a] = float(_pr)
                            else:
                                _live_price_cache[_a] = None
                                if _pr is not None and not isinstance(_pr, float):
                                    logger.debug(
                                        "[engine] batch price prefetch failed for %s: %s",
                                        _a, _pr,
                                    )
                        logger.info(
                            "[engine] batch price prefetch: assets=%d cached=%d",
                            len(_unique_assets),
                            sum(1 for v in _live_price_cache.values() if v is not None),
                        )
                except Exception as _pf_err:
                    logger.debug(f"[engine] batch price prefetch failed, continuing without cache: {_pf_err}")

                _fresh_scored_signals: list = []
                try:
                    from engine.stale_signal_validator import validate_signal_freshness
                    for _sig in scored_signals_all:
                        try:
                            _cached_px = _live_price_cache.get(str(_sig.get("asset") or ""))
                            _fresh, _reason, _price = await validate_signal_freshness(
                                _sig, cached_live_price=_cached_px
                            )
                            if _fresh:
                                # Store the confirmed live price so downstream steps
                                # (dispatch_signals / _check_entry_status) can reuse
                                # it without making another HTTP call.
                                if _price and _price > 0:
                                    _sig["current_price"] = _price
                                elif _cached_px and _cached_px > 0:
                                    _sig["current_price"] = _cached_px
                                _fresh_scored_signals.append(_sig)
                            else:
                                logger.info(
                                    f"[engine] Stale signal dropped — {_sig.get('asset')} "
                                    f"{_sig.get('timeframe')}: {_reason}"
                                )
                                # --- Rebuild with live price, keeping direction + strategy vote ---
                                _rebuilt = None
                                if _price and _price > 0:
                                    _rebuilt = _rebuild_stale_signal(_sig, _price)
                                if _rebuilt is not None:
                                    try:
                                        if get_session is not None:
                                            from db.pg_features import get_or_create_signal
                                            async with get_session() as _rs:
                                                _new_sig_row = await get_or_create_signal(_rs, _rebuilt)
                                                await _rs.commit()
                                                _rebuilt['signal_id'] = str(_new_sig_row.signal_id)
                                        _fresh_scored_signals.append(_rebuilt)
                                        logger.info(
                                            f"[engine] Stale signal REFRESHED — {_rebuilt.get('asset')} "
                                            f"{_rebuilt.get('timeframe')} "
                                            f"new_entry={_rebuilt['entry']:.5f}"
                                        )
                                    except Exception as _store_err:
                                        logger.debug(f"[engine] Failed to store refreshed signal: {_store_err}")
                                else:
                                    logger.debug(
                                        f"[engine] Could not rebuild stale signal for "
                                        f"{_sig.get('asset')} — no live price or bad SL/TP"
                                    )
                                # Mark original as expired in DB so resend job skips it.
                                try:
                                    _sig_id = _sig.get('signal_id') or _sig.get('id')
                                    if _sig_id and get_session is not None:
                                        from db.pg_features import expire_signal
                                        async with get_session() as _es:
                                            await expire_signal(_es, str(_sig_id))
                                            await _es.commit()
                                except Exception as _exp_err:
                                    logger.debug(f"[engine] Could not expire stale signal in DB: {_exp_err}")
                        except Exception:
                            _fresh_scored_signals.append(_sig)
                except Exception:
                    _fresh_scored_signals = list(scored_signals_all)

                # Correlation governance: keep only the strongest signal per
                # correlation cluster/timeframe to reduce compounding exposure.
                try:
                    _corr_enabled = _env_bool("FEATURE_SIGNAL_CORRELATION_FILTER_ENABLED", True)
                    _corr_mode = str(os.getenv("CORRELATION_FILTER_MODE", "best_per_cluster") or "best_per_cluster").strip().lower()
                    if _corr_enabled and _corr_mode == "best_per_cluster":
                        from engine.correlation_filter import select_best_per_cluster
                        _before = len(_fresh_scored_signals)
                        _fresh_scored_signals = select_best_per_cluster(_fresh_scored_signals)
                        _after = len(_fresh_scored_signals)
                        if _after < _before:
                            logger.info("[engine] correlation filter reduced signals: before=%s after=%s", _before, _after)
                except Exception as _corr_err:
                    logger.debug("[engine] correlation filter skipped: %s", _corr_err)

                for user_id in user_ids:
                    try:
                        users_seen += 1
                        from signalrank_telegram.access import resolve_user_tier
                        user_tier = 'free'
                        try:
                            user_tier = resolve_user_tier(user_id).lower()
                        except Exception as e:
                            logger.debug(f"[engine] Failed to resolve user tier for user {user_id}: {e}")
                            user_tier = 'free'

                        # Check daily limit
                        from core.tier_constants import TIER_DAILY_LIMITS
                        from db.session import get_session as _get_limit_session
                        from db.pg_features import count_signals_sent_today
                        
                        signals_sent_today = 0
                        try:
                            async with _get_limit_session() as _ls:
                                signals_sent_today = int(
                                    await count_signals_sent_today(_ls, int(user_id))
                                )
                                await _ls.commit()
                        except Exception as _dl_err:
                            logger.debug(
                                "[engine] DB daily-limit count failed for user=%s: %s",
                                user_id,
                                _dl_err,
                            )
                            signals_sent_today = 0
                        
                        daily_limit = TIER_DAILY_LIMITS.get(
                            user_tier,
                            TIER_DAILY_LIMITS.get("free", 3),
                        )
                        
                        if signals_sent_today >= daily_limit:
                            logger.info(f"[engine] daily limit reached for user={user_id} tier={user_tier}")
                            skipped_daily_limit += 1
                            continue

                        user_signals = []
                        for sig in _fresh_scored_signals:
                            if signals_sent_today + len(user_signals) >= daily_limit:
                                break

                            try:
                                from engine.price_validator import (
                                    is_signal_fresh, validate_price_drift,
                                    check_sl_tp_hit,
                                )

                                # Check signal freshness
                                is_fresh, fresh_reason = is_signal_fresh(sig)
                                if not is_fresh:
                                    logger.info(f"[engine] Skipping stale signal for {sig.get('asset')}: {fresh_reason}")
                                    continue

                                # Use pre-fetched cycle cache only (no blocking HTTP calls here)
                                asset = sig.get('asset')
                                current_price = _live_price_cache.get(str(asset or ""))
                                if current_price is None:
                                    try:
                                        current_price = float(sig.get("current_price")) if sig.get("current_price") is not None else None
                                    except Exception:
                                        current_price = None

                                if current_price is None:
                                    logger.debug(f"[engine] No cached current price for {asset}, using signal as-is")
                                else:
                                    current_price = float(current_price)
                                    # Check if SL/TP already hit
                                    should_skip, skip_reason = check_sl_tp_hit(sig, current_price)
                                    if should_skip:
                                        logger.info(f"[engine] Skipping signal for {asset}: {skip_reason}")
                                        continue

                                    # Validate price drift and update if needed
                                    is_valid, drift_reason, updated_sig = validate_price_drift(sig, current_price)
                                    if updated_sig:
                                        logger.info(f"[engine] Updated signal prices for {asset}: {drift_reason}")
                                        sig = updated_sig
                                        sig['price_updated'] = True
                                    else:
                                        sig['price_updated'] = False
                                    sig['current_price'] = current_price
                            except Exception as e:
                                logger.warning(f"[engine] Price validation failed for signal: {e}")
                                # Continue with signal delivery even if validation fails

                            # Robust eligibility check with logging
                            try:
                                eligible = delivery_mgr.should_send_signal(user_tier, float(sig.get('score', 0)), user_id=user_id)
                                logger.info(f"[engine] Eligibility for user={user_id} tier={user_tier} score={sig.get('score', 0)}: {eligible}")
                                if eligible:
                                    user_signals.append(sig)
                            except Exception as e:
                                logger.warning(f"[engine] Failed to check signal eligibility for user {user_id}: {e}")
                                pass

                        # ── Dispatch block (OUTSIDE the per-signal loop) ───────────────────
                        # Collect ALL eligible signals first, then dispatch once per user.
                        # Previously this block was inside the for-sig loop which caused:
                        #   1. dispatch called once per eligible signal (not once per user)
                        #   2. daily-limit counter never updated between dispatches
                        #   3. `continue` skipped to next sig instead of next user
                        if not user_signals:
                            skipped_no_eligible_signals += 1
                            continue

                        # Filter out signals already sent to this user (prevent duplicates)
                        user_signals = await filter_non_duplicate_signals(user_id, user_signals)
                        if not user_signals:
                            logger.debug(f"[engine] All signals already sent to user {user_id}, skipping dispatch")
                            skipped_no_eligible_signals += 1
                            continue

                        if DRY_RUN:
                            for msg in user_signals:
                                print(f"[DRY RUN][{user_tier}] {msg}")
                            dispatched_count += 1
                        else:
                            await dispatch_signals_async(user_signals, user_id=user_id)
                            dispatched_count += 1
                    except Exception:
                        logger.exception("deliver_all per-user failed")
                logger.info(
                    "[engine] delivery summary: users_seen=%s users_dispatched=%s skipped_daily_limit=%s skipped_no_eligible=%s",
                    users_seen,
                    dispatched_count,
                    skipped_daily_limit,
                    skipped_no_eligible_signals,
                )
                return dispatched_count

            try:
                dispatched = run_sync(deliver_all(), timeout=float(_env_float("DELIVER_ALL_TIMEOUT_SECONDS", 180.0)))
            except Exception:
                logger.exception("deliver_all failed")
                dispatched = 0

            # Record this batch as processed and update round stats.
            _cycle_queue.mark_done(assets, signals_generated=len(scored_signals_all))
            if _env_bool("ENGINE_CYCLE_LOG", True):
                logger.info(
                    f"[engine] batch_complete {_cycle_queue.round_progress} "
                    f"signals_this_batch={len(scored_signals_all)} dispatched={dispatched}"
                )
            if cycle_no % 10 == 0:
                try:
                    signal_analytics.flush()
                except Exception:
                    logger.exception("analytics flush failed")

            # Automated analyst: trigger Gemini audit when many strict candidates were rejected
            try:
                if str(os.getenv("AUTO_ANALYST_ENABLED", "1")).strip().lower() in {"1", "true", "yes"}:
                    try:
                        # Only run when strict_candidates list exists in this scope and useful work was skipped
                        if 'strict_candidates' in globals() or 'strict_candidates' in locals():
                            sc_count = len(strict_candidates) if isinstance(strict_candidates, list) else 0
                            fs_count = len(final_signals) if isinstance(final_signals, list) else 0
                            if sc_count > 0 and sc_count > fs_count:
                                try:
                                    from services.automated_analyst import run_automated_audit
                                    # Best-effort synchronous call with timeout so the engine isn't blocked long
                                    try:
                                        run_sync(run_automated_audit(cycle_no, sc_count, fs_count), timeout=60.0)
                                    except Exception:
                                        # swallow - non-critical
                                        logger.debug("[engine] automated analyst call failed or timed out", exc_info=True)
                                except Exception:
                                    logger.debug("[engine] failed to import automated_analyst", exc_info=True)
                    except Exception:
                        logger.debug("[engine] automated analyst check failed", exc_info=True)
            except Exception:
                pass

            # cycle logging
            if _env_bool("ENGINE_CYCLE_LOG", True):
                try:
                    top_score = max((s.get('score', 0) for s in scored_signals_all), default=None)
                    if top_score is None:
                        top_score = max_candidate_score
                    if _env_bool("ENGINE_PIPELINE_DEBUG", True):
                        stats_str = " ".join([f"{k}={v}" for k, v in pipeline_stats.items()])
                    else:
                        stats_str = ""
                    print(
                        f"[engine] cycle={cycle_no} assets={cycle_assets} generated_signals={len(scored_signals_all)} "
                        f"max_score={top_score} max_score_pre_threshold={max_candidate_score} {stats_str}",
                        flush=True,
                    )
                except Exception as e:
                    logger.debug(f"[engine] Failed to print analytics stats: {e}")
                    pass

            # ── Anti-stagnation: stamp last_analyzed_at for managed assets ────────
            # Only DB-pinned assets need the timestamp; env/discovered assets are
            # excluded so the managed_assets table stays minimal.
            _managed_set = set(_managed_assets)
            _batch_managed = [a for a in assets if a in _managed_set]
            if _batch_managed:
                try:
                    from db.session import get_session as _get_session
                    from db.pg_features import update_managed_asset_last_analyzed as _stamp
                    from utils.async_runner import run_sync as _rs
                    async def _do_stamp():
                        async with _get_session() as _s:
                            await _stamp(_s, _batch_managed)
                            await _s.commit()
                    _rs(_do_stamp())
                except Exception:
                    pass

            # ── Auto-discovery persistence: promote high-ROI / high-score assets ───
            # Keeps strong discovered symbols in managed_assets so they continue to be
            # analyzed in future cycles even when short-term trending APIs fluctuate.
            if _env_bool("AUTO_PROMOTE_HIGH_ROI_ASSETS", True):
                try:
                    _min_score = _env_float("AUTO_MANAGED_ASSET_MIN_SCORE", 88.0)
                    _min_rr = _env_float("AUTO_MANAGED_ASSET_MIN_RR", 1.8)
                    _max_add_per_cycle = max(1, _env_int("AUTO_MANAGED_ASSET_MAX_PER_CYCLE", 3))

                    _candidates: list[str] = []
                    for _sig in scored_signals_all:
                        try:
                            _score = _safe_float(_sig.get("score"), 0.0)
                            _rr = _signal_roi_score(_sig)
                            _asset = _normalize_asset_symbol(str(_sig.get("asset") or "").upper())
                            if not _asset:
                                continue
                            if _score < _min_score or _rr < _min_rr:
                                continue
                            _candidates.append(_asset)
                        except Exception:
                            continue

                    _candidates = _dedupe_preserve_order(_candidates)[:_max_add_per_cycle]
                    if _candidates:
                        from db.session import get_session as _get_session
                        from db.pg_features import add_managed_asset as _add_managed_asset
                        from utils.async_runner import run_sync as _rs

                        async def _promote() -> int:
                            added = 0
                            async with _get_session() as _s:
                                for _sym in _candidates:
                                    _atype = "crypto" if is_crypto(_sym) else ("fx" if is_fx(_sym) else ("commodity" if is_commodity(_sym) else "stock"))
                                    await _add_managed_asset(
                                        _s,
                                        symbol=_sym,
                                        asset_type=_atype,
                                        added_by=None,
                                        note="auto-promoted by engine (high score/ROI)",
                                    )
                                    added += 1
                                await _s.commit()
                            return added

                        _added = int(_rs(_promote()) or 0)
                        if _added:
                            logger.info("[engine] auto-promoted managed assets: %s", ",".join(_candidates[:_added]))
                except Exception as _promote_err:
                    logger.debug("[engine] auto-promotion skipped: %s", _promote_err)

            # Avoid forced GC here; it surfaces asyncpg/SQLAlchemy finalizers while
            # connections are still in-flight and adds noisy SAWarnings in production.
            if _env_bool("ENGINE_FORCE_GC", False):
                try:
                    import gc as _gc
                    _gc.collect()
                except Exception:
                    pass

            time.sleep(max(5, cycle_sleep_seconds))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main_loop(DRY_RUN=(_env_bool('DRY_RUN', True)))
