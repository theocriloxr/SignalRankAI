#!/usr/bin/env python3
"""Full engine pipeline test - simulate what's happening in production."""
import sys
import os
sys.path.insert(0, '.')

# Force short cache
os.environ['CANDLE_REQUEST_CACHE_TTL_SECONDS'] = '0.1'

print('=== Full Signal Chain Test ===')
try:
    from data.fetcher import get_candles
    from data.indicators import calculate_indicators
    from strategies import run_all_strategies
    from engine.consensus import apply_consensus_filter
    from engine.scoring import calculate_signal_score
    
    asset = 'BTCUSDT'
    timeframe = '1h'
    
    # === Step 1: Fetch data ===
    print(f'1. Fetching data for {asset}...')
    candles = get_candles(asset, timeframe)
    print(f'   Got {len(candles)} candles')
    
    if not candles:
        print('ERROR: No candles!')
        sys.exit(1)
    
    # === Step 2: Calculate indicators ===
    print(f'2. Calculating indicators...')
    indicators = calculate_indicators(candles)
    print(f'   RSI={indicators.get("rsi"):.2f}, EMA_fast={indicators.get("ema_fast")}')
    
    # === Step 3: Build market_data as engine does ===
    market_data = {
        timeframe: {
            'candles': candles,
            'indicators': indicators,
        }
    }
    regime = 'TRENDING'
    
    # === Step 4: Run strategies ===
    print(f'3. Running strategies...')
    signals = run_all_strategies(asset, market_data, regime)
    print(f'   Generated: {len(signals)} signals')
    
    if not signals:
        print('ERROR: No strategy signals!')
        sys.exit(1)
    
    # === Step 5: Normalize & dedupe (SignalController) ===
    print(f'4. Normalizing signals...')
    from engine.signal_controller import SignalController
    controller = SignalController()
    normalized = controller.normalize_signals(signals)
    print(f'   After normalize: {len(normalized)} signals')
    
    # === Step 6: Consensus filter ===
    print(f'5. Applying consensus...')
    consensus_signals = apply_consensus_filter(normalized)
    print(f'   After consensus: {len(consensus_signals)} signals')
    
    # === Step 7: Scoring ===
    print(f'6. Scoring signals...')
    scored = []
    for sig in consensus_signals:
        score = calculate_signal_score(sig)
        sig['score'] = score
        scored.append(sig)
        print(f'   - {sig.get("strategy_name")}: score={score:.1f}')
    
    # === Step 8: Apply threshold ===
    print(f'7. Applying score threshold...')
    from engine.core import _current_min_score_threshold
    threshold = _current_min_score_threshold()
    passed = [s for s in scored if s.get('score', 0) >= threshold]
    print(f'   Threshold={threshold:.1f}, Passed: {len(passed)}/{len(scored)}')
    
    if passed:
        print(f'\n=== SUCCESS: {len(passed)} signals passed threshold! ===')
    else:
        print(f'\n=== FAILED: No signals passed threshold! ===')
        
except Exception as e:
    import traceback
    print(f'Error: {type(e).__name__}: {e}')
    traceback.print_exc()
