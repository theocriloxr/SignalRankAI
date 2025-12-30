def trend_strategies(asset, timeframe, data):
    # Example: EMA crossover trend strategy
    signals = []
    ind = data['indicators']
    if ind['ema_fast'] > ind['ema_slow'] and ind['ema_slow'] > ind['ema_trend']:
        signals.append({
            'asset': asset,
            'timeframe': timeframe,
            'direction': 'BUY',
            'entry': data['candles'][-1]['close'] if data['candles'] else None,
            'stop_loss': data['candles'][-1]['low'] if data['candles'] else None,
            'take_profit': None,
            'rr_ratio': 2.5,
            'strategy_name': 'EMA Trend',
            'strategy_group': 'TREND',
            'strength': 0.9
        })
    return signals
