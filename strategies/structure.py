def structure_strategy(asset, timeframe, data):
    # Example: Price above 200 EMA = bullish structure
    signals = []
    ind = data['indicators']
    if ind['ema_trend'] and data['candles']:
        price = data['candles'][-1]['close']
        if price > ind['ema_trend']:
            signals.append({
                'asset': asset,
                'timeframe': timeframe,
                'direction': 'BUY',
                'entry': price,
                'stop_loss': data['candles'][-1]['low'],
                'take_profit': None,
                'rr_ratio': 2.1,
                'strategy_name': 'Structure Bull',
                'strategy_group': 'STRUCTURE',
                'strength': 0.6
            })
    return signals
