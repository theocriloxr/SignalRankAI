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
from config import OWNER_IDS

# Optional advanced features (graceful fallback if missing)
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


# Background outage alert job
def start_outage_alert_job():
    def _job():
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        bot = None
        try:
            from telegram import Bot
            bot = Bot(token=bot_token) if bot_token else None
        except Exception:
            bot = None
        while True:
            try:
                unhealthy = []
                try:
                    from data.fetcher import get_unhealthy_providers
                    unhealthy = get_unhealthy_providers()
                except Exception:
                    unhealthy = []
                if unhealthy and bot is not None:
                    for name, mins in unhealthy:
                        msg = f"🚨 Provider outage: {name} has been down for {mins:.1f} minutes."
                        for admin_id in (OWNER_IDS or []):
                            try:
                                _send_message_sync(bot, admin_id, msg)
                            except Exception:
                                logger.exception("Failed to send outage message")
                time.sleep(120)
            except Exception:
                logger.exception("outage alert job failed")
                time.sleep(120)
    t = threading.Thread(target=_job, daemon=True)
    t.start()


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


MIN_SCORE_THRESHOLD = _env_float("PREMIUM_SCORE_THRESHOLD", 55)


def load_tradable_assets() -> List[str]:
    raw = (os.getenv("TRADABLE_ASSETS") or "").strip()
    if not raw:
        # If get_all_tradable_assets exists, use it as default
        try:
            all_assets = list(get_all_tradable_assets() or [])
            return [a for a in all_assets]
        except Exception:
            return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def main_loop(DRY_RUN: bool = False):
    start_outage_alert_job()

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
    crypto_timeframes = [tf.strip() for tf in (os.getenv('CRYPTO_TIMEFRAMES', '1h,4h,1d').split(',')) if tf.strip()]
    fx_timeframes = [tf.strip() for tf in (os.getenv('FX_TIMEFRAMES', '1h,4h,1d').split(',')) if tf.strip()]
    stock_timeframes = [tf.strip() for tf in (os.getenv('STOCK_TIMEFRAMES', '1h,4h,1d').split(',')) if tf.strip()]
    commodity_timeframes = [tf.strip() for tf in (os.getenv('COMMODITY_TIMEFRAMES', '1h,4h,1d').split(',')) if tf.strip()]

    cycle_no = 0

    # Keep the main loop simple and robust
    while True:
        cycle_no += 1
        cycle_sleep_seconds = 10

        # Acquire assets list
        assets = load_tradable_assets()
        if not assets:
            try:
                assets = list(get_all_trending_pairs() or []) + list(get_trending_stock_tickers() or [])
            except Exception:
                assets = []

        assets = _dedupe_preserve_order(assets)
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

        # Bound crypto/fx/stocks per cycle using rotation
        crypto_max_pairs = _env_int("CRYPTO_MAX_PAIRS_PER_CYCLE", 20)
        crypto_pair_rotation = _env_bool("CRYPTO_PAIR_ROTATION", True)
        if crypto_max_pairs > 0 and len(crypto_assets) > crypto_max_pairs:
            start = (cycle_no - 1) * crypto_max_pairs
            crypto_assets = _rotate_slice(crypto_assets, start, crypto_max_pairs) if crypto_pair_rotation else crypto_assets[:crypto_max_pairs]

        fx_max_pairs = _env_int("FX_MAX_PAIRS_PER_CYCLE", 10)
        fx_pair_rotation = _env_bool("FX_PAIR_ROTATION", True)
        if fx_max_pairs > 0 and len(fx_assets) > fx_max_pairs:
            start = (cycle_no - 1) * fx_max_pairs
            fx_assets = _rotate_slice(fx_assets, start, fx_max_pairs) if fx_pair_rotation else fx_assets[:fx_max_pairs]

        stock_max_pairs = _env_int("STOCK_MAX_PAIRS_PER_CYCLE", 10)
        stock_pair_rotation = _env_bool("STOCK_PAIR_ROTATION", True)
        if stock_max_pairs > 0 and len(stock_assets) > stock_max_pairs:
            start = (cycle_no - 1) * stock_max_pairs
            stock_assets = _rotate_slice(stock_assets, start, stock_max_pairs) if stock_pair_rotation else stock_assets[:stock_max_pairs]

        # Ensure minimum diversity: at least 1 from each open category
        def _ensure_minimum(assets_list, category_name, min_count=1):
            """Log if category has fewer assets than minimum."""
            if len(assets_list) < min_count and len(assets_list) > 0:
                logger.info(f"[engine] {category_name} has {len(assets_list)} assets, below minimum {min_count}")
            return assets_list

        crypto_assets = _ensure_minimum(crypto_assets, "crypto", 1)
        fx_assets = _ensure_minimum(fx_assets, "fx", 1) if fx_enabled else []
        stock_assets = _ensure_minimum(stock_assets, "stocks", 1) if stocks_enabled else []
        commodity_assets = _ensure_minimum(commodity_assets, "commodities", 1)

        # Build cycle_assets ensuring diversity (round-robin from each category)
        cycle_assets_list = []
        # Add at least 1 from each category first (if available)
        for category in [crypto_assets, fx_assets, stock_assets, commodity_assets]:
            if category and category[0] not in cycle_assets_list:
                cycle_assets_list.append(category[0])
        # Then add remaining assets
        for category in [crypto_assets, fx_assets, stock_assets, commodity_assets]:
            for a in category:
                if a not in cycle_assets_list:
                    cycle_assets_list.append(a)
        
        assets = cycle_assets_list
        cycle_assets = len(assets)

        if _env_bool("ENGINE_CYCLE_LOG", True) and _env_bool("ENGINE_ASSET_DEBUG", False):
            sample = ",".join(assets[:10])
            logger.info(f"[engine] cycle={cycle_no} assets={cycle_assets} sample={sample}")

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
            all_market_data = run_sync(_fetch_market_data_for_assets(asset_to_tfs_degraded))
        except Exception:
            logger.exception("Market data fetch failed")
            all_market_data = {}

        scored_signals_all: List[Dict] = []
        max_candidate_score = None
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
                            approved, prob = ml_filter.ml_filter(features, threshold=float(os.getenv('ML_PROB_THRESHOLD', '0.65')))
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
                        sig['stop_loss'] = sl
                        sig['take_profit'] = tp

                        # final gating by score threshold
                        if sig.get('score', 0) < MIN_SCORE_THRESHOLD:
                            sig['rejection_reason'] = f"score {sig.get('score',0)} < {MIN_SCORE_THRESHOLD}"
                            _log_decision("skipped", sig, reason=sig['rejection_reason'], meta={"score": sig.get("score")})
                            continue

                        # attach regime & expiration
                        sig['regime'] = regime
                        sig['expires_at'] = signal_context.calculate_signal_expiration(sig.get('timeframe', '1h'))

                        final_signals.append(sig)
                    except Exception:
                        logger.exception("scoring/filtering failed for signal")

                pipeline_stats["final_signals"] += len(final_signals)
                # store final_signals
                for sig in final_signals:
                    try:
                        logger.info(f"[engine] storing signal: {sig.get('asset')} tf={sig.get('timeframe')} score={sig.get('score')}")
                        store_signal_compat(sig)
                        scored_signals_all.append(sig)
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
                                
                                async with get_session() as session:
                                    for trade in closed_trades:
                                        try:
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
                                                        msg = (
                                                            f"{emoji} Signal Outcome\n\n"
                                                            f"Asset: {trade.symbol}\n"
                                                            f"Direction: {trade.direction.upper()}\n"
                                                            f"Outcome: {trade.outcome}\n"
                                                            f"R-Multiple: {r_str}\n"
                                                            f"Entry: {trade.entry}\n"
                                                            f"Close: {getattr(trade, 'close_price', 'N/A')}\n\n"
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
                        
                        # Run notification in background (don't block main loop)
                        try:
                            import asyncio
                            asyncio.create_task(notify_users_about_outcomes())
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

        # ensure owners included
        for _oid in (OWNER_IDS or []):
            try:
                oid = int(_oid)
                if oid not in user_ids:
                    user_ids.append(oid)
            except Exception as e:
                logger.debug(f"[engine] Failed to parse user ID from OWNER_TELEGRAM_ID: {e}")
                pass

        async def deliver_all():
            dispatched_count = 0
            # session management adapted to your codebase
            try:
                from db.session import get_session
            except Exception:
                get_session = None

            for user_id in user_ids:
                try:
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
                        continue

                    user_signals = []
                    for sig in scored_signals_all:
                        if signals_sent_today + len(user_signals) >= daily_limit:
                            break
                        
                        # Validate signal freshness and price before delivery
                        try:
                            # Zero-stale-signal gate: check live price drift against entry zone
                            from engine.stale_signal_validator import validate_signal_freshness_sync
                            _sval_fresh, _sval_reason, _sval_price = validate_signal_freshness_sync(sig)
                            if not _sval_fresh:
                                logger.info(
                                    f"[engine] Stale signal dropped — {sig.get('asset')} "
                                    f"{sig.get('timeframe')}: {_sval_reason}"
                                )
                                continue
                        except Exception as _sval_err:
                            logger.debug(f"[engine] stale_signal_validator unavailable: {_sval_err}")

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
                        
                        try:
                            eligible = delivery_mgr.should_send_signal(user_tier, float(sig.get('score', 0)), user_id=user_id)
                            if eligible:
                                user_signals.append(sig)
                        except Exception as e:
                            logger.debug(f"[engine] Failed to check signal eligibility for user {user_id}: {e}")
                            pass

                    if not user_signals:
                        continue

                    if DRY_RUN:
                        for msg in user_signals:
                            print(f"[DRY RUN][{user_tier}] {msg}")
                    else:
                        try:
                            dispatch_signals(user_signals, user_id=user_id)
                            # Increment Redis counter
                            try:
                                new_count = signals_sent_today + len(user_signals)
                                state.set_sync(redis_key, str(new_count), ex=86400)
                            except Exception as e:
                                logger.debug(f"[engine] Failed to update signal count in Redis: {e}")
                                pass
                        except Exception as e:
                            logger.warning(f"[engine] Failed to dispatch signals: {e}")
                            logger.exception("dispatch_signals failed")
                    dispatched_count += 1
                except Exception:
                    logger.exception("deliver_all per-user failed")
            return dispatched_count

        try:
            dispatched = run_sync(deliver_all())
        except Exception:
            logger.exception("deliver_all failed")
            dispatched = 0

        # flush analytics periodically
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

        time.sleep(max(5, cycle_sleep_seconds))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main_loop(DRY_RUN=(_env_bool('DRY_RUN', True)))
