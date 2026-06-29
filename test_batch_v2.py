#!/usr/bin/env python3
"""Simple batch pipeline test."""
import asyncio
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

os.environ.setdefault("TRADINGVIEW_ENABLED", "false")
os.environ.setdefault("USE_FALLBACK_STRATEGIES", "true")


async def test_batch():
    from data.fetcher import is_crypto, is_fx, is_stock, is_commodity
    from data.market_data import fetch_market_data_cached
    from data.indicators import calculate_indicators
    from engine.regime import detect_market_regime
    from strategies import run_all_strategies
    from engine.consensus import apply_consensus_filter
    
    # Small batch of assets
    assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "EURUSD", "NVDA"]
    
    logger.info(f"Testing batch with {len(assets)} assets")
    
    # Build asset-to-tfs
    asset_to_tfs = {}
    for asset in assets:
        if is_crypto(asset):
            asset_to_tfs[asset] = ["1h", "4h"]
        elif is_fx(asset):
            asset_to_tfs[asset] = ["1h", "4h"]
        elif is_stock(asset):
            asset_to_tfs[asset] = ["1h", "4h"]
        else:
            asset_to_tfs[asset] = ["1h", "4h"]
    
    logger.info("Fetching market data...")
    all_data = {}
    
    for asset, tfs in asset_to_tfs.items():
        logger.info(f"  Fetching {asset}...")
        data = await fetch_market_data_cached(asset, tfs)
        if not data:
            logger.warning(f"  FAILED: {asset} - no data")
            continue
        
        # Ensure indicators
        for tf, tf_data in data.items():
            if tf_data and not tf_data.get('indicators'):
                candles = tf_data.get('candles', [])
                if candles:
                    tf_data['indicators'] = calculate_indicators(candles)
        
        all_data[asset] = data
        logger.info(f"  OK: {asset} - {len(data)} TFs")
    
    logger.info(f"Got data for {len(all_data)} assets")
    
    # Run pipeline
    total_signals = 0
    for asset, market_data in all_data.items():
        regime = detect_market_regime(market_data)
        
        signals = run_all_strategies(asset, market_data, regime) or []
        
        if signals:
            total_signals += len(signals)
            consensus = apply_consensus_filter(signals)
            logger.info(f"  {asset}: {len(signals)} signals -> {len(consensus)} consensus")
        else:
            logger.warning(f"  {asset}: NO SIGNALS")
    
    logger.info(f"FINAL: {total_signals} total signals from {len(all_data)} assets")
    
    if total_signals == 0:
        logger.error("BUG CONFIRMED: 0 signals despite valid data!")
    else:
        logger.info("Working correctly!")


if __name__ == "__main__":
    asyncio.run(test_batch())
