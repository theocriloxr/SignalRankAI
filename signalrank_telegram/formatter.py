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
	"""Format a signal for Telegram with tier-appropriate detail.

	- display_tier: force header tier label (vip/premium/free)
	- limited: Free-tier display (direction-only; no exact levels)
	
	Tier rules:
	- FREE: Direction + asset + timeframe only (limited)
	- PREMIUM: Full signal with SL/TP + confidence + regime
	- VIP: Everything + strategy + strength + ML confidence + R/R analysis
	- ADMIN: Same as VIP (sees all details)
	"""

	# Always use signal_id from database (the actual tracking ID)
	ref = signal.get("signal_id")
	if not ref:
		ref = None
	
	# Short user-facing reference: first 8 chars of signal_id
	ref_short = None
	if ref:
		try:
			ref_short = str(ref)[:8]
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

	# Determine what details to show based on tier
	show_levels = label in {'PREMIUM', 'VIP', 'OWNER', 'ADMIN'}
	show_strategy = label in {'VIP', 'OWNER', 'ADMIN'}
	show_ml = label in {'VIP', 'OWNER', 'ADMIN'}
	show_rr_detail = label in {'VIP', 'OWNER', 'ADMIN'}
	show_contributors = label in {'VIP', 'OWNER', 'ADMIN'}
	show_confidence = label in {'PREMIUM', 'VIP', 'OWNER', 'ADMIN'}  # Hide confidence from FREE

	msg = f"""\
🚀 TRADE ALERT — {label}

Asset: {signal.get('asset')}
Direction: {signal.get('direction').upper() if signal.get('direction') else 'N/A'}
Timeframe: {signal.get('timeframe')}
"""
	
	if show_levels:
		msg += f"""Entry: {signal.get('entry')}
Stop Loss: {signal.get('stop_loss')}
Take Profit: {signal.get('take_profit')}
"""
	else:
		# FREE tier: encourage upgrade
		msg += "\n🔒 Upgrade to PREMIUM to see Entry, Stop Loss, and Take Profit levels.\n"
	
	# Entry status flag
	entry_status = signal.get('entry_status', 'UNKNOWN')
	if entry_status == 'AT_ENTRY':
		status_emoji = "✅"
		status_text = "Entry zone reached"
	elif entry_status == 'PENDING_ENTRY':
		status_emoji = "⏳"
		status_text = "Awaiting entry"
	else:
		status_emoji = "❓"
		status_text = "Status unknown"
	msg += f"{status_emoji} Status: {status_text}\n"
	
	if show_confidence:
		msg += f"""Confidence Score: {signal.get('score')}/100
Suggested risk: {_risk_suggestion(signal.get('score'))}
"""

	if show_levels:
		msg += f"Market Regime: {signal.get('regime', 'N/A')}\n"
	
	if ref_short:
		msg = f"📋 Ref: {ref_short} (use /outcome {ref_short})\n" + msg

	# Strategy + strength for VIP+
	if show_strategy:
		try:
			strategy = signal.get('strategy_name') or signal.get('strategy')
			group = signal.get('strategy_group')
			strength = signal.get('strength')
			contributors = signal.get('contributors', [])
			
			if strategy:
				msg += f"\n📍 Primary Strategy: {strategy}"
				if group:
					msg += f" ({group})"
			
			if contributors and len(contributors) > 1:
				msg += f"\n🤝 Contributors: {', '.join(contributors[:3])}"
			
			if strength is not None:
				msg += f"\n💪 Strength: {strength}"
		except Exception:
			pass

	# ML confidence for VIP+
	if show_ml and signal.get('ml_probability') is not None:
		try:
			ml_val = float(signal['ml_probability'])
			ml_pct = round(ml_val * 100, 1)
			ml_emoji = "✅" if ml_val >= 0.75 else ("⚠️" if ml_val >= 0.5 else "❌")
			msg += f"\n{ml_emoji} ML Score: {ml_pct}% approval"
		except Exception:
			pass

	# R/R analysis for VIP+
	if show_rr_detail:
		try:
			rr = signal.get('rr_ratio')
			if rr is not None:
				rr_val = float(rr)
				rr_emoji = "🔥" if rr_val >= 2.0 else ("✅" if rr_val >= 1.5 else "⚠️")
				msg += f"\n{rr_emoji} Risk/Reward: {rr_val:.2f}:1"
		except Exception:
			pass

	msg += "\n\n⚠️ Educational only. Not financial advice."
	return msg


def format_signal_free_limited(signal):
	"""Format a signal for FREE users with limited information.
	
	Shows: Reference, Asset, Timeframe, Direction only.
	No Entry, SL, TP, or confidence scores.
	"""
	ref = signal.get("signal_id") or signal.get("id")
	try:
		ref = str(ref)
	except Exception:
		ref = None

	ref_short = None
	try:
		if ref:
			ref_short = ref[:8]
	except Exception:
		ref_short = None

	lines = ["🔒 FREE USER (LIMITED SIGNAL)", ""]
	if ref_short:
		lines.append(f"Reference: {ref_short}")
	lines += [
		f"Asset: {signal.get('asset')}",
		f"Timeframe: {signal.get('timeframe')}",
		f"Direction: {signal.get('direction', 'N/A').upper()}",
		"",
		"🔒 Upgrade to PREMIUM to see Entry, Stop Loss, and Take Profit levels.",
		"",
		"⚠️ Educational only. Not financial advice."
	]
	return "\n".join(lines)
