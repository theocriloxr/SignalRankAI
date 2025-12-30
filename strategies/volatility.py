def volatility_strategies(asset, timeframe, data):
    # Example: ATR breakout
    signals = []
    ind = data['indicators']
    if ind['atr'] > 1.5 * ind['bollinger']['width']:
        signals.append({
            'asset': asset,
            'timeframe': timeframe,
            'direction': 'BUY',
            'entry': data['candles'][-1]['close'] if data['candles'] else None,
            'stop_loss': data['candles'][-1]['low'] if data['candles'] else None,
            'take_profit': None,
            'rr_ratio': 2.2,
            'strategy_name': 'ATR Breakout',
            'strategy_group': 'VOLATILITY',
            'strength': 0.8
        })
    return signals
