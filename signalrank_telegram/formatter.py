from engine.tier_notifications import TierNotificationManager
from datetime import datetime

# Initialize tier notification manager
_tier_notifier = TierNotificationManager()

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

def _confidence_tag(score: float | int | None) -> str:
	"""Return confidence strength emoji tag based on score."""
	try:
		s = float(score or 0)
	except Exception:
		s = 0.0
	
	if s >= 80:
		return "🔥 STRONG"
	elif s >= 65:
		return "✅ MODERATE"
	else:
		return "⚠️ WEAK"

def _confluence_display(confluence_count: int | None, confluence_total: int | None) -> str:
	"""Return confluence check marks display."""
	count = confluence_count or 0
	total = confluence_total or 5
	
	# Display as ✅ for each confirmation, ⭕ for remaining
	checks = "✅" * count + "⭕" * (total - count)
	return f"{checks} ({count}/{total})"

def _format_expiration(expires_at: str | None) -> str:
	"""Format expiration time nicely."""
	if not expires_at:
		return "Open-ended"
	try:
		from datetime import datetime
		exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
		now = datetime.utcnow().replace(tzinfo=exp_dt.tzinfo) if exp_dt.tzinfo else datetime.utcnow()
		diff = (exp_dt - now).total_seconds()
		if diff < 0:
			return "Expired"
		hours = int(diff // 3600)
		minutes = int((diff % 3600) // 60)
		if hours > 0:
			return f"{hours}h {minutes}m remaining"
		else:
			return f"{minutes}m remaining"
	except Exception:
		return expires_at[:10] if isinstance(expires_at, str) else "N/A"

def _risk_guidance(tier: str, score: float | int | None) -> str:
	"""Return risk management guidance based on tier and score."""
	try:
		s = float(score or 0)
	except Exception:
		s = 0.0
	
	tier = str(tier or "").upper()
	
	if tier == "PREMIUM":
		if s >= 80:
			return "💡 Max position: 3% of capital | Stop at -1% | Trail above entry"
		elif s >= 65:
			return "💡 Max position: 2% of capital | Stop at -1.5% | Trail above entry"
		else:
			return "⚠️ Max position: 1% of capital | Stop at -2% | Trail tightly"
	elif tier in {"VIP", "OWNER", "ADMIN"}:
		if s >= 80:
			return "💡 Max position: 5% of capital | Scale into wins | Trail aggressively"
		elif s >= 65:
			return "💡 Max position: 3% of capital | Scale into wins | Trail above breakeven"
		else:
			return "⚠️ Max position: 2% of capital | No scaling | Trail tightly"
	else:
		return "📌 Always use stop loss | Risk max 1% per trade"

def _star_rating(confluence_count: int | None, score: float | int | None) -> str:
	"""Generate a star rating based on confluence count and score."""
	try:
		conf = int(confluence_count or 0)
		scr = float(score or 0)
	except Exception:
		return "⭐" * 3
	
	# 5-star scale: confluence (0-5) counts for 3 stars, score for 2 stars
	conf_stars = min(conf, 5) / 5 * 3  # 0-3 stars from confluence
	score_stars = 2 if scr >= 80 else (1.5 if scr >= 65 else 1)  # 1-2 stars from score
	
	total_stars = int(conf_stars + score_stars)
	total_stars = max(1, min(5, total_stars))  # Clamp to 1-5
	
	return "⭐" * total_stars

def format_signal(signal, display_tier: str | None = None, limited: bool = False):
	"""Format a signal for Telegram with tier-appropriate detail.

	- display_tier: force header tier label (vip/premium/free)
	- limited: Free-tier display (direction-only; no exact levels)
	
	Tier rules:
	- FREE: Direction + asset + timeframe only (limited)
	- PREMIUM: Full signal with SL/TP + confidence + regime + NEW FEATURES
	- VIP: Everything + strategy + strength + ML confidence + R/R analysis + NEW FEATURES
	- ADMIN: Same as VIP (sees all details)
	"""
	
	# Use new tier-based notification system for premium/vip
	if display_tier and display_tier.lower() in ('premium', 'vip', 'admin', 'owner'):
		# Map tier
		user_tier = display_tier.lower()
		if user_tier in ('owner', 'admin'):
			user_tier = 'vip'  # Admin/Owner get VIP formatting
		
		# Extract new features from signal
		entry_zone = signal.get('entry_zone', {})
		htf_bias = signal.get('htf_bias', {})
		mtf_confluence = signal.get('mtf_confluence', {})
		session = signal.get('session', 'UNKNOWN')
		
		# If new features present, use new formatter
		if entry_zone or htf_bias:
			try:
				return _tier_notifier.format_new_signal(
					signal=signal,
					user_tier=user_tier,
					entry_zone=entry_zone,
					htf_bias=htf_bias,
					mtf_confluence=mtf_confluence,
					session=session
				)
			except Exception as e:
				# Fallback to old formatter on error
				pass

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

	# Generate star rating for display
	star_rating = _star_rating(signal.get('confluence_count'), signal.get('score'))

	msg = f"""\
🚀 TRADE ALERT — {label} {star_rating}

Asset: {signal.get('asset')}
Direction: {signal.get('direction').upper() if signal.get('direction') else 'N/A'}
Timeframe: {signal.get('timeframe')}
"""
	if show_levels:
		msg += f"""Entry: {signal.get('entry')}
Stop Loss: {signal.get('stop_loss')}
"""
		# Display multiple TP levels with exit percentages
		tp_levels = signal.get('tp_levels', [])
		if tp_levels and len(tp_levels) >= 3:
			# Standard 3-level exits: 33% each
			msg += f"""Take Profit 1: {tp_levels[0]} (33% exit)
Take Profit 2: {tp_levels[1]} (33% exit)
Take Profit 3: {tp_levels[2]} (34% exit)
"""
		elif tp_levels:
			# Fallback for fewer TP levels
			exit_pct = 100 // len(tp_levels)
			for i, tp in enumerate(tp_levels, 1):
				pct = exit_pct if i < len(tp_levels) else (100 - exit_pct * (len(tp_levels) - 1))
				msg += f"Take Profit {i}: {tp} ({pct}% exit)\n"
		else:
			# No TP levels, show single TP
			msg += f"Take Profit: {signal.get('take_profit')}\n"
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
		confidence_tag = _confidence_tag(signal.get('score'))
		confluence_display = _confluence_display(signal.get('confluence_count'), signal.get('confluence_total'))
		msg += f"""Confidence: {confidence_tag}
Score: {signal.get('score')}/100
Confluence: {confluence_display}
Suggested risk: {_risk_suggestion(signal.get('score'))}
"""

	if show_levels:
		msg += f"Market Regime: {signal.get('regime', 'N/A')}\n"
		session = signal.get('session')
		if session:
			msg += f"📍 Session: {session}\n"
	
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

	# Expiration time for PREMIUM+
	if show_levels:
		try:
			expires_at = signal.get('expires_at')
			if expires_at:
				exp_str = _format_expiration(expires_at)
				msg += f"\n⏰ Valid: {exp_str}"
		except Exception:
			pass
	
	# Risk guidance for PREMIUM+
	if show_levels:
		try:
			guidance = _risk_guidance(label, signal.get('score'))
			msg += f"\n{guidance}"
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
