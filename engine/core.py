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
from collections import Counter
from typing import Any, Dict, List
from datetime import datetime, timedelta as _timedelta

# Core engine pieces (ensure these exist in your repo or adapt names)
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
from db.pg_compat import get_all_user_ids_compat, store_signal_compat
from db.repository import persist_decision_log
from engine.signal_deduplicator import MLRejectionTracker
from engine.ranking import rank_signals
from signalrank_telegram.bot import dispatch_signals, _send_message_sync
from core.redis_state import state
from config import OWNER_IDS, ADMIN_IDS

# Optional advanced features (graceful fallback if missing)
try:
    from data.market_data import detect_order_blocks as _detect_order_blocks
except Exception:
    def _detect_order_blocks(candles, lookback=100) -> bool:  # type: ignore
        return False

try:
    from services.economic_calendar import is_no_trade_zone_sync as _is_no_trade_zone_sync
except Exception:
    def _is_no_trade_zone_sync(symbol: str, buffer_minutes: int = 30) -> bool:  # type: ignore
        return False

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


def _log_decision(decision: str, sig: Dict[str, Any], reason: str | None = None, meta: Dict[str, Any] | None = None) -> None:
    try:
        run_sync(
            persist_decision_log(
                sig.get("signal_id"),
                sig.get("asset"),
                sig.get("timeframe"),
                decision,
                reason=reason,
                meta=meta or {},
            )
        )
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
                    for name, mins in unhealthy:
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
                data = await asyncio.wait_for(fetch_market_data_cached(asset, tfs), timeout=max(5.0, per_asset_timeout))
                if not data or not any(data.values()):
                    logger.error(f"[engine] candle_fetch asset={asset} status=empty (no candles returned)")
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
            except asyncio.TimeoutError:
                logger.warning(f"[engine] candle_fetch asset={asset} status=timeout")
                return asset, {}
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
MIN_SCORE_THRESHOLD = _env_float("PREMIUM_SCORE_THRESHOLD", 70)


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

    # Start outcome tracker unless explicitly disabled (default off on Railway).
    try:
        _running_on_railway = bool((os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
        _enable_engine_tracker_default = False if _running_on_railway else True
        _enable_engine_tracker = str(
            os.getenv(
                "ENGINE_OUTCOME_TRACKER_ENABLED",
                "1" if _enable_engine_tracker_default else "0",
            )
        ).strip().lower() in {"1", "true", "yes", "on"}

        if _enable_engine_tracker:
            import threading
            import asyncio as _asyncio

            def _start_outcome_tracker_thread() -> None:
                try:
                    loop = _asyncio.new_event_loop()
                    _asyncio.set_event_loop(loop)
                    from engine.realtime_outcome_tracker import outcome_tracker

                    async def _run_tracker():
                        stop_event = _asyncio.Event()
                        await outcome_tracker.start()
                        try:
                            await stop_event.wait()
                        except (_asyncio.CancelledError, Exception):
                            pass
                        finally:
                            await outcome_tracker.stop()

                    loop.run_until_complete(_run_tracker())
                except Exception as _ot_err:
                    logger.warning("[engine] outcome tracker thread error: %s", _ot_err)

            _ot_thread = threading.Thread(
                target=_start_outcome_tracker_thread,
                name="outcome-tracker",
                daemon=True,
            )
            _ot_thread.start()
            logger.info("[engine] RealtimeOutcomeTracker thread launched")
        else:
            logger.info("[engine] RealtimeOutcomeTracker disabled for this engine instance")
    except Exception as _launch_err:
        logger.warning("[engine] Could not launch outcome tracker thread: %s", _launch_err)

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
    _tf_default = '1h,4h' if _running_on_railway else '1h,4h,1d'
    crypto_timeframes = [tf.strip() for tf in (os.getenv('CRYPTO_TIMEFRAMES', _tf_default).split(',')) if tf.strip()]
    fx_timeframes = [tf.strip() for tf in (os.getenv('FX_TIMEFRAMES', _tf_default).split(',')) if tf.strip()]
    stock_timeframes = [tf.strip() for tf in (os.getenv('STOCK_TIMEFRAMES', _tf_default).split(',')) if tf.strip()]
    commodity_timeframes = [tf.strip() for tf in (os.getenv('COMMODITY_TIMEFRAMES', _tf_default).split(',')) if tf.strip()]

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
    while True:
        cycle_no += 1
        cycle_sleep_seconds = 10
        now = time.time()
        # Heartbeat log every 30 seconds
        if now - last_heartbeat > 30:
            logger.info(f"[engine] heartbeat: cycle={cycle_no} running")
            print(f"[engine] heartbeat: cycle={cycle_no} running", flush=True)
            last_heartbeat = now

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

        # Feed the queue; refresh_universe only rebuilds once per hour
        # (CYCLE_UNIVERSE_REFRESH_INTERVAL env var) unless this is wakeup #1.
        _cycle_queue.refresh_universe(_all_open, force=(cycle_no == 1))

        # Pop this batch from the queue.
        _running_on_railway = bool((os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
        _default_cycle_batch = 6 if _running_on_railway else 10
        CYCLE_BATCH_SIZE = _env_int("CYCLE_BATCH_SIZE", _default_cycle_batch)
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
        _TF_SLEEP_MAP = {"1m": 60, "5m": 120, "15m": 300, "1h": 300, "4h": 900, "1d": 3600, "1w": 7200}
        env_sleep = _env_int("ENGINE_CYCLE_SLEEP_SECONDS", 0)
        if env_sleep > 0:
            cycle_sleep_seconds = env_sleep
        else:
            all_tfs = []
            for tfs in asset_to_tfs.values():
                all_tfs.extend(tfs)
            smallest_tf = min(all_tfs, key=lambda tf: _TF_SLEEP_MAP.get(tf, 300)) if all_tfs else "1h"
            cycle_sleep_seconds = _TF_SLEEP_MAP.get(smallest_tf, 300)

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
        }

        # Per-asset pipeline
        for asset in assets:
            logger.info(f"[engine] pipeline: starting asset={asset}")
            try:
                market_data = all_market_data.get(asset, {})

                # Basic safety: ensure we have at least one TF with candles
                has_candles = any((tf_data.get('candles') for tf_data in market_data.values())) if isinstance(market_data, dict) else False
                if not has_candles:
                    logger.warning(f"[engine] No market data for asset={asset}")
                    continue

                # Check data age for each timeframe
                # Data is considered stale if older than 2x the timeframe interval
                # (e.g., 1h candles stale after 2 hours, allows for provider delays)
                _TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}
                stale_data = False
                for tf, tf_data in market_data.items():
                    if isinstance(tf_data, dict):
                        data_age = tf_data.get("data_age_seconds")
                        tf_interval = _TF_SECONDS.get(tf, 3600)
                        max_age = tf_interval * 2  # Allow 2x interval for provider delays
                        if data_age is not None and data_age > max_age:
                            logger.warning(f"[engine] Stale data for {asset} {tf}: age={data_age}s > max={max_age}s, skipping")
                            stale_data = True
                            break
                if stale_data:
                    continue

                # Economic calendar no-trade-zone gate (30-min buffer around high-impact events)
                try:
                    if _is_no_trade_zone_sync(asset):
                        logger.info(f"[engine] no_trade_zone gate: skipping asset={asset} (high-impact event within 30 min)")
                        continue
                except Exception:
                    pass

                # Detect regime
                try:
                    regime = detect_market_regime(market_data)
                except Exception:
                    regime = None

                # News sentiment (non-critical)
                try:
                    news_sent = get_news_sentiment(asset)
                    market_data['news_sentiment'] = news_sent
                except Exception:
                    market_data['news_sentiment'] = None

                # Run strategies -> returns list of signals (each is a dict)
                try:
                    strategy_signals = run_all_strategies(asset, market_data, regime) or []
                except Exception:
                    logger.exception(f"Strategies failed for {asset}")
                    strategy_signals = []

                pipeline_stats["strategy_signals"] += len(strategy_signals)
                if not strategy_signals:
                    logger.debug(f"[engine] No strategy signals for {asset}")
                    continue

                # Normalize & dedupe (using SignalController if available)
                try:
                    from engine.signal_controller import SignalController
                    controller = SignalController()
                    normalized = controller.normalize_signals(strategy_signals)
                except Exception:
                    normalized = strategy_signals
                pipeline_stats["normalized"] += len(normalized)

                # Consensus filter
                try:
                    consensus_signals = apply_consensus_filter(normalized)
                except Exception:
                    consensus_signals = normalized
                # Fallback: if consensus is too strict, keep normalized signals to avoid zero output
                if not consensus_signals:
                    _log_decision("skipped", {"asset": asset, "timeframe": "*"}, reason="consensus_empty_fallback")
                    consensus_signals = normalized
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
                            _log_decision("skipped", sig, reason=sig['rejection_reason'])
                            continue
                        # risk gate
                        account_state = type('AccountState', (), {'drawdown': 0.0})()
                        if not risk_check(sig, account_state):
                            sig['rejection_reason'] = 'risk/volatility'
                            _log_decision("skipped", sig, reason=sig['rejection_reason'])
                            continue
                        # confluence
                        conf = calculate_confluence(sig)
                        if conf < 20:  # relaxed here; tune via env
                            sig['rejection_reason'] = f'confluence {conf:.1f}%'
                            _log_decision("skipped", sig, reason=sig['rejection_reason'], meta={"confluence": conf})
                            continue
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
                    if ml_filter and getattr(ml_filter, 'active', False):
                        try:
                            features = extract_features(sig, market_data)
                            approved, prob = ml_filter.ml_filter(features, threshold=float(os.getenv('ML_PROB_THRESHOLD', '0.72')))
                        except Exception:
                            approved, prob = True, None
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
                            _log_decision("skipped", sig, reason=sig['rejection_reason'])
                            continue

                        # ultra quality (optional)
                        if _env_bool('ULTRA_QUALITY_ENABLED', False):
                            should_trade, rejection, qscore = ultra_quality.apply_ultra_filter(sig)
                            if not should_trade:
                                sig['rejection_reason'] = f'ultra:{rejection}'
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

                        # final gating by score threshold
                        if sig.get('score', 0) < MIN_SCORE_THRESHOLD:
                            sig['rejection_reason'] = f"score {sig.get('score',0)} < {MIN_SCORE_THRESHOLD}"
                            _log_decision("skipped", sig, reason=sig['rejection_reason'], meta={"score": sig.get("score")})
                            continue

                        # attach regime & expiration (30-minute hard cap per product requirement)
                        # rationale: reduce stale-signal risk in fast markets and keep lifecycle aligned with
                        # the short monitoring/tracking window used by outcome delivery and expiry jobs.
                        sig['regime'] = regime
                        from datetime import timedelta as _timedelta
                        sig['expires_at'] = datetime.utcnow() + _timedelta(minutes=30)

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

                    _cooled_down_pairs = run_sync(_batch_cooldown_check())
                except Exception as _bcd_err:
                    logger.debug(f"[engine] batch cooldown pre-check failed, falling back to per-signal: {_bcd_err}")

                for sig in final_signals:
                    try:
                        _asset_tf_key = f"{sig.get('asset')}_{sig.get('timeframe')}"

                        # Fix 2: cycle-level dedup (same asset+TF already queued this batch)
                        if _asset_tf_key in _cycle_cooldown:
                            logger.info(f"[engine] cooldown(cycle): skipping duplicate {_asset_tf_key}")
                            continue

                        # DB cooldown — use pre-computed batch result (O(1) lookup)
                        if _asset_tf_key in _cooled_down_pairs:
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
                                # Gate: skip if confluence direction contradicts the signal
                                _conf_dir  = _conf_result['direction']
                                _sig_dir   = str(sig.get('direction') or 'LONG').upper()
                                _norm_sdir = 'LONG' if _sig_dir in ('LONG', 'BUY') else 'SHORT'
                                if _conf_dir != 'NEUTRAL' and _conf_dir != _norm_sdir:
                                    logger.info(
                                        f"[engine] confluence mismatch: signal={_norm_sdir} "
                                        f"confluence={_conf_dir} ({_conf_result['score']}/{_conf_result['total']}) "
                                        f"— skipping {sig.get('asset')}"
                                    )
                                    continue
                        except Exception as _ce:
                            logger.debug(f"[engine] confluence engine error: {_ce}")

                        # Stamp created_at so freshness checks in the delivery loop have a timestamp.
                        # store_signal_compat sets it on the DB row but doesn't write it back
                        # to the dict; without this every is_signal_fresh() call returns False.
                        sig.setdefault('created_at', datetime.utcnow())
                        logger.info(f"[engine] storing signal: {sig.get('asset')} tf={sig.get('timeframe')} score={sig.get('score')} confluence={sig.get('confluence_vote_count', '?')}/{sig.get('confluence_total', 15)}")
                        stored_signal_id = store_signal_compat(sig)
                        if stored_signal_id:
                            sig["signal_id"] = str(stored_signal_id)
                        scored_signals_all.append(sig)
                        _cycle_cooldown.add(_asset_tf_key)
                        pipeline_stats["stored"] += 1
                    except Exception as e:
                        logger.exception("store_signal failed")

                # Track new signals as open trades
                from core.trade_tracker import add_trade, update_trade_outcomes
                for sig in final_signals:
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
                    from datetime import datetime
                    from core.redis_state import state
                    from core.tier_constants import TIER_DAILY_LIMITS
                    
                    date_str = datetime.utcnow().strftime('%Y-%m-%d')
                    redis_key = f"signals_sent:{user_id}:{date_str}"
                    signals_sent_today = 0
                    try:
                        signals_sent_today = int(state.get_sync(redis_key) or 0)
                    except Exception:
                        signals_sent_today = 0
                    
                    daily_limit = TIER_DAILY_LIMITS.get(user_tier, 2)
                    
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
                                check_sl_tp_hit, get_current_price,
                                enrich_signal_with_live_price
                            )

                            # Check signal freshness
                            is_fresh, fresh_reason = is_signal_fresh(sig)
                            if not is_fresh:
                                logger.info(f"[engine] Skipping stale signal for {sig.get('asset')}: {fresh_reason}")
                                continue

                            # Get current market price
                            asset = sig.get('asset')
                            current_price = get_current_price(asset)

                            if current_price is None:
                                logger.warning(f"[engine] Failed to fetch current price for {asset}, using signal as-is")
                                # Still deliver if we can't fetch price - enrich with age at least
                                sig = enrich_signal_with_live_price(sig)
                            else:
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
                                    # Enrich with current price and age
                                    sig = enrich_signal_with_live_price(sig)
                                    sig['price_updated'] = True
                                else:
                                    # Enrich with current price and age
                                    sig = enrich_signal_with_live_price(sig)
                                    sig['price_updated'] = False
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

                    if not user_signals:
                        skipped_no_eligible_signals += 1
                        continue

                    if DRY_RUN:
                        for msg in user_signals:
                            print(f"[DRY RUN][{user_tier}] {msg}")
                        dispatched_count += 1
                    else:
                        _dispatched_ok = False
                        try:
                            dispatch_signals(user_signals, user_id=user_id)
                            _dispatched_ok = True
                        except Exception as e:
                            logger.warning(f"[engine] Failed to dispatch signals: {e}")
                            logger.exception("dispatch_signals failed")
                        if _dispatched_ok:
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
            dispatched = run_sync(deliver_all())
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

        # Explicit per-cycle garbage collection to keep memory stable on long
        # running Railway workers.
        try:
            import gc as _gc
            _gc.collect()
        except Exception:
            pass

        time.sleep(max(5, cycle_sleep_seconds))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main_loop(DRY_RUN=(_env_bool('DRY_RUN', True)))
