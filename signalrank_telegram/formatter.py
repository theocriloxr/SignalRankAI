def format_signal(signal):
	tier = 'VIP' if signal.get('score', 0) >= 85 else 'PREMIUM'
	return f"""
🚀 TRADE ALERT — {tier}

Asset: {signal.get('asset')}
Direction: {signal.get('direction')}
Timeframe: {signal.get('timeframe')}
Entry: {signal.get('entry')}
Stop Loss: {signal.get('stop_loss')}
Take Profit: {signal.get('take_profit')}
Risk/Reward: {signal.get('rr_ratio')}
Confidence Score: {signal.get('score')}/100
Market Regime: {signal.get('regime', 'N/A')}
"""
