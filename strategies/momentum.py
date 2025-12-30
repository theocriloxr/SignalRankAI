def momentum_strategies(asset, timeframe, data):
    # Example: RSI oversold/overbought
    signals = []
    ind = data['indicators']
    if ind['rsi'] < 30:
        signals.append({
            'asset': asset,
            'timeframe': timeframe,
            'direction': 'BUY',
            'entry': data['candles'][-1]['close'] if data['candles'] else None,
            'stop_loss': data['candles'][-1]['low'] if data['candles'] else None,
            'take_profit': None,
            'rr_ratio': 2.0,
            'strategy_name': 'RSI Momentum',
            'strategy_group': 'MOMENTUM',
            'strength': 0.7
        })
    if ind['rsi'] > 70:
        signals.append({
            'asset': asset,
            'timeframe': timeframe,
            'direction': 'SELL',
            'entry': data['candles'][-1]['close'] if data['candles'] else None,
            'stop_loss': data['candles'][-1]['high'] if data['candles'] else None,
            'take_profit': None,
            'rr_ratio': 2.0,
            'strategy_name': 'RSI Momentum',
            'strategy_group': 'MOMENTUM',
            'strength': 0.7
        })
    return signals
