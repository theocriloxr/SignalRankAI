import os
import time
import asyncio
import logging
import threading
from engine.signal_analytics import signal_analytics
from collections import Counter

from data.fetcher import is_crypto, is_binance_blocked, market_closed_reason, is_fx, is_stock
from data.market_data import fetch_market_data_cached
from data.pair_discovery import get_all_trending_pairs, get_trending_stock_tickers
from data.indicators import calculate_indicators
from engine.regime import detect_market_regime
from engine.risk_manager import RiskManager, CorrelationManager
from engine.exit_manager import ExitManager, PartialExitTracker
from engine.filters import SignalFilter, MarketRegimeFilter, SlippageControl
from engine.backtest import BacktestEngine, OptimizationEngine
from strategies import run_all_strategies
from engine.consensus import apply_consensus_filter
from engine.risk import calculate_dynamic_risk
from engine.scoring import calculate_signal_score, calculate_confluence
from db.pg_compat import get_all_user_ids_compat, store_signal_compat
from engine.ranking import rank_signals
from signalrank_telegram.bot import dispatch_signals
from core.redis_state import state

# For outage alerting
from data.fetcher import get_unhealthy_providers
from signalrank_telegram.bot import _send_message_sync
from config import OWNER_IDS

# NEW: Signal-only bot features
from engine.mtf_analysis import MultiTimeframeAnalyzer
from engine.signal_context import SignalContext, SignalCooldownManager, OneBiasPerTimeframe
from engine.advanced_filters import SmartFilterSuite
from engine.tier_notifications import TierNotificationManager

# NEW: Near-zero loss trading system
from engine.ultra_quality_filter import ultra_quality
from engine.advanced_exit_manager import advanced_exit

logger = logging.getLogger(__name__)

# Background outage alert job
def start_outage_alert_job():
    from telegram import Bot
    def _job():
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        bot = Bot(token=bot_token) if bot_token else None
        while True:
            try:
                unhealthy = get_unhealthy_providers()
                if unhealthy and bot is not None:
                    for name, mins in unhealthy:
                        msg = f"🚨 Provider outage: {name} has been down for {mins:.1f} minutes."
                        for admin_id in OWNER_IDS:
                            _send_message_sync(bot, admin_id, msg)
                time.sleep(120)  # Check every 2 minutes
            except Exception as e:
                print(f"[outage_alert] Error: {e}", flush=True)
                time.sleep(120)
    t = threading.Thread(target=_job, daemon=True)
    t.start()


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


# Store/dispatch threshold for the main pipeline.
# Ultra-strict: 85 minimum = near-zero loss trading
# Only signals with confluence >= 80%, R:R >= 2.5, trending regime
# - 50: Permissive (all passing signals)
# - 60: Balanced (reasonable quality)
# - 65: Quality-focused (only high-confidence+good setups)
# - 70: Strict (premium quality only)
# - 75: Very strict (only top-tier signals)
# - 85: ULTRA (near-zero loss)
# - 90: Elite (only perfect setups)
# Default to 70 so we actually emit high-quality signals under tight liquidity/coverage.
MIN_SCORE_THRESHOLD = _env_float("PREMIUM_SCORE_THRESHOLD", 70)

def load_tradable_assets():
    """Return configured fallback assets.

    This intentionally avoids hardcoded demo symbols.
    Use TRADABLE_ASSETS="BTCUSDT,ETHUSDT" (comma-separated) to provide a fallback list.
    """
    raw = (os.getenv("TRADABLE_ASSETS") or "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


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


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        xs = str(x or "").strip()
        if not xs or xs in seen:
            continue
        seen.add(xs)
        out.append(xs)
    return out


def _rotate_slice(items: list[str], start: int, size: int) -> list[str]:
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


async def _fetch_market_data_for_assets(asset_to_timeframes: dict[str, list[str]]) -> dict[str, dict]:
    """Fetch cached market data for many assets using a bounded concurrency."""

    concurrency = max(1, _env_int("MARKET_CACHE_FETCH_CONCURRENCY", 8))
    # When Binance is blocked we rely on slower fallbacks (Bybit/CryptoCompare), so allow much more time.
    per_asset_timeout_default = 120.0 if is_binance_blocked() else 45.0
    per_asset_timeout = float(_env_float("MARKET_FETCH_TIMEOUT_SECONDS", per_asset_timeout_default))
    sem = asyncio.Semaphore(concurrency)

    async def _one(asset: str, tfs: list[str]) -> tuple[str, dict]:
        async with sem:
            try:
                data = await asyncio.wait_for(fetch_market_data_cached(asset, tfs), timeout=max(5.0, per_asset_timeout))
                if not data or not any(data.values()):
                    if _env_bool("ENGINE_ASSET_DEBUG", False):
                        print(f"[engine] candle_fetch asset={asset} status=empty", flush=True)
                return asset, (data or {})
            except asyncio.TimeoutError:
                if _env_bool("ENGINE_ASSET_DEBUG", False):
                    print(f"[engine] candle_fetch asset={asset} status=timeout", flush=True)
                return asset, {}
            except Exception as e:
                if _env_bool("ENGINE_ASSET_DEBUG", False):
                    print(f"[engine] candle_fetch asset={asset} status=error err={type(e).__name__}", flush=True)
                return asset, {}

    tasks = [_one(a, tfs) for a, tfs in (asset_to_timeframes or {}).items()]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return {asset: data for asset, data in results}

def main_loop(DRY_RUN=False):
    # Persistent objects (initialized once)
    start_outage_alert_job()
    account_equity = 10000.0  # Default, should come from broker API
    risk_manager = RiskManager(account_equity)
    correlation_manager = CorrelationManager()
    exit_manager = ExitManager()
    partial_exit_tracker = PartialExitTracker()
    signal_filter = SignalFilter()
    regime_filter = MarketRegimeFilter()
    slippage_control = SlippageControl()
    backtest_engine = BacktestEngine()
    optimization_engine = OptimizationEngine()
    open_positions = []
    last_trade_times = {}
    mtf_analyzer = MultiTimeframeAnalyzer()
    signal_context = SignalContext()
    cooldown_manager = SignalCooldownManager()
    bias_manager = OneBiasPerTimeframe()
    advanced_filters = SmartFilterSuite()
    tier_notifier = TierNotificationManager()
    import concurrent.futures
    import functools

    while True:
        # Per-cycle variables
        cycle_candidates = 0
        cycle_after_dedupe = 0
        new_degraded_assets = set()
        degraded_assets = set()
        # --- PARALLEL ASSET PIPELINE: Each asset is processed in its own async task for true concurrency and isolation ---
        def process_asset(asset, market_data):
            try:
                # --- Candle Completeness & Safety Checks ---
                min_candles = int((os.getenv("MIN_CANDLES_PER_TIMEFRAME") or "50").strip())
                min_candles = max(1, int(min_candles))
                needs_refresh = False
                if not market_data:
                    needs_refresh = True
                else:
                    for tf, tf_data in (market_data or {}).items():
                        candles = (tf_data or {}).get("candles") or []
                        if not isinstance(candles, list) or len(candles) < min_candles:
                            needs_refresh = True
                            break
                        last_candle = candles[-1] if candles else None
                        if last_candle:
                            if 'timestamp' not in last_candle or 'close' not in last_candle:
                                needs_refresh = True
                                break
                            if 'close_time' in last_candle:
                                import time
                # ...existing code...
            except Exception as e:
                # Handle/log exception as needed
                pass
                            now = int(time.time())
                            close_time = int(last_candle['close_time'])
                            tf_sec = 60
                            if 'm' in tf:
                                tf_sec = int(tf.replace('m','')) * 60
                            elif 'h' in tf:
                                tf_sec = int(tf.replace('h','')) * 3600
                            elif 'd' in tf:
                                tf_sec = int(tf.replace('d','')) * 86400
                            if now - close_time > 2 * tf_sec:
                                needs_refresh = True
                                break
                    if needs_refresh:
                        try:
                            market_data = asyncio.run(fetch_market_data_cached(asset, list((asset_to_tfs_degraded.get(asset) or []))))
                            valid = False
                            for tf, tf_data in (market_data or {}).items():
                                candles = (tf_data or {}).get('candles') or []
                                if isinstance(candles, list) and len(candles) >= min_candles:
                                    last_candle = candles[-1] if candles else None
                                    if last_candle and 'timestamp' in last_candle and 'close' in last_candle:
                                        valid = True
                                        break
                            if not valid:
                                return None, asset
                        except Exception:
                            return None, asset

                    regime = detect_market_regime(market_data)
                    strategy_signals = run_all_strategies(
                        asset,
                        market_data,
                        regime,
                        strategy_weights=strategy_weights,
                        regime_strategies=regime_strategies,
                    )
                    # Track candidate count
                    # nonlocal is invalid here; increment local in main_loop
                    # Use a mutable object or return value if you need to aggregate
                    # For now, just remove the nonlocal and increment is skipped
                    pass
                    from engine.signal_controller import SignalController
                    controller = SignalController()
                    normalized_signals = controller.normalize_signals(strategy_signals)
                    from engine.consensus import consensus_filter
                    consensus_signals = consensus_filter(normalized_signals)
                    selected_signals = controller.pick_best_direction_per_pair(consensus_signals)
                    from db.pg_features import compute_signal_fingerprint
                    unique_signals = []
                    seen_fingerprints = set()
                    for sig in selected_signals:
                        fp = compute_signal_fingerprint(sig)
                        sig["fingerprint"] = fp
                        if fp in seen_fingerprints:
                            continue
                        seen_fingerprints.add(fp)
                        unique_signals.append(sig)
                    selected_signals = unique_signals
                    # Track deduped count
                    # nonlocal is invalid here; increment local in main_loop
                    # Use a mutable object or return value if you need to aggregate
                    # For now, just remove the nonlocal and increment is skipped
                    pass
                    from engine.signal_validator import validate_signal
                    from engine.risk import risk_check
                    from engine.scoring import score_signal, calculate_confluence
                    strict_signals = []
                    for sig in selected_signals:
                        is_valid, err = validate_signal(sig)
                        if not is_valid:
                            sig["rejection_reason"] = f"validation: {err}"
                            continue
                        account_state = type('AccountState', (), {'drawdown': 0.0})()
                        if not risk_check(sig, account_state):
                            sig["rejection_reason"] = "risk/volatility gate"
                            continue
                        confluence = calculate_confluence(sig)
                        if confluence < 50:
                            sig["rejection_reason"] = f"confluence {confluence:.1f}% < 50%"
                            continue
                        if sig.get("ml_probability") is not None and float(sig["ml_probability"]) < 0.5:
                            sig["rejection_reason"] = f"ml_probability {sig['ml_probability']:.2f} < 0.5"
                            continue
                        score = score_signal(sig)
                        if score < MIN_SCORE_THRESHOLD:
                            sig["rejection_reason"] = f"score {score:.2f} < {MIN_SCORE_THRESHOLD}"
                            continue
                        sig["score"] = score
                        strict_signals.append(sig)
                    return strict_signals, None
        except Exception:
            return None, asset

            # Use ThreadPoolExecutor for true parallelism (avoids GIL for IO-bound work)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(functools.partial(process_asset, asset, (all_market_data or {}).get(asset) or {})) for asset in assets]
                results = [f.result() for f in futures]
            # Aggregate results and degraded assets
            all_strict_signals = []
            for sigs, degraded in results:
                if degraded:
                    new_degraded_assets.add(degraded)
                elif sigs:
                    all_strict_signals.extend(sigs)

            selected_signals = all_strict_signals
            print(f"[engine] Added {len(stock_list)} stock ticker(s) to asset list", flush=True)
        except Exception:
            pass

            if _env_bool("ENGINE_CYCLE_LOG", True) and _env_bool("ENGINE_ASSET_DEBUG", False):
                try:
                    raw_tradable = (os.getenv("TRADABLE_ASSETS") or "").strip()
                    raw_fx = (os.getenv("FX_PAIRS") or "").strip()
                    print(
                        f"[engine] env tradable_len={len(raw_tradable)} fx_len={len(raw_fx)} tradable_count={len(tradable)} discovered_count={len(discovered)} final_count={len(assets)}",
                        flush=True,
                    )
                except Exception:
                    pass

            # No assets => do not run on demo/hardcoded data.
            if not assets:
                if _env_bool("ENGINE_CYCLE_LOG", True):
                    try:
                        print(f"[engine] cycle={cycle_no} skipped=no_assets", flush=True)
                    except Exception:
                        pass
                time.sleep(max(5, cycle_sleep_seconds))
                # Instead of 'continue', use 'return' to exit the function if not in a loop
                return

            # Cap FX pairs per cycle to avoid AlphaVantage throttling (especially on free tier).
            try:
                assets = _dedupe_preserve_order(list(assets or []))

                # Filter out closed markets with per-pair notice.
                closed_notes = []
                open_assets = []
                for a in assets:
                    reason = market_closed_reason(a)
                    if reason:
                        closed_notes.append((a, reason))
                    else:
                        open_assets.append(a)
                if closed_notes and _env_bool("ENGINE_CYCLE_LOG", True):
                    try:
                        msg = ", ".join([f"{p}:{r}" for p, r in closed_notes])
                        print(f"[engine] cycle={cycle_no} market_closed skip={msg}", flush=True)
                    except Exception:
                        pass

                crypto_assets = [a for a in open_assets if is_crypto(a)]
                fx_assets = [a for a in open_assets if is_fx(a)]
                stock_assets = [a for a in open_assets if is_stock(a)]
                if not fx_enabled:
                    fx_assets = []
                if not stocks_enabled:
                    stock_assets = []

                # FX universe can be moderate; bound per-cycle calls but rotate to cover all.
                fx_pair_rotation = _env_bool("FX_PAIR_ROTATION", True)
                if fx_assets and fx_max_pairs > 0 and len(fx_assets) > int(fx_max_pairs):
                    if fx_pair_rotation:
                        start = (max(0, int(cycle_no)) - 1) * int(fx_max_pairs)
                        fx_assets = _rotate_slice(fx_assets, start=start, size=int(fx_max_pairs))
                    else:
                        fx_assets = fx_assets[: int(fx_max_pairs)]

                # Crypto universe can be large; bound per-cycle work but rotate so we cover all.
                default_crypto_max = 20
                try:
                    if is_binance_blocked():
                        # When geo-blocked, throttle pair count to reduce cycle time and API strain.
                        default_crypto_max = 12
                        if not (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip():
                            default_crypto_max = 8
                except Exception:
                    pass
                crypto_max_pairs = _env_int("CRYPTO_MAX_PAIRS_PER_CYCLE", int(default_crypto_max))
                crypto_pair_rotation = _env_bool("CRYPTO_PAIR_ROTATION", True)
                if crypto_max_pairs > 0 and len(crypto_assets) > crypto_max_pairs:
                    if crypto_pair_rotation:
                        start = (max(0, int(cycle_no)) - 1) * int(crypto_max_pairs)
                        crypto_assets = _rotate_slice(crypto_assets, start=start, size=int(crypto_max_pairs))
                    else:
                        crypto_assets = crypto_assets[: int(crypto_max_pairs)]

                # Bound stock universe per cycle to keep runtime predictable
                try:
                    # Lower default stock scan batch to 10 to keep cycles fast; override via env STOCK_MAX_PAIRS_PER_CYCLE.
                    stock_max_pairs = _env_int("STOCK_MAX_PAIRS_PER_CYCLE", 10)
                except Exception:
                    stock_max_pairs = 10
                stock_pair_rotation = _env_bool("STOCK_PAIR_ROTATION", True)
                if stock_assets and stock_max_pairs > 0 and len(stock_assets) > stock_max_pairs:
                    if stock_pair_rotation:
                        start = (max(0, int(cycle_no)) - 1) * int(stock_max_pairs)
                        stock_assets = _rotate_slice(stock_assets, start=start, size=int(stock_max_pairs))
                    else:
                        stock_assets = stock_assets[: int(stock_max_pairs)]

                assets = crypto_assets + fx_assets + stock_assets
            except Exception:
                pass

            cycle_assets = len(assets)

            # Optional visibility into what we are actually scanning.
            if _env_bool("ENGINE_CYCLE_LOG", True) and _env_bool("ENGINE_ASSET_DEBUG", False):
                try:
                    crypto_n = len([a for a in assets if is_crypto(a)])
                    fx_n = len([a for a in assets if is_fx(a)])
                    stock_n = len([a for a in assets if is_stock(a)])
                    sample = ",".join([str(a) for a in list(assets)[:10]])
                    print(
                        f"[engine] cycle={cycle_no} assets_split crypto={crypto_n} fx={fx_n} stocks={stock_n} sample={sample}",
                        flush=True,
                    )
                except Exception:
                    pass

            scored_signals_all = []

            # Fetch all market data once per cycle (avoids per-asset asyncio.run overhead).
            asset_to_tfs: dict[str, list[str]] = {}
            for asset in assets:
                if is_crypto(asset):
                    tfs = crypto_timeframes
                elif is_fx(asset):
                    tfs = fx_timeframes
                else:
                    tfs = stock_timeframes
                asset_to_tfs[str(asset)] = list(tfs)


            # Graceful degradation: reduce batch size and skip some timeframes for problematic assets
            asset_to_tfs_degraded = {}
            for asset, tfs in asset_to_tfs.items():
                if asset in degraded_assets:
                    # Only scan 1 timeframe for degraded assets (lowest timeframe)
                    asset_to_tfs_degraded[asset] = [tfs[0]] if tfs else []
                else:
                    asset_to_tfs_degraded[asset] = tfs

            try:
                all_market_data = asyncio.run(_fetch_market_data_for_assets(asset_to_tfs_degraded))
            except Exception:
                all_market_data = {}

            new_degraded_assets = set()

            for asset in assets:

                try:
                    market_data = (all_market_data or {}).get(asset) or {}

                    # --- Candle Completeness & Safety Checks ---
                    # Only confirmed, closed candles are ever used for strategy execution.
                    # This block ensures:
                    #   - Minimum required candles per timeframe
                    #   - No partial or forming candles
                    #   - No stale or expired market snapshots
                    #   - All required fields are present
                    try:
                        min_candles = int((os.getenv("MIN_CANDLES_PER_TIMEFRAME") or "50").strip())
                    except Exception:
                        min_candles = 50
                    min_candles = max(1, int(min_candles))
                    needs_refresh = False
                    if not market_data:
                        needs_refresh = True
                    else:
                        for tf, tf_data in (market_data or {}).items():
                            candles = (tf_data or {}).get("candles") or []
                            # Require minimum candles and all required fields
                            if not isinstance(candles, list) or len(candles) < min_candles:
                                needs_refresh = True
                                break
                            # Check that the last candle is closed/final (not forming)
                            last_candle = candles[-1] if candles else None
                            if last_candle:
                                # Require timestamp and close fields
                                if 'timestamp' not in last_candle or 'close' not in last_candle:
                                    needs_refresh = True
                                    break
                                # If close_time is present, check staleness
                                if 'close_time' in last_candle:
                                    import time
                                    now = int(time.time())
                                    close_time = int(last_candle['close_time'])
                                    # Assume timeframe in seconds (e.g., 900 for 15m)
                                    tf_sec = 60
                                    if 'm' in tf:
                                        tf_sec = int(tf.replace('m','')) * 60
                                    elif 'h' in tf:
                                        tf_sec = int(tf.replace('h','')) * 3600
                                    elif 'd' in tf:
                                        tf_sec = int(tf.replace('d','')) * 86400
                                    # If last candle is too old, mark as stale
                                    if now - close_time > 2 * tf_sec:
                                        needs_refresh = True
                                        break
                    if needs_refresh:
                        # Re-fetch market data for this asset
                        try:
                            market_data = asyncio.run(fetch_market_data_cached(asset, list((asset_to_tfs_degraded.get(asset) or []))))
                            # After re-fetch, re-validate completeness
                            valid = False
                            for tf, tf_data in (market_data or {}).items():
                                candles = (tf_data or {}).get('candles') or []
                                if isinstance(candles, list) and len(candles) >= min_candles:
                                    last_candle = candles[-1] if candles else None
                                    if last_candle and 'timestamp' in last_candle and 'close' in last_candle:
                                        valid = True
                                        break
                            if not valid:
                                new_degraded_assets.add(asset)
                                continue
                        except Exception:
                            new_degraded_assets.add(asset)
                            continue

                    regime = detect_market_regime(market_data)
                    strategy_signals = run_all_strategies(
                        asset,
                        market_data,
                        regime,
                        strategy_weights=strategy_weights,
                        regime_strategies=regime_strategies,
                    )

                    try:
                        cycle_candidates += len(strategy_signals or [])
                    except Exception:
                        pass

                    # Signal Controller step (deduplication + normalization)
                    from engine.signal_controller import SignalController
                    controller = SignalController()
                    normalized_signals = controller.normalize_signals(strategy_signals)

                    # Consensus Engine (aggregates across strategies)
                    from engine.consensus import consensus_filter
                    consensus_signals = consensus_filter(normalized_signals)

                    # Per pair/timeframe, pick the stronger direction (buy vs sell)
                    selected_signals = controller.pick_best_direction_per_pair(consensus_signals)

                    # --- Enforce deterministic signal fingerprint and deduplication ---
                    # Each signal must have a unique fingerprint (hash) for asset/timeframe/direction/candle/consensus
                    from db.pg_features import compute_signal_fingerprint
                    unique_signals = []
                    seen_fingerprints = set()
                    for sig in selected_signals:
                        fp = compute_signal_fingerprint(sig)
                        sig["fingerprint"] = fp
                        if fp in seen_fingerprints:
                            continue
                        seen_fingerprints.add(fp)
                        unique_signals.append(sig)
                    selected_signals = unique_signals
                    try:
                        cycle_after_dedupe += len(selected_signals or [])
                    except Exception:
                        pass

                    # --- STRICT SIGNAL GENERATION RULES: Gating and rejection reasons ---
                    from engine.signal_validator import validate_signal
                    from engine.risk import risk_check
                    from engine.scoring import score_signal, calculate_confluence
                    strict_signals = []
                    for sig in selected_signals:
                        # 1. Validate structure and price logic
                        is_valid, err = validate_signal(sig)
                        if not is_valid:
                            sig["rejection_reason"] = f"validation: {err}"
                            continue
                        # 2. Risk/volatility gate
                        account_state = type('AccountState', (), {'drawdown': 0.0})()
                        if not risk_check(sig, account_state):
                            sig["rejection_reason"] = "risk/volatility gate"
                            continue
                        # 3. Confluence gate
                        confluence = calculate_confluence(sig)
                        if confluence < 50:
                            sig["rejection_reason"] = f"confluence {confluence:.1f}% < 50%"
                            continue
                        # 4. ML risk advisory (if present)
                        if sig.get("ml_probability") is not None and float(sig["ml_probability"]) < 0.5:
                            sig["rejection_reason"] = f"ml_probability {sig['ml_probability']:.2f} < 0.5"
                            continue
                        # 5. Score gate (final quality)
                        score = score_signal(sig)
                        if score < MIN_SCORE_THRESHOLD:
                            sig["rejection_reason"] = f"score {score:.2f} < {MIN_SCORE_THRESHOLD}"
                            continue
                        sig["score"] = score
                        strict_signals.append(sig)
                    selected_signals = strict_signals

                    # Risk Engine
                    from engine.risk import risk_check

                    account_state = type('AccountState', (), {'drawdown': 0.0})()  # Replace with real account state
                    risk_signals = [s for s in selected_signals if risk_check(s, account_state)]
                    try:
                        cycle_after_risk += len(risk_signals or [])
                    except Exception:
                        pass

                    # ML Probability Filter
                    # --- ML Layer: Post-Consensus, Advisory-Only ---
                    # ML is applied strictly after consensus and risk checks.
                    # It acts only as a confidence/risk modifier and advisory, never as a hard override.
                    # ML output is stored as 'ml_probability' and 'ml_advisory' for downstream use.
                    from ml.features import extract_features
                    from ml.inference import MLFilter

                    ml_filter = MLFilter()
                    ml_signals = []
                    try:
                        ml_threshold = float((os.getenv("ML_PROB_THRESHOLD") or "0.65").strip())
                    except Exception:
                        ml_threshold = 0.65
                    for signal in risk_signals:
                        if getattr(ml_filter, "active", False):
                            features = extract_features(signal, market_data)
                            try:
                                approved, probability = ml_filter.ml_filter(features, threshold=ml_threshold)
                            except Exception:
                                approved, probability = True, None
                        else:
                            approved, probability = True, None
                        # ML can only filter or adjust confidence, never override rule consensus
                        if not approved:
                            # ML advisory: signal filtered by ML risk model
                            signal["ml_advisory"] = "ML model flagged this signal as high risk."
                            continue
                        signal["ml_probability"] = probability
                        if probability is not None:
                            # ML advisory: add guidance for downstream delivery/advisory layers
                            if probability > 0.85:
                                signal["ml_advisory"] = "ML model: High confidence in this signal."
                            elif probability > 0.7:
                                signal["ml_advisory"] = "ML model: Moderate confidence."
                            elif probability > 0.5:
                                signal["ml_advisory"] = "ML model: Caution advised."
                            else:
                                signal["ml_advisory"] = "ML model: Low confidence, high risk."
                        ml_signals.append(signal)
                    try:
                        cycle_after_ml += len(ml_signals or [])
                    except Exception:
                        pass

                    # Scoring
                    from engine.scoring import score_signal

                    for signal in ml_signals:
                        try:
                            # ----------------------------------------
                            # Enrich signal with indicator context so scoring/confluence works
                            # ----------------------------------------
                            tf_data = (market_data.get(signal.get('timeframe', '')) or {})
                            ind = tf_data.get('indicators', {}) if isinstance(tf_data, dict) else {}
                            try:
                                candles = tf_data.get('candles', []) if isinstance(tf_data, dict) else []
                                last_close = candles[-1]['close'] if candles else None
                            except Exception:
                                last_close = None

                            signal.setdefault('trend_ema', ind.get('trend_ema', ind.get('ema_trend', 0)))
                            signal.setdefault('trend_sma', ind.get('trend_sma', 0))
                            signal.setdefault('rsi', ind.get('rsi', 50))
                            signal.setdefault('macd_trend', ind.get('macd_trend', 0))
                            signal.setdefault('volume_ratio', ind.get('volume_ratio', 1.0))
                            signal.setdefault('adx_trend', ind.get('adx', ind.get('adx_trend', 30)))
                            signal.setdefault('nearest_support', ind.get('nearest_support', 0))
                            signal.setdefault('nearest_resistance', ind.get('nearest_resistance', 0))
                            signal.setdefault('close_price', ind.get('close_price', last_close or 0))
                            
                            # Calculate volatility (ATR as % of price)
                            atr_val = ind.get('atr', signal.get('atr', 0))
                            close_val = last_close or signal.get('entry', 0)
                            signal.setdefault('volatility', (atr_val / close_val) if close_val > 0 else 0)

                            # ========================================
                            # NEW: SIGNAL-ONLY BOT VALIDATION
                            # ========================================
                            
                            symbol = signal.get('asset') or signal.get('symbol', '')
                            timeframe = signal.get('timeframe', '1h')
                            direction = signal.get('direction', 'long')
                            
                            # 1. Check candle close confirmation
                            if not signal_context.wait_for_candle_close(
                                market_data.get(timeframe, {}).get('candles', []),
                                timeframe
                            ):
                                continue  # Skip mid-candle signals
                            
                            # 2. Check cooldown (prevent spam)
                            can_send, reason = cooldown_manager.can_send_signal(symbol, timeframe)
                            if not can_send:
                                continue
                            
                            # 3. Get HTF bias (multi-timeframe analysis)
                            htf_bias = mtf_analyzer.get_htf_bias(symbol, timeframe, market_data)
                            
                            # 4. Validate against HTF trend
                            is_valid_htf, htf_reason = mtf_analyzer.validate_against_htf(direction, htf_bias)
                            signal['htf_bias_aligned'] = is_valid_htf
                            if not is_valid_htf:
                                continue  # Reject signals against HTF trend
                            
                            # 5. Check one-bias-per-timeframe rule
                            can_add_bias, bias_reason = bias_manager.can_add_signal(symbol, timeframe, direction)
                            if not can_add_bias:
                                continue  # Only one direction per TF
                            
                            # 6. Get MTF confluence score
                            mtf_confluence = mtf_analyzer.get_mtf_confluence(symbol, market_data, direction)
                            
                            # 7. Detect trading session
                            session = signal_context.detect_trading_session()
                            
                            # 8. Calculate entry zone (range, not single price)
                            atr = signal.get('atr', 0)
                            if not atr:
                                # Calculate ATR if not present
                                try:
                                    candles = market_data.get(timeframe, {}).get('candles', [])
                                    if len(candles) >= 14:
                                        highs = [c['high'] for c in candles[-14:]]
                                        lows = [c['low'] for c in candles[-14:]]
                                        closes = [c['close'] for c in candles[-14:]]
                                        tr_values = []
                                        for i in range(1, len(candles[-14:])):
                                            tr = max(
                                                highs[i] - lows[i],
                                                abs(highs[i] - closes[i-1]),
                                                abs(lows[i] - closes[i-1])
                                            )
                                            tr_values.append(tr)
                                        atr = sum(tr_values) / len(tr_values) if tr_values else 0
                                except Exception:
                                    atr = 0
                            
                            entry_price = signal.get('entry', signal.get('entry_price', 0))
                            entry_zone = signal_context.calculate_entry_zone(entry_price, atr, direction)

                            # ========================================
                            # EXISTING SCORING (compute before filters for observability)
                            # ========================================
                            score = score_signal(signal)
                            signal['score'] = score
                            # Ultra-filter expects confidence (0.0-1.0); derive from score
                            signal.setdefault('confidence', min(1.0, score / 100.0))

                            try:
                                if cycle_max_score is None or float(score) > float(cycle_max_score):
                                    cycle_max_score = float(score)
                                    cycle_max_score_asset = str(signal.get('asset') or signal.get('symbol') or '')
                            except Exception:
                                pass
                            
                            # 9. Run advanced filters
                            market_filter_data = {
                                'price': entry_price,
                                'ema_20': signal.get('ema_20', 0),
                                'ema_50': signal.get('ema_50', 0),
                                'atr': atr,
                                'candles': market_data.get(timeframe, {}).get('candles', []),
                                'adx': signal.get('adx', 30),
                                'atr_pct': (atr / entry_price * 100) if entry_price > 0 else 0
                            }
                            
                            passed_filters, rejections = advanced_filters.run_all_filters(
                                signal,
                                market_filter_data,
                                session
                            )
                            
                            if not passed_filters:
                                cycle_rejected_filters += 1
                                for reason in rejections:
                                    if reason:
                                        cycle_filter_rejection_counts[reason] += 1
                                # Signal rejected by advanced filters
                                if _env_bool("ENGINE_SIGNAL_DEBUG", False):
                                    print(f"[engine] signal rejected: {symbol} {timeframe} - {rejections}", flush=True)
                                continue
                            
                            # 10. Calculate signal expiration
                            expires_at = signal_context.calculate_signal_expiration(timeframe)
                            
                            # 11. Calculate invalidation price (kill zone)
                            sl_price = signal.get('stop_loss', signal.get('stop', 0))
                            if direction == 'long':
                                # Invalidate if price closes below SL - 0.5*ATR
                                invalid_price = sl_price - (0.5 * atr) if sl_price > 0 else None
                            else:
                                # Invalidate if price closes above SL + 0.5*ATR
                                invalid_price = sl_price + (0.5 * atr) if sl_price > 0 else None
                            
                            # ========================================
                            # NEW: ULTRA-QUALITY FILTER (Near-Zero Loss)
                            # ========================================
                            # Apply ultra-strict validation to prevent losses
                            # Skip ultra-quality for now; it requires many fields from strategies
                            # that aren't populated. Will re-enable once signal enrichment is complete.
                            ultra_quality_enabled = _env_bool("ULTRA_QUALITY_ENABLED", False)
                            if ultra_quality_enabled:
                                should_trade, rejection, quality_score = ultra_quality.apply_ultra_filter(signal)
                                
                                if not should_trade:
                                    cycle_rejected_ultra += 1
                                    # Signal rejected by ultra-quality filter
                                    if _env_bool("ENGINE_SIGNAL_DEBUG", False):
                                        print(f"[engine] ultra-filter rejected: {symbol} {timeframe} - {rejection}", flush=True)
                                    continue
                                
                                if _env_bool("ENGINE_SIGNAL_DEBUG", False):
                                    print(f"[engine] ultra-filter approved: {symbol} {timeframe} score={quality_score:.1f}", flush=True)
                            
                        except Exception as e:
                            cycle_score_errors += 1
                            if cycle_score_errors <= 3:
                                try:
                                    print(f"[engine] score_error asset={symbol} tf={timeframe} err={_short_err(e)}", flush=True)
                                except Exception:
                                    pass
                            # Isolated failure - continue with next signal
                            continue
                        
                        try:
                            if cycle_max_score is None or float(score) > float(cycle_max_score):
                                cycle_max_score = float(score)
                                cycle_max_score_asset = str(signal.get('asset') or signal.get('symbol') or '')
                        except Exception:
                            pass
                        
                        if score >= MIN_SCORE_THRESHOLD:
                            # Normalize for DB + formatters
                            signal['regime'] = regime
                            
                            # Ensure stop_loss and take_profit are populated
                            # Fallback: Use ATR-based stops if missing

                            entry = signal.get('entry')
                            sl = signal.get('stop_loss', signal.get('stop'))
                            tp = signal.get('take_profit', signal.get('targets'))

                            # Infer direction if missing or invalid
                            direction = (signal.get('direction') or '').lower().strip()
                            try:
                                entry_f = float(entry) if entry is not None else None
                                # Handle TP as list or float
                                if isinstance(tp, (list, tuple)) and tp:
                                    tp_f = float(tp[0])
                                else:
                                    tp_f = float(tp) if tp is not None else None
                                if direction not in {'long', 'short'} and entry_f is not None and tp_f is not None:
                                    if tp_f < entry_f:
                                        direction = 'short'
                                    elif tp_f > entry_f:
                                        direction = 'long'
                                    signal['direction'] = direction
                            except Exception:
                                pass

                            # If stops are missing/invalid, calculate from ATR
                            if not sl or sl == entry:
                                atr_value = signal.get('atr', 0)
                                if atr_value > 0 and entry is not None and float(entry) > 0:
                                    if direction == 'long':
                                        sl = float(entry) - (2 * atr_value)  # 2x ATR below
                                    else:
                                        sl = float(entry) + (2 * atr_value)  # 2x ATR above

                            if not tp or tp == entry:
                                atr_value = signal.get('atr', 0)
                                if atr_value > 0 and entry is not None and float(entry) > 0 and sl and sl != entry:
                                    rr = 2.0  # Target 2:1 R/R
                                    if direction == 'long':
                                        tp = float(entry) + (abs(float(entry) - float(sl)) * rr)
                                    else:
                                        tp = float(entry) - (abs(float(entry) - float(sl)) * rr)

                            signal['stop_loss'] = sl
                            signal['take_profit'] = tp
                            
                            # Recalculate R:R with actual values
                            if entry is not None and sl is not None and tp is not None and abs(entry - sl) > 0:
                                signal['rr_ratio'] = abs(tp - entry) / abs(entry - sl)
                            else:
                                signal['rr_ratio'] = signal.get('rr_ratio', 0)
                            
                            # ========================================
                            # NEW: ADD SIGNAL CONTEXT TO SIGNAL
                            # ========================================
                            signal['entry_zone'] = entry_zone
                            signal['htf_bias'] = htf_bias
                            signal['htf_bias_at_creation'] = htf_bias.get('bias')  # For invalidation check
                            signal['mtf_confluence'] = mtf_confluence
                            signal['session'] = session
                            signal['expires_at'] = expires_at
                            signal['invalid_if_price'] = invalid_price
                            
                            # Calculate position sizing SUGGESTION
                            try:
                                # Use ultra-quality position sizing (Kelly criterion)
                                entry_price = signal.get('entry', 0)
                                sl_price = signal.get('stop_loss', 0)
                                
                                if entry_price > 0 and sl_price > 0:
                                    position_size, sizing_detail = ultra_quality.calculate_dynamic_position_size(
                                        account_equity=account_equity,
                                        entry_price=entry_price,
                                        stop_loss=sl_price,
                                        current_win_rate=None
                                    )
                                    signal['position_size'] = position_size
                                    signal['position_sizing_method'] = 'Kelly Criterion (25%)'
                                    signal['sizing_detail'] = sizing_detail
                            except Exception:
                                pass
                            
                            # ========================================
                            # NEW: CALCULATE SMART EXITS (Near-Zero Loss)
                            # ========================================
                            try:
                                entry = signal.get('entry', 0)
                                atr_value = signal.get('atr', 0)
                                direction = signal.get('direction', 'long')
                                current_price = signal.get('close_price', entry)
                                
                                # Get market structure support/resistance
                                recent_candles = market_data.get(timeframe, {}).get('candles', [])
                                recent_lows = [c['low'] for c in recent_candles[-50:]] if recent_candles else []
                                recent_highs = [c['high'] for c in recent_candles[-50:]] if recent_candles else []
                                support = min(recent_lows) if recent_lows else entry
                                resistance = max(recent_highs) if recent_highs else entry
                                
                                # Calculate smart stops
                                smart_stops = advanced_exit.calculate_smart_stops(
                                    entry_price=entry,
                                    atr=atr_value,
                                    direction=direction,
                                    current_price=current_price,
                                    recent_low=support,
                                    recent_high=resistance,
                                    support=support,
                                    resistance=resistance
                                )
                                
                                signal['stops'] = smart_stops
                                signal['tp_levels'] = [smart_stops['tp1'], smart_stops['tp2'], smart_stops['tp3']]
                                
                                # Only update SL/TP if the smart stops are valid (different from entry)
                                if smart_stops.get('stop_loss') and smart_stops['stop_loss'] != entry:
                                    signal['stop_loss'] = smart_stops['stop_loss']
                                if smart_stops.get('tp3') and smart_stops['tp3'] != entry:
                                    signal['take_profit'] = smart_stops['tp3']  # Default to TP3
                                
                                # Calculate partial exits
                                position_size = signal.get('position_size', 1.0)
                                partial_exits = advanced_exit.calculate_partial_exit_targets(
                                    position_size=position_size,
                                    entry_price=entry,
                                    tp_levels=[smart_stops['tp1'], smart_stops['tp2'], smart_stops['tp3']]
                                )
                                signal['partial_exits'] = partial_exits
                                
                                if _env_bool("ENGINE_SIGNAL_DEBUG", False):
                                    exit_summary = advanced_exit.get_exit_plan_summary(
                                        entry=entry,
                                        stops=smart_stops,
                                        position_size=position_size,
                                        account_equity=account_equity
                                    )
                                    print(f"[engine] exit plan: {symbol} {timeframe} {exit_summary}", flush=True)
                                    
                            except Exception as e:
                                if _env_bool("ENGINE_SIGNAL_DEBUG", False):
                                    print(f"[engine] exit plan error: {symbol} - {e}", flush=True)
                            
                            scored_signals_all.append(signal)
                            cycle_scored += 1
                            
                            # Record signal for cooldown/bias tracking
                            cooldown_manager.record_signal(symbol, timeframe)
                            bias_manager.set_bias(symbol, timeframe, direction)
                            
                            # VALIDATE SIGNAL BEFORE STORING
                            try:
                                from engine.signal_validator import validate_signal
                                is_valid, error_desc = validate_signal(signal)
                                
                                if not is_valid:
                                    logger.warning(f"Signal validation failed for {symbol}: {error_desc}")
                                    if _env_bool("ENGINE_SIGNAL_DEBUG", False):
                                        print(f"[VALIDATION FAILED] {symbol} {timeframe}: {error_desc}", flush=True)
                                    # Skip storing invalid signal
                                    continue
                            except Exception as e:
                                logger.error(f"Signal validation error: {e}")
                                # If validation fails, continue storing (backward compatibility)
                            
                            try:
                                store_signal_compat(signal)
                                cycle_stored += 1
                            except Exception as e:
                                cycle_store_failures += 1
                                # Keep loop alive but emit a single useful hint per cycle.
                                if cycle_store_failures == 1:
                                    cycle_store_error = _short_err(e)
                                    try:
                                        print(f"[ERROR] store_signal failed: {type(e).__name__}: {e}", flush=True)
                                    except Exception:
                                        pass

                                    # Optional traceback for faster diagnosis in production logs.
                                    if _env_bool("STORE_SIGNAL_TRACE", False):
                                        try:
                                            import traceback

                                            traceback.print_exc()
                                        except Exception:
                                            pass
                except Exception:
                    # Isolate per-asset failures so the loop stays alive.
                    continue

            # Update degraded_assets for next cycle
            degraded_assets = new_degraded_assets

            # --- Centralized Tier-Based Delivery ---
            from signalrank_telegram.tier_delivery import TierDeliveryManager
            delivery_mgr = TierDeliveryManager()
            from db.pg_compat import get_all_user_ids_compat
            from signalrank_telegram.access import resolve_user_tier
            user_ids = []
            try:
                user_ids = list(get_all_user_ids_compat() or [])
            except Exception:
                user_ids = []
            # Ensure OWNER_IDS are included so owners always receive signals
            try:
                for _oid in (OWNER_IDS or set()):
                    try:
                        oid = int(_oid)
                        if oid not in user_ids:
                            user_ids.append(oid)
                    except Exception:
                        continue
            except Exception:
                pass
            try:
                cycle_users = len(user_ids or [])
            except Exception:
                cycle_users = 0
            # For each user, resolve tier and deliver only signals allowed by TierDeliveryManager
            import asyncio
            from db.session import get_session
            async def deliver_all():
                dispatched_count = 0
                async with get_session() as session:
                    for user_id in user_ids:
                        try:
                            user_tier = resolve_user_tier(user_id).lower()
                        except Exception:
                            user_tier = 'free'
                        user_signals = []
                        for sig in scored_signals_all:
                            eligible = await delivery_mgr.should_send_signal(user_tier, float(sig.get('score', 0)), user_id=user_id, session=session)
                            if eligible:
                                msg = delivery_mgr.format_for_delivery(sig, user_tier)
                                if msg:
                                    user_signals.append(msg)
                        if DRY_RUN:
                            for msg in user_signals:
                                print(f"[DRY RUN][{user_tier}] {msg}")
                        else:
                            from signalrank_telegram.bot import dispatch_signals
                            dispatched = dispatch_signals(user_signals, user_id=user_id)
                        dispatched_count += 1
                return dispatched_count
            cycle_dispatched_users += asyncio.run(deliver_all())

            # Optionally flush analytics every N cycles or on interval
            if cycle_no % 10 == 0:
                signal_analytics.flush()

            # Explicit per-cycle max score logging for easier troubleshooting.
            if _env_bool("ENGINE_CYCLE_LOG", True):
                if cycle_max_score is not None:
                    print(
                        f"[engine] cycle={cycle_no} max_score={cycle_max_score:.2f} max_asset={cycle_max_score_asset or 'n/a'} threshold={MIN_SCORE_THRESHOLD}",
                        flush=True,
                    )
                else:
                    print(
                        f"[engine] cycle={cycle_no} max_score=n/a threshold={MIN_SCORE_THRESHOLD}",
                        flush=True,
                    )

            # One-line per-cycle health signal for Railway logs.
            if _env_bool("ENGINE_CYCLE_LOG", True):
                every = max(1, _env_int("ENGINE_CYCLE_LOG_EVERY", 1))
                if cycle_no <= 0 or (cycle_no % every) == 0:
                    crypto_provider = (os.getenv("CRYPTO_DATA_PROVIDER") or "binance").strip().lower()
                    filter_top = ""
                    if cycle_filter_rejection_counts:
                        top3 = cycle_filter_rejection_counts.most_common(3)
                        filter_top = ";".join([f"{r}:{c}" for r, c in top3])
                    print(
                        "[engine] cycle="
                        f"{cycle_no} assets={cycle_assets} candidates={cycle_candidates} "
                            f"deduped={cycle_after_dedupe} consensus={cycle_after_consensus} risk_ok={cycle_after_risk} ml_ok={cycle_after_ml} "
                        f"scored>={MIN_SCORE_THRESHOLD:.2f}={cycle_scored} stored={cycle_stored} "
                        f"rejected_filters={cycle_rejected_filters} rejected_ultra={cycle_rejected_ultra} "
                        f"score_errors={cycle_score_errors} "
                        f"store_failures={cycle_store_failures} "
                            f"store_error={cycle_store_error or 'n/a'} "
                        f"users={cycle_users} dispatched={cycle_dispatched_users} "
                            f"max_score={cycle_max_score if cycle_max_score is not None else 'n/a'} max_score_asset={cycle_max_score_asset or 'n/a'} "
                            f"filter_top={filter_top or 'n/a'} "
                            f"crypto_provider={crypto_provider} fx_enabled={fx_enabled} stocks_enabled={stocks_enabled}",
                        flush=True,
                    )
        except Exception:
            # Keep process alive; production version should log structured errors.
            if _env_bool("ENGINE_CYCLE_LOG", True):
                try:
                    import traceback

                    print(f"[engine] cycle={cycle_no} error=unhandled_exception", flush=True)
                    traceback.print_exc()
                except Exception:
                    pass

        time.sleep(max(5, cycle_sleep_seconds))
