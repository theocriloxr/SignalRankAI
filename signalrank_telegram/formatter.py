def _risk_suggestion(score: float | int | None) -> str:
	try:
		s = float(score or 0)
	except Exception:
		s = 0.0
	# Very simple mapping; keep conservative.
	if s >= 92:
		return "2.0%"
	if s >= 85:
		return "1.5%"
	if s >= 75:
		return "1.0%"
	return "0.5%"


def format_signal(signal, display_tier: str | None = None, limited: bool = False):
	"""Format a signal for Telegram.

	- display_tier: force header tier label (vip/premium/free)
	- limited: Free-tier display (direction-only; no exact levels)
	"""

	ref = signal.get("signal_id") or signal.get("id")
	try:
		ref = str(ref)
	except Exception:
		ref = None

	# Short user-facing reference: keep DB IDs intact, display a prefix.
	ref_short = None
	try:
		if ref:
			ref_short = ref[:8]
	except Exception:
		ref_short = None

	if limited:
		lines = ["🔒 FREE USER (LIMITED SIGNAL)", ""]
		if ref_short:
			lines.append(f"Reference: {ref_short}")
		lines += [
			f"Asset: {signal.get('asset')}",
			f"Timeframe: {signal.get('timeframe')}",
			f"Direction: {signal.get('direction')}",
			"",
			"Upgrade to Premium to see exact entry/SL/TP and receive real-time alerts.",
		]
		return "\n".join(lines)

	# Full detail
	if display_tier is None:
		try:
			import os
			vip_cut = float((os.getenv("VIP_SCORE_THRESHOLD") or "72").strip())
		except Exception:
			vip_cut = 72.0
		display_tier = 'vip' if float(signal.get('score', 0) or 0) >= vip_cut else 'premium'
	label = str(display_tier).strip().upper()

	msg = f"""\
🚀 TRADE ALERT — {label}

Asset: {signal.get('asset')}
Direction: {signal.get('direction')}
Timeframe: {signal.get('timeframe')}
Entry: {signal.get('entry')}
Stop Loss: {signal.get('stop_loss')}
Take Profit: {signal.get('take_profit')}
Risk/Reward: {signal.get('rr_ratio')}
Confidence Score: {signal.get('score')}/100
Suggested risk: {_risk_suggestion(signal.get('score'))}
Market Regime: {signal.get('regime', 'N/A')}
"""
	if ref_short:
		msg = f"Reference: {ref_short}\n" + msg

	# Extra detail for VIP-ish tiers
	if label in {'VIP', 'OWNER', 'ADMIN'}:
		try:
			strategy = signal.get('strategy_name') or signal.get('strategy')
			group = signal.get('strategy_group')
			strength = signal.get('strength')
			if strategy:
				msg += f"\nStrategy: {strategy}" + (f" ({group})" if group else "")
			if strength is not None:
				msg += f"\nStrength: {strength}"
		except Exception:
			pass

	# Show ML confidence only for VIP-ish tiers
	if label in {'VIP', 'OWNER'} and signal.get('ml_probability') is not None:
		try:
			msg += f"\n📊 ML Confidence: {round(float(signal['ml_probability'])*100, 1)}%"
		except Exception:
			pass
	msg += "\n\n⚠️ Educational only. Not financial advice."
	return msg
