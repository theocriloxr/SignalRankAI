import os
import time
import asyncio
import logging
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

# NEW: Signal-only bot features
from engine.mtf_analysis import MultiTimeframeAnalyzer
from engine.signal_context import SignalContext, SignalCooldownManager, OneBiasPerTimeframe
from engine.advanced_filters import SmartFilterSuite
from engine.tier_notifications import TierNotificationManager

# NEW: Near-zero loss trading system
from engine.ultra_quality_filter import ultra_quality
from engine.advanced_exit_manager import advanced_exit

logger = logging.getLogger(__name__)


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
    # When Binance is blocked we rely on slower fallbacks (Bybit/CryptoCompare), so allow more time.
    per_asset_timeout_default = 60.0 if is_binance_blocked() else 25.0
    per_asset_timeout = float(_env_float("MARKET_FETCH_TIMEOUT_SECONDS", per_asset_timeout_default))
    sem = asyncio.Semaphore(concurrency)

    async def _one(asset: str, tfs: list[str]) -> tuple[str, dict]:
        async with sem:
            try:
                data = await asyncio.wait_for(fetch_market_data_cached(asset, tfs), timeout=max(1.0, per_asset_timeout))
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
    # ============================================
    # INITIALIZE ALL TRADING SYSTEM COMPONENTS
    # ============================================
    
    # Risk management (for SUGGESTIONS, not execution)
    account_equity = 10000.0  # Default, should come from broker API
    risk_manager = RiskManager(account_equity)
    correlation_manager = CorrelationManager()
    
    # Exit management (for TRACKING outcomes, not execution)
    exit_manager = ExitManager()
    partial_exit_tracker = PartialExitTracker()
    
    # Smart filters
    signal_filter = SignalFilter()
    regime_filter = MarketRegimeFilter()
    slippage_control = SlippageControl()
    
    # Analytics (for performance tracking)
    backtest_engine = BacktestEngine()
    optimization_engine = OptimizationEngine()
    
    # Position tracking (monitor signal outcomes)
    open_positions = []
    last_trade_times = {}
    
    # ============================================
    # NEW: SIGNAL-ONLY BOT FEATURES
    # ============================================
    
    # Multi-timeframe analysis
    mtf_analyzer = MultiTimeframeAnalyzer()
    
    # Signal context management
    signal_context = SignalContext()
    cooldown_manager = SignalCooldownManager()
    bias_manager = OneBiasPerTimeframe()
    
    # Advanced filters
    advanced_filters = SmartFilterSuite()
    
    # Tier-based notifications
    tier_notifier = TierNotificationManager()
    
    # NO TRADE alert tracking
    last_no_trade_alert = None
    
    # If Binance is blocked and no explicit override is provided, drop the heaviest TF (5m) to speed fallbacks.
    if os.getenv("CRYPTO_TIMEFRAMES"):
        crypto_timeframes = [x.strip() for x in os.getenv("CRYPTO_TIMEFRAMES").split(",") if x.strip()]
    else:
        crypto_timeframes = [x.strip() for x in ("15m,1h,4h,1d" if is_binance_blocked() else "5m,15m,1h,4h,1d").split(",") if x.strip()]
    # AlphaVantage free tier is rate-limited; default to daily-only for FX.
    fx_timeframes = [x.strip() for x in (os.getenv("FX_TIMEFRAMES") or "1d").split(",") if x.strip()]
    # Stocks: use mid/HTFs by default; override via STOCK_TIMEFRAMES
    stock_timeframes = [x.strip() for x in (os.getenv("STOCK_TIMEFRAMES") or "15m,1h,4h,1d").split(",") if x.strip()]

    if _env_bool("ENGINE_CYCLE_LOG", True):
        try:
            print(
                "[engine] loop_start "
                f"dry_run={bool(DRY_RUN)} "
                f"cycle_sleep_seconds={int(os.getenv('CYCLE_SLEEP_SECONDS', '60'))} "
                f"crypto_timeframes={','.join(crypto_timeframes)} "
                f"fx_timeframes={','.join(fx_timeframes)} "
                f"stock_timeframes={','.join(stock_timeframes)}",
                flush=True,
            )
        except Exception:
            pass

    try:
        fx_max_pairs = int((os.getenv("FX_MAX_PAIRS_PER_CYCLE") or os.getenv("FX_MAX_PAIRS") or "6").strip())
    except Exception:
        fx_max_pairs = 6

    cycle_sleep_seconds = int(os.getenv("CYCLE_SLEEP_SECONDS", "60"))

    # If FX pairs are configured, require a real candle provider key.
    # Non-fatal: warn and disable FX rather than crashing the whole engine.
    fx_pairs = (os.getenv("FX_PAIRS") or "").strip()
    fx_enabled = True
    # Explicit stocks toggle; default enabled
    stocks_enabled = (os.getenv("STOCK_TRADING_ENABLED") or "true").strip().lower() in {"1","true","yes","y","on"}
    alphavantage_key = (os.getenv("ALPHAVANTAGE_API_KEY") or "").strip()
    if not alphavantage_key:
        # If we don't have a provider key, we can still run crypto-only.
        # FX pairs (configured or defaulted) will be skipped below.
        fx_enabled = False
        if fx_pairs:
            print(
                "[WARN] FX_PAIRS is set but ALPHAVANTAGE_API_KEY is missing. Disabling FX candles.",
                flush=True,
            )
        else:
            print(
                "[INFO] FX trading disabled: no ALPHAVANTAGE_API_KEY configured.",
                flush=True,
            )
    else:
        print(
            f"[INFO] FX trading enabled: AlphaVantage key configured ({alphavantage_key[:4]}...)",
            flush=True,
        )

    # Example: fetch strategy weights and regime_strategies from ML/DB (stubbed here)
    from engine.ml import get_strategy_weights, get_regime_strategies
    strategy_weights = get_strategy_weights() if hasattr(get_strategy_weights, '__call__') else {}
    regime_strategies = get_regime_strategies() if hasattr(get_regime_strategies, '__call__') else None

    while True:
        # Increment cycle counter early so we can use it for pair rotation.
        try:
            cycle_no = _env_int("_ENGINE_CYCLE_NO", 0) + 1
            os.environ["_ENGINE_CYCLE_NO"] = str(cycle_no)
        except Exception:
            cycle_no = 0

        if _env_bool("ENGINE_CYCLE_LOG", True):
            try:
                every = max(1, _env_int("ENGINE_CYCLE_LOG_EVERY", 1))
                if cycle_no <= 0 or (cycle_no % every) == 0:
                    print(f"[engine] cycle={cycle_no} start", flush=True)
            except Exception:
                pass

        cycle_assets = 0
        cycle_candidates = 0
        cycle_after_dedupe = 0
        cycle_after_consensus = 0
        cycle_after_risk = 0
        cycle_after_ml = 0
        cycle_scored = 0
        cycle_stored = 0
        cycle_rejected_filters = 0
        cycle_rejected_ultra = 0
        cycle_score_errors = 0
        cycle_store_failures = 0
        cycle_store_error = None
        cycle_max_score = None
        cycle_max_score_asset = None
        cycle_users = 0
        cycle_dispatched_users = 0
        cycle_filter_rejection_counts: Counter[str] = Counter()
        # Global kill-switch (skip cycle but keep process alive)
        try:
            if state.get_killswitch_sync().enabled:
                if _env_bool("ENGINE_CYCLE_LOG", True):
                    try:
                        print(f"[engine] cycle={cycle_no} skipped=killswitch", flush=True)
                    except Exception:
                        pass
                time.sleep(max(5, cycle_sleep_seconds))
                continue
        except Exception:
            pass

        try:
            # Prioritize TRADABLE_ASSETS env for crypto; fallback to discovery if empty.
            tradable = load_tradable_assets()
            try:
                discovered = get_all_trending_pairs() or []
            except Exception:
                discovered = []

            if tradable:
                assets = tradable  # Env-configured universe takes priority
            else:
                assets = discovered  # Fallback to discovery
            
            # Add FX pairs to the asset list if configured and enabled
            if fx_enabled and fx_pairs:
                fx_list = [x.strip() for x in fx_pairs.split(",") if x.strip()]
                assets = list(assets) + fx_list
                if _env_bool("ENGINE_CYCLE_LOG", True) and _env_bool("ENGINE_ASSET_DEBUG", False):
                    print(f"[engine] Added {len(fx_list)} FX pair(s) to asset list", flush=True)

            # If TRADABLE_ASSETS is set, supplement with stock tickers when enabled
            # This ensures stocks are not omitted when a custom universe is provided.
            if stocks_enabled:
                try:
                    # Prefer manual configuration via STOCK_TICKERS, else discover trending
                    manual = (os.getenv("STOCK_TICKERS") or "").strip()
                    if manual:
                        stock_list = [x.strip().upper() for x in manual.split(",") if x.strip()]
                    else:
                        # Use the same env-driven limit as discovery
                        try:
                            stock_top_n = int((os.getenv("STOCK_TRENDING_TOP_N") or "20").strip())
                        except Exception:
                            stock_top_n = 20
                        stock_list = get_trending_stock_tickers(stock_top_n)
                    if stock_list:
                        assets = list(assets) + list(stock_list)
                        if _env_bool("ENGINE_CYCLE_LOG", True) and _env_bool("ENGINE_ASSET_DEBUG", False):
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
                continue

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

            try:
                all_market_data = asyncio.run(_fetch_market_data_for_assets(asset_to_tfs))
            except Exception:
                all_market_data = {}

            for asset in assets:
                try:
                    market_data = (all_market_data or {}).get(asset) or {}

                    # Fail-closed: never run strategies on empty/insufficient market data.
                    try:
                        min_candles = int((os.getenv("MIN_CANDLES_PER_TIMEFRAME") or "50").strip())
                    except Exception:
                        min_candles = 50
                    min_candles = max(1, int(min_candles))
                    if not market_data:
                        continue
                    has_enough = False
                    for tf_data in (market_data or {}).values():
                        candles = (tf_data or {}).get("candles") or []
                        if isinstance(candles, list) and len(candles) >= min_candles:
                            has_enough = True
                            break
                    if not has_enough:
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
                    try:
                        cycle_after_consensus += len(consensus_signals or [])
                    except Exception:
                        pass
                    try:
                        cycle_after_dedupe += len(selected_signals or [])
                    except Exception:
                        pass

                    # Risk Engine
                    from engine.risk import risk_check

                    account_state = type('AccountState', (), {'drawdown': 0.0})()  # Replace with real account state
                    risk_signals = [s for s in selected_signals if risk_check(s, account_state)]
                    try:
                        cycle_after_risk += len(risk_signals or [])
                    except Exception:
                        pass

                    # ML Probability Filter
                    from ml.features import extract_features
                    from ml.inference import MLFilter

                    ml_filter = MLFilter()
                    ml_signals = []
                    try:
                        # Raised to 0.65 for win rate recovery (was 0.6)
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
                        if not approved:
                            continue
                        signal["ml_probability"] = probability
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
                            
                            # If stops are missing/invalid, calculate from ATR
                            if not sl or sl == entry:
                                atr_value = signal.get('atr', 0)
                                if atr_value > 0 and entry > 0:
                                    direction = signal.get('direction', 'long').lower()
                                    if direction == 'long':
                                        sl = entry - (2 * atr_value)  # 2x ATR below
                                    else:
                                        sl = entry + (2 * atr_value)  # 2x ATR above
                            
                            if not tp or tp == entry:
                                atr_value = signal.get('atr', 0)
                                if atr_value > 0 and entry > 0 and sl and sl != entry:
                                    direction = signal.get('direction', 'long').lower()
                                    rr = 2.0  # Target 2:1 R/R
                                    if direction == 'long':
                                        tp = entry + (abs(entry - sl) * rr)
                                    else:
                                        tp = entry - (abs(entry - sl) * rr)
                            
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

            # Ranking and Dispatch
            ranked_signals = rank_signals(scored_signals_all)
            if DRY_RUN:
                for sig in (ranked_signals.get('vip', []) + ranked_signals.get('premium', [])):
                    print("[DRY RUN]", sig)
            else:
                user_ids = get_all_user_ids_compat()
                try:
                    cycle_users = len(user_ids or [])
                except Exception:
                    cycle_users = 0
                for user_id in user_ids:
                    dispatch_signals(ranked_signals, user_id=user_id)
                    cycle_dispatched_users += 1

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
