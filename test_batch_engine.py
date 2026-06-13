#!/usr/bin/env python3
"""
Replicate the BATCH engine flow to diagnose why 0 signals in production.
This tests the exact same code path used in main_loop() batch processing.
"""
import asyncio
import logging
import os
import time
from collections import Counter

logging.basicConfig(
    level=logging.INFO,
    format='%(name)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

os.environ.setdefault("TRADINGVIEW_ENABLED", "false")
os.environ.setdefault("USE_FALLBACK_STRATEGIES", "true")

# Use same threshold defaults as engine/core.py
os.environ.setdefault("ML_PROB_THRESHOLD", "0.40")
os.environ.setdefault("PREMIUM_SCORE_THRESHOLD", "40")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_asset_symbol(symbol: str) -> str:
    s = str(symbol or "").upper().strip()
    if s == "MATICUSDT":
        return "POLUSDT"
    return s


# Hard blacklist from engine/core.py
HARD_BLACKLIST = ["USDCUSDT", "USDTPERF", "DAIUSDT", "FDUSDUSDT", "USDTUSDC", "TUSDUSDT"]


async def batch_fetch_market_data(asset_to_tfs: dict) -> dict:
    """Exact copy of _fetch_market_data_for_assets from engine/core.py"""
    from data.fetcher import is_crypto, is_binance_blocked
    from data.market_data import fetch_market_data_cached
    from data.indicators import calculate_indicators
    import random
    
    concurrency = max(1, _env_int("MARKET_CACHE_FETCH_CONCURRENCY", 8))
    per_asset_timeout_default = 120.0 if is_binance_blocked() else 45.0
    per_asset_timeout = per_asset_timeout_default
    sem = asyncio.Semaphore(concurrency)
    
    _fetch_delay_base = float(os.getenv("ASSET_FETCH_DELAY_SECONDS", "1.0"))
    _fetch_delay_jitter = float(os.getenv("ASSET_FETCH_DELAY_JITTER", "0.5"))

    async def _one(asset: str, tfs: list, _index: int = 0):
        async with sem:
            if _index > 0 and _fetch_delay_base > 0:
                _jitter = random.random() * _fetch_delay_jitter
                _delay = _fetch_delay_base + _jitter
                await asyncio.sleep(_delay)
            
            try:
                started = time.time()
                data = await fetch_market_data_cached(asset, tfs)
                elapsed = time.time() - started
                
                if not data or not any(data.values()):
                    logger.error(
                        "[engine][FATAL] All providers failed for %s timeframes=%s",
                        asset,
                        tfs,
                    )
                    return asset, {}
                
                # Ensure indicators are present per timeframe
                for tf, tf_data in (data or {}).items():
                    try:
                        if not tf_data.get('indicators'):
                            tf_candles = tf_data.get('candles', [])
                            tf_data['indicators'] = calculate_indicators(tf_candles)
                    except Exception:
                        pass
                return asset, (data or {})
            except Exception as e:
                logger.error(
                    "[engine][FATAL] CANDLE FETCH EXCEPTION for %s: %s",
                    asset,
                    str(e)[:200],
                )
                return asset, {}

    tasks = [_one(a, tfs) for a, tfs in asset_to_tfs.items()]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return {asset: data for asset, data in results}


def _count_gate_failure(asset: str, gate: str):
    """Track gate failures for diagnostic heatmap"""
    logger.info(f"  [GATE FAIL] {asset}: {gate}")


async def test_batch_pipeline():
    """Replicate exact batch pipeline from engine.main_loop()"""
    from data.fetcher import is_crypto, is_fx, is_stock, is_commodity, market_closed_reason
    from engine.regime import detect_market_regime
    from strategies import run_all_strategies
    from engine.consensus import apply_consensus_filter
    from engine.signal_controller import SignalController
    from db.pg_features import compute_signal_fingerprint
    from engine.signal_validator import validate_signal
    from engine.risk import risk_check
    from engine.scoring import calculate_signal_score as score_signal, calculate_confluence
    
    # Simulate assets list - use a realistic set
    assets = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
        "DOGEUSDT", "DOTUSDT", "AVAXUSDT", "MATICUSDT", "LINKUSDT",
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
        "NVDA", "TSLA", "META", "AAPL", "MSFT"
    ]
    
    logger.info(f"Testing batch pipeline with {len(assets)} assets")
    
    # Build asset-to-tfs mapping (exact replica from engine)
    crypto_timeframes = ["1h", "4h", "1d"]
    fx_timeframes = ["1h", "4h"]
    stock_timeframes = ["1h", "4h", "1d"]
    commodity_timeframes = ["1h", "4h"]
    
    asset_to_tfs = {}
    for asset in assets:
        if _normalize_asset_symbol(asset) in HARD_BLACKLIST:
            _count_gate_failure(asset, "hard_blacklist")
            continue
            
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
    
    # Batch fetch market data
    logger.info("=== BATCH FETCH START ===")
    all_market_data = await batch_fetch_market_data(asset_to_tfs)
    logger.info(f"=== BATCH FETCH COMPLETE: {len(all_market_data)} assets with data ===")
    
    # Track stats like engine/core.py
    pipeline_stats = {
        "strategy_signals": 0,
        "normalized": 0,
        "consensus": 0,
        "selected": 0,
        "unique": 0,
        "strict_candidates": 0,
        "risk_passed": 0,
        "final_signals": 0,
    }
    
    failed_assets = []
    success_assets = []
    
    # Process each asset - exact replica of main_loop per-asset pipeline
    for asset in assets:
        norm_asset = _normalize_asset_symbol(asset)
        
        if norm_asset in HARD_BLACKLIST:
            logger.warning(f"[engine] HARDBLACKLIST: skipping {asset}")
            continue
            
        logger.info(f"[engine] pipeline: starting asset={asset}")
        
        market_data = all_market_data.get(asset, {})
        if not market_data:
            logger.warning(f"[engine][DATA STARVATION] {asset} returned empty data")
            _count_gate_failure(asset, "no_market_data")
            failed_assets.append(asset)
            continue
        
        # Check for candles
        has_candles = any((tf_data.get('candles') for tf_data in market_data.values())) if market_data else False
        if not has_candles:
            logger.warning(f"[engine][DATA STARVATION] {asset} returned empty candles")
            _count_gate_failure(asset, "no_candles")
            failed_assets.append(asset)
            continue
        
        # Check valid indicators  
        has_valid_indicators = False
        for tf_name, tf_data in market_data.items():
            if isinstance(tf_data, dict):
                ind = tf_data.get('indicators')
                if ind and isinstance(ind, dict) and len(ind) > 0:
                    rsi_val = ind.get('rsi', 0)
                    try:
                        if rsi_val and 0 <= float(rsi_val) <= 100:
                            has_valid_indicators = True
                    except (TypeError, ValueError):
                        pass
        
        if not has_valid_indicators:
            logger.warning(f"[engine][INDICATOR STARVATION] {asset} missing valid indicators")
            _count_gate_failure(asset, "no_valid_indicators")
            failed_assets.append(asset)
            continue
        
        # Detect regime
        try:
            regime = detect_market_regime(market_data)
        except Exception:
            regime = None
        
        # Run strategies
        try:
            strategy_signals = run_all_strategies(asset, market_data, regime) or []
        except Exception as e:
            logger.exception(f"Strategies failed for {asset}")
            strategy_signals = []

        pipeline_stats["strategy_signals"] += len(strategy_signals)
        
        if not strategy_signals:
            logger.warning(f"[engine] No strategy signals for {asset}")
            _count_gate_failure(asset, "no_strategy_signals")
            failed_assets.append(asset)
            continue
        
        logger.info(f"[engine] strategy_signals generated for {asset}: count={len(strategy_signals)}")
        
        # Normalize/dedupe
        try:
            controller = SignalController()
            normalized = controller.normalize_signals(strategy_signals)
        except Exception:
            normalized = strategy_signals
        pipeline_stats["normalized"] += len(normalized)
        
        # Consensus
        try:
            consensus_signals = apply_consensus_filter(normalized)
        except Exception:
            consensus_signals = []
        pipeline_stats["consensus"] += len(consensus_signals)
        
        # Pick best direction
        try:
            if 'controller' in locals():
                selected_signals = controller.pick_best_direction_per_pair(consensus_signals)
            else:
                selected_signals = consensus_signals
        except Exception:
            selected_signals = consensus_signals
        pipeline_stats["selected"] += len(selected_signals)
        
        # Unique/de-dupe
        try:
            unique_signals = []
            seen = set()
            for sig in selected_signals:
                fp = compute_signal_fingerprint(sig)
                sig['fingerprint'] = fp
                if fp and fp in seen:
                    continue
                if fp:
                    seen.add(fp)
                unique_signals.append(sig)
            selected_signals = unique_signals
        except Exception:
            pass
        pipeline_stats["unique"] += len(selected_signals)
        
        # Validate/strict gates
        strict_candidates = []
        for sig in selected_signals:
            # Basic validation
            ok, reason = validate_signal(sig)
            if not ok:
                continue
            # Risk check
            account_state = type('AccountState', (), {'drawdown': 0.0})()
            if not risk_check(sig, account_state):
                continue
            strict_candidates.append(sig)
        
        pipeline_stats["strict_candidates"] += len(strict_candidates)
        
        if not strict_candidates:
            logger.warning(f"[engine] No strict candidates for {asset}")
            _count_gate_failure(asset, "no_strict_candidates")
            failed_assets.append(asset)
            continue
        
        # Skip ML for now - just check if signals pass basic gates
        
        # Final signals 
        final_signals = strict_candidates
        pipeline_stats["final_signals"] += len(final_signals)
        
        if final_signals:
            success_assets.append(asset)
            logger.info(f"[engine] FINAL: {asset} has {len(final_signals)} signals")
    
    # Summary
    logger.info("=" * 60)
    logger.info("BATCH PIPELINE SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total assets processed: {len(assets)}")
    logger.info(f"Assets with successful signals: {len(success_assets)}")
    logger.info(f"Assets failed: {len(failed_assets)}")
    logger.info(f"Pipeline stats: {pipeline_stats}")
    
    if failed_assets:
        logger.info(f"Failed asset breakdown: {failed_assets[:10]}...")
    
    if success_assets:
        logger.info(f"Success assets: {success_assets}")


if __name__ == "__main__":
    asyncio.run(test_batch_pipeline())
