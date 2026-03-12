from engine.tier_notifications import TierNotificationManager
from datetime import datetime, timezone
import os

# Initialize tier notification manager
_tier_notifier = TierNotificationManager()

# Tier constants
TIER_FREE = "free"
TIER_PREMIUM = "premium"
TIER_VIP = "vip"
TIER_ADMIN = "admin"
TIER_OWNER = "owner"

def _get_user_tier(user_tier: str | None) -> str:
	"""Normalize and return user tier."""
	if not user_tier:
		return TIER_FREE
	tier = str(user_tier).lower().strip()
	if tier in {TIER_ADMIN, TIER_OWNER}:
		return TIER_VIP  # Admin/Owner see VIP content + everything
	if tier == TIER_VIP:
		return TIER_VIP
	if tier == TIER_PREMIUM:
		return TIER_PREMIUM
	return TIER_FREE

def _should_send_signal_for_tier(user_tier: str, score: float) -> bool:
	"""Check if signal should be sent to this tier based on quality."""
	tier = _get_user_tier(user_tier)
	
	# FREE: only 80%+ quality signals
	if tier == TIER_FREE:
		return score >= 80.0
	
	# PREMIUM: 65%+ signals (high & medium confidence)
	if tier == TIER_PREMIUM:
		return score >= 65.0
	
	# VIP/ADMIN/OWNER: all signals, but filtered quality-first
	if tier == TIER_VIP:
		return score >= 55.0  # Accept lower scores, but will show differently
	
	return True

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

def _format_expiration(expires_at) -> str:
	"""Format expiration time nicely. Accepts datetime objects or ISO strings."""
	if not expires_at:
		return "Open-ended"
	try:
		from datetime import datetime, timezone
		# Handle datetime objects directly (most common case from engine)
		if isinstance(expires_at, datetime):
			if expires_at.tzinfo is None:
				now = datetime.utcnow()
			else:
				now = datetime.now(timezone.utc)
			diff = (expires_at - now).total_seconds()
			if diff < 0:
				return "Expired"
			hours = int(diff // 3600)
			minutes = int((diff % 3600) // 60)
			if hours > 0:
				return f"{hours}h {minutes}m remaining"
			else:
				return f"{minutes}m remaining"
		# Handle ISO string
		if isinstance(expires_at, str):
			exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
			now = datetime.now(timezone.utc)
			diff = (exp_dt - now).total_seconds()
			if diff < 0:
				return "Expired"
			hours = int(diff // 3600)
			minutes = int((diff % 3600) // 60)
			if hours > 0:
				return f"{hours}h {minutes}m remaining"
			else:
				return f"{minutes}m remaining"
		return str(expires_at)
	except Exception:
		return str(expires_at)[:16] if expires_at else "N/A"

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

# ============================================================
# TIER-SPECIFIC FORMATTERS
# ============================================================

def format_signal_free(signal) -> str:
	"""Format signal for FREE tier: PROOF only, no explanations.
	
	Attributes:
	- 1-3 signals/day (score 80%+)
	- Single TP only
	- Basic SL
	- No explanations, no updates, optional delay
	- Purpose: Attract users, build trust, showcase accuracy
	"""
	ref = signal.get("signal_id") or signal.get("id")
	ref_short = str(ref)[:8] if ref else "N/A"
	
	msg = f"""\
🚀 BUY SIGNAL

Asset: {signal.get('asset')}
Timeframe: {signal.get('timeframe')}

Entry: {signal.get('entry')}
Stop Loss: {signal.get('stop_loss')}
Take Profit: {signal.get('take_profit')}

⚠️ Risk max 1–2%

📋 Ref: {ref_short} (use /outcome {ref_short})
"""
	return msg

def format_signal_premium(signal) -> str:
	"""Format signal for PREMIUM tier: Core revenue tier.
	
	Attributes:
	- 5-10 signals/day (score 65%+)
	- 2-3 TP levels
	- Confidence rating (%)
	- Signal validity window
	- Basic update alerts (TP / SL)
	- Session tag
	- Purpose: Core revenue, active traders, better clarity & control
	"""
	ref = signal.get("signal_id") or signal.get("id")
	ref_short = str(ref)[:8] if ref else "N/A"
	
	tp_levels = signal.get('tp_levels', [])
	score = signal.get('score', 0)
	session = signal.get('session', '')
	expires_at = signal.get('expires_at')
	
	msg = f"""\
🚀 BUY SIGNAL

Asset: {signal.get('asset')}
Timeframe: {signal.get('timeframe')}
"""
	
	if session:
		msg += f"Session: {session}\n"
	
	msg += f"""
Entry: {signal.get('entry')}
Stop Loss: {signal.get('stop_loss')}
"""
	
	# Multiple TP levels (2-3)
	if tp_levels:
		for i, tp in enumerate(tp_levels[:3], 1):
			msg += f"TP{i}: {tp}\n"
	else:
		msg += f"TP: {signal.get('take_profit')}\n"
	
	msg += f"""
🔥 Confidence: {int(score)}%
"""
	
	# Validity window
	if expires_at:
		try:
			exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
			now = datetime.now(timezone.utc)
			diff = (exp_dt - now).total_seconds()
			candles = max(1, int(diff / 900))  # Assume 15min candles
			msg += f"⏳ Validity: Next {candles} candles\n"
		except Exception as e:
			import logging
			logging.debug(f"[formatter] Failed to calculate validity window: {e}")
			pass
	
	msg += f"""
⚠️ Risk max 1–2%

📋 Ref: {ref_short} (use /outcome {ref_short})
"""
	return msg

def format_signal_vip(signal) -> str:
	"""Format signal for VIP tier: Maximum edge & transparency.
	
	Attributes:
	- Fewer but highest-quality signals (score-filtered)
	- 3+ TP levels
	- Full confidence score (0-100)
	- Confluence breakdown
	- Market regime info
	- Invalidation levels
	- Full update alerts
	- NO-TRADE alerts
	- Weekly performance summary
	- Priority delivery
	- Purpose: High-value users, institutional-style
	"""
	ref = signal.get("signal_id") or signal.get("id")
	ref_short = str(ref)[:8] if ref else "N/A"
	
	tp_levels = signal.get('tp_levels', [])
	score = signal.get('score', 0)
	session = signal.get('session', '')
	regime = signal.get('regime', '')
	confluence_count = signal.get('confluence_count', 0)
	confluence_total = signal.get('confluence_total', 5)
	rr_ratio = signal.get('rr_ratio', 0)
	strategy = signal.get('strategy_name') or signal.get('strategy')
	
	msg = f"""\
🚀 BUY SIGNAL — VIP

Asset: {signal.get('asset')}
Timeframe: {signal.get('timeframe')}
"""
	
	if session:
		msg += f"Session: {session}\n"
	if regime:
		msg += f"Market Regime: {regime}\n"
	
	msg += f"""
Entry Zone: {signal.get('entry')}
Stop Loss: {signal.get('stop_loss')}

"""
	
	# All 3 TP levels for VIP
	if tp_levels and len(tp_levels) >= 3:
		msg += f"TP1: {tp_levels[0]}\n"
		msg += f"TP2: {tp_levels[1]}\n"
		msg += f"TP3: {tp_levels[2]}\n"
	else:
		msg += f"TP: {signal.get('take_profit')}\n"
	
	# Full score breakdown
	msg += f"""
📊 Confluence Score: {int(score)} / 100
🔥 Confidence: {'VERY HIGH' if score >= 80 else ('HIGH' if score >= 65 else 'MEDIUM')}
"""
	
	# HTF Bias
	htf_bias = signal.get('htf_bias', {})
	if isinstance(htf_bias, dict):
		bias_str = htf_bias.get('bias', 'NEUTRAL')
		msg += f"📈 HTF Bias: {bias_str}\n"
	
	# Risk-Reward ratio
	if rr_ratio and rr_ratio > 0:
		msg += f"📊 Risk–Reward: 1 : {rr_ratio:.1f}\n"
	
	# Invalidation levels
	invalid_price = signal.get('invalid_if_price')
	if invalid_price:
		msg += f"""
❌ Invalidation:
• Close below {invalid_price}
"""
	
	# Trading logic / reasoning
	if signal.get('technical_reason'):
		msg += f"""
🧠 Trade Logic:
• {signal.get('technical_reason')}
"""
	
	msg += f"""
📌 Signal ID: {ref_short}
📈 Strategy: {strategy or 'Multi-Strategy'}

📋 (use /outcome {ref_short} WIN/LOSS/CANCEL to track result)
"""
	return msg

def format_signal_admin(signal) -> str:
	"""Format signal for ADMIN/OWNER: Everything.
	
	Same as VIP but with additional internal information.
	"""
	vip_msg = format_signal_vip(signal)
	
	# Add admin-specific info
	admin_info = f"""

═══ ADMIN INFO ═══
Score: {signal.get('score')}/100
ML Prob: {signal.get('ml_probability', 'N/A')}
Confluence: {signal.get('confluence_count', 0)}/{signal.get('confluence_total', 5)}
Contributors: {', '.join(signal.get('contributors', [])[:3])}
Created: {signal.get('created_at', 'N/A')}
"""
	return vip_msg + admin_info

def format_signal_update_tp_hit(signal, tp_number: int) -> str:
	"""Format TP HIT update alert."""
	asset = signal.get('asset', 'UNKNOWN')
	ref = signal.get('signal_id', 'N/A')
	ref_short = str(ref)[:8]
	
	msg = f"""\
📢 UPDATE — {asset}

✅ TP{tp_number} HIT
🔒 Consider moving SL to breakeven
"""
	return msg

def format_signal_no_trade_alert() -> str:
	"""Format NO-TRADE alert for VIP."""
	msg = """\
⛔ NO TRADE ZONE — VIP

Market Conditions:
• Low volume
• Choppy structure
• Poor risk-to-reward

📉 Capital preservation mode active
"""
	return msg

def format_performance_summary_vip(stats: dict) -> str:
	"""Format weekly performance summary for VIP."""
	msg = f"""\
📊 WEEKLY PERFORMANCE — VIP

Signals Delivered: {stats.get('total_signals', 0)}
Winning Trades: {stats.get('wins', 0)} ({stats.get('win_rate', 0):.1f}%)
Avg R/Reward: {stats.get('avg_rr', 0):.2f}:1
Best Asset: {stats.get('best_asset', 'N/A')}
Best Timeframe: {stats.get('best_tf', 'N/A')}

Capital Gained: {stats.get('profit_pct', 0):.2f}%
"""
	return msg

def format_signal(signal, display_tier: str | None = None, limited: bool = False, user_tier: str | None = None, signals_sent_today: int = 0, daily_limit: int = 2):
	"""
	Format a signal for Telegram with tier-appropriate detail.

	All signal formatting must use this function, which enforces the GOLDEN RULE:
	  - FREE: Entry shown but SL/TP locked (2 signals/day, score 70%+)
	  - PREMIUM: Full details (20 signals/day, score 55%+)
	  - VIP: Everything + extras (unlimited, score 45%+)
	  - ADMIN/OWNER: Everything VIP gets + admin info

	This function routes to tier-specific formatters and applies per-tier quality gates.
	It is the only supported entry point for Telegram signal formatting.
	
	Args:
	    signal: Signal dictionary
	    display_tier: Tier to display (for backwards compatibility)
	    limited: Whether to show limited info (for backwards compatibility)
	    user_tier: User's actual tier
	    signals_sent_today: Number of signals sent today
	    daily_limit: Daily limit for the tier
	"""
	
	# Determine actual tier to show to user
	if not user_tier:
		user_tier = display_tier
	
	tier = _get_user_tier(user_tier)
	score = float(signal.get('score', 0) or 0)
	
	# Check if signal should be sent to this tier (quality gate)
	if not _should_send_signal_for_tier(tier, score):
		return None  # Signal filtered out for this tier
	
	# Route to tier-specific formatter with new parameters
	if tier == TIER_FREE:
		return format_signal_free_new(signal, signals_sent_today, daily_limit)
	elif tier == TIER_PREMIUM:
		return format_signal_premium_new(signal)
	elif tier == TIER_VIP:
		return format_signal_vip_new(signal)
	elif tier in {TIER_ADMIN, TIER_OWNER}:
		return format_signal_vip_new(signal)  # VIP format for admin/owner
	
	# Fallback to PREMIUM format
	return format_signal_premium_new(signal)

def _get_freshness_badge(signal: dict) -> str:
	"""Get data freshness badge based on data_age_seconds."""
	data_age = signal.get('data_age_seconds', 0)
	if data_age < 300:  # < 5 min
		return "🟢 Fresh"
	elif data_age < 1800:  # 5-30 min
		return "🟡 Recent"
	else:  # > 30 min
		return "🔴 Delayed"

def _get_signal_age_indicator(signal: dict) -> str:
	"""Get signal age indicator based on signal_age_seconds."""
	age_seconds = signal.get('signal_age_seconds')
	if age_seconds is None:
		return ""
	
	age_minutes = age_seconds / 60
	age_hours = age_seconds / 3600
	
	if age_seconds < 180:  # < 3 minutes
		return "⚡ Live"
	elif age_minutes < 10:
		return f"⏱️ {int(age_minutes)}m ago"
	elif age_hours < 1:
		return f"⏰ {int(age_minutes)}m ago"
	elif age_hours < 24:
		return f"⏰ {int(age_hours)}h ago"
	else:
		days = int(age_hours / 24)
		return f"📆 {days}d ago"

def _get_price_context(signal: dict) -> str:
	"""Get price context string showing current price vs entry."""
	current_price = signal.get('current_price')
	entry = signal.get('entry')
	price_distance_pct = signal.get('price_distance_pct')
	
	if current_price is None or entry is None:
		return ""
	
	try:
		entry_float = float(entry)
		direction = signal.get('direction', 'long').lower()
		
		# Format prices
		asset = signal.get('asset', '')
		current_str = _format_price(current_price, asset)
		entry_str = _format_price(entry_float, asset)
		
		# Price distance indicator
		if price_distance_pct is not None:
			abs_dist = abs(price_distance_pct)
			if abs_dist < 0.5:
				dist_emoji = "✅"  # Very close
			elif abs_dist < 2.0:
				dist_emoji = "⚠️"  # Moderate distance
			else:
				dist_emoji = "🚨"  # Far from entry
			
			return f"{dist_emoji} Current: {current_str} | Entry: {entry_str} ({price_distance_pct:+.2f}%)"
		else:
			return f"Current: {current_str} | Entry: {entry_str}"
	except Exception:
		return ""

def _get_score_explanation(signal: dict) -> str:
	"""Build score explanation based on indicator values."""
	explanations = []
	
	if signal.get('trend_ema'):
		explanations.append("Strong trend confirmation")
	if signal.get('volume_ratio', 0) > 1.5:
		explanations.append("Volume spike")
	if signal.get('rsi'):
		rsi = signal.get('rsi', 50)
		if rsi < 30:
			explanations.append("RSI oversold bounce")
		elif rsi > 70:
			explanations.append("RSI overbought reversal")
	if signal.get('adx_trend'):
		explanations.append("ADX trend strength")
	
	# Add support/resistance if available
	if signal.get('support_bounce'):
		explanations.append("Support bounce")
	
	if not explanations:
		return "Multiple confluence factors"
	
	return " + ".join(explanations)

def _format_price(price, asset: str = "") -> str:
	"""Format price with proper decimal places. Returns 'N/A' for None/zero/invalid."""
	if price is None:
		return "N/A"
	try:
		p = float(price)
	except Exception:
		s = str(price).strip()
		if s in ("", "N/A", "None", "nan", "0", "0.0"):
			return "N/A"
		return s
	if p == 0:
		return "N/A"
	# Crypto: 2 decimals for BTC/ETH, 4 for alts
	asset_upper = asset.upper()
	if "BTC" in asset_upper or "ETH" in asset_upper:
		return f"${p:,.2f}"
	elif "USD" in asset_upper and not asset_upper.endswith("USDT") and not asset_upper.endswith("USDC"):
		# Forex: 5 decimals
		return f"{p:.5f}"
	else:
		# Stocks, crypto alts: 4 decimals
		return f"${p:,.4f}"

def _parse_tp_list(tp_raw) -> list:
	"""Parse take_profit into a list of floats.

	Handles all storage formats:
	  - float/int           → [float_val]
	  - list of float/str   → [float, ...]
	  - JSON string         → parsed list
	  - Python repr string  → parsed list  (e.g. "['112.94']")
	  - plain float string  → [float_val]
	"""
	import json as _j
	if tp_raw is None:
		return []
	if isinstance(tp_raw, (int, float)):
		try:
			return [float(tp_raw)]
		except Exception:
			return []
	if isinstance(tp_raw, list):
		result = []
		for item in tp_raw:
			try:
				if isinstance(item, dict):
					# StrategySignal format: {'price': X, 'pct': Y, 'exit_percent': Z}
					price_val = item.get('price') or item.get('tp') or item.get('target')
					if price_val is not None:
						result.append(float(price_val))
				else:
					result.append(float(item))
			except (TypeError, ValueError):
				pass
		return [x for x in result if x > 0]
	# String forms
	s = str(tp_raw).strip()
	if not s or s in ('N/A', 'None', 'nan', ''):
		return []
	# Try proper JSON first
	try:
		data = _j.loads(s)
		if isinstance(data, list):
			return [float(x) for x in data if x is not None]
		return [float(data)]
	except Exception:
		pass
	# Python repr like "['112.94']" or "['112.94', '115.0']"
	try:
		s_clean = s.strip('[]').replace("'", '').replace('"', '')
		parts = [p.strip() for p in s_clean.split(',') if p.strip()]
		return [float(p) for p in parts]
	except Exception:
		pass
	# Plain float string
	try:
		return [float(s)]
	except Exception:
		return []

def _score_strength(score: float) -> str:
	"""Convert a numeric confidence score to a human-readable strength label."""
	if score >= 85:
		return "Very Strong"
	elif score >= 75:
		return "Strong"
	elif score >= 65:
		return "Moderate"
	elif score >= 55:
		return "Developing"
	else:
		return "Weak"


def format_signal_free_new(signal: dict, signals_sent_today: int = 0, daily_limit: int = 2) -> str:
	"""Format signal for FREE tier — professional template with locked SL/TP/RR."""
	asset      = signal.get('asset', 'UNKNOWN')
	direction  = (signal.get('direction') or 'LONG').upper()
	timeframe  = signal.get('timeframe', 'N/A')
	entry_raw  = signal.get('entry')
	confidence = int(float(signal.get('score') or 0))
	expires_at = signal.get('expires_at')
	ref        = signal.get('signal_id', 'N/A')

	dir_emoji  = "⬆️" if direction == "LONG" else "⬇️"
	strength   = _score_strength(confidence)

	entry_str  = _format_price(entry_raw, asset)

	expiry_str = "8h"
	if expires_at:
		expiry_str = _format_expiration(expires_at)

	ref_short = str(ref)[:8] if ref and ref != 'N/A' else 'N/A'
	used       = signals_sent_today
	limit_str  = str(daily_limit)

	return (
		"━━━━━━━━━━━━━━━━━━━━━\n"
		"🔔 SIGNAL ALERT — FREE\n"
		"━━━━━━━━━━━━━━━━━━━━━\n"
		f"📌 {asset} | {timeframe} | {direction} {dir_emoji}\n"
		f"🎯 Confidence: {confidence}/100 ({strength})\n"
		"\n"
		f"📍 Entry: {entry_str}\n"
		"🔒 Stop Loss: [PREMIUM]\n"
		"🔒 Take Profit: [PREMIUM]\n"
		"🔒 Risk/Reward: [PREMIUM]\n"
		"\n"
		f"📊 Signals Today: {used}/{limit_str}\n"
		f"⏰ Valid: {expiry_str}\n"
		"━━━━━━━━━━━━━━━━━━━━━\n"
		"🚀 /upgrade to unlock full details"
	)


def format_signal_premium_new(signal: dict) -> str:
	"""Format signal for PREMIUM tier — professional template."""
	from engine.signal_calculations import format_enhanced_signal_data

	asset      = signal.get('asset', 'UNKNOWN')
	direction  = (signal.get('direction') or 'LONG').upper()
	timeframe  = signal.get('timeframe', 'N/A')
	entry_raw  = signal.get('entry')
	stop_loss  = signal.get('stop_loss')
	confidence = int(float(signal.get('score') or 0))
	strategy   = signal.get('strategy_name') or signal.get('strategy', 'Multi-Strategy')
	regime     = signal.get('regime', 'N/A')
	expires_at = signal.get('expires_at')
	ref        = signal.get('signal_id', 'N/A')

	# RR: prefer stored value but fall back to None so enhanced calc can fill it
	rr_ratio   = signal.get('rr_ratio') or signal.get('rr_estimate') or None

	# Parse TP list from all possible storage formats
	_tp_raw    = signal.get('tp_levels') or signal.get('take_profit')
	tp_levels  = _parse_tp_list(_tp_raw)

	# Enhanced calculations
	enhanced         = format_enhanced_signal_data(signal)
	expected_profit  = enhanced.get('expected_profit_pct')
	expected_loss    = enhanced.get('expected_loss_pct')
	rr_calculated    = enhanced.get('risk_reward_ratio')

	if rr_calculated:
		rr_ratio = rr_calculated

	dir_emoji  = "⬆️" if direction == "LONG" else "⬇️"
	strength   = _score_strength(confidence)
	expiry_str = "8h"
	if expires_at:
		expiry_str = _format_expiration(expires_at)

	ref_short  = str(ref)[:8] if ref and ref != 'N/A' else 'N/A'
	entry_str  = _format_price(entry_raw, asset)
	sl_str     = _format_price(stop_loss, asset)

	# TP lines
	tp_lines = ""
	if len(tp_levels) >= 2:
		tp_lines = (
			f"🎯 TP1: {_format_price(tp_levels[0], asset)}\n"
			f"🎯 TP2: {_format_price(tp_levels[1], asset)}\n"
		)
	elif len(tp_levels) == 1:
		tp_lines = f"🎯 Take Profit: {_format_price(tp_levels[0], asset)}\n"
	else:
		tp_lines = "🎯 Take Profit: N/A\n"

	rr_str = f"1:{rr_ratio:.1f}" if rr_ratio else "N/A"

	msg = (
		"━━━━━━━━━━━━━━━━━━━━━━━━\n"
		"⭐ SIGNAL ALERT — PREMIUM\n"
		"━━━━━━━━━━━━━━━━━━━━━━━━\n"
		f"📌 {asset} | {timeframe} | {direction} {dir_emoji}\n"
		f"🎯 Confidence: {confidence}/100 — {strength}\n"
		"\n"
		f"📍 Entry: {entry_str}\n"
		f"🛡️ Stop Loss: {sl_str}\n"
	)
	msg += tp_lines
	msg += (
		f"📊 Risk/Reward: {rr_str}\n"
		"\n"
		f"📈 Strategy: {strategy}\n"
		f"📉 Regime: {regime}\n"
		f"⏰ Expires: {expiry_str}\n"
	)

	if expected_profit is not None:
		msg += f"📈 Expected Profit: +{expected_profit:.2f}%\n"
	if expected_loss is not None:
		loss_display = expected_loss if expected_loss < 0 else -abs(expected_loss)
		msg += f"📉 Max Loss: {loss_display:.2f}%\n"

	msg += (
		"\n"
		f"🔖 Ref: SIG-{ref_short}\n"
		f"📋 Track: /outcome {ref_short}\n"
		"━━━━━━━━━━━━━━━━━━━━━━━━"
	)
	return msg


def format_signal_vip_new(signal: dict) -> str:
	"""Format signal for VIP tier — professional template with all extras."""
	from engine.signal_calculations import format_enhanced_signal_data

	asset      = signal.get('asset', 'UNKNOWN')
	direction  = (signal.get('direction') or 'LONG').upper()
	timeframe  = signal.get('timeframe', 'N/A')
	entry_raw  = signal.get('entry')
	stop_loss  = signal.get('stop_loss')
	confidence = int(float(signal.get('score') or 0))
	strategy   = signal.get('strategy_name') or signal.get('strategy', 'Multi-Strategy')
	regime     = signal.get('regime', 'N/A')
	expires_at = signal.get('expires_at')
	ref        = signal.get('signal_id', 'N/A')
	htf_bias   = signal.get('htf_bias', 'N/A')
	tech_reason = signal.get('technical_reason') or signal.get('trade_logic') or 'Multi-confluence setup'
	entry_zone_low  = signal.get('entry_zone_low')
	entry_zone_high = signal.get('entry_zone_high')

	# RR: prefer stored value but fall back to None so enhanced calc can fill it
	rr_ratio    = signal.get('rr_ratio') or signal.get('rr_estimate') or None

	# Multiple TPs
	_tp_raw     = signal.get('tp_levels') or signal.get('take_profit')
	tp_levels   = _parse_tp_list(_tp_raw)

	# Confluence data
	conf_count  = signal.get('confluence_vote_count') or signal.get('confluence_count') or signal.get('confluence')
	conf_total  = signal.get('confluence_total') or 15
	conf_drivers = signal.get('confluence_drivers') or []

	# Enhanced calculations
	enhanced         = format_enhanced_signal_data(signal)
	expected_profit  = enhanced.get('expected_profit_pct')
	expected_loss    = enhanced.get('expected_loss_pct')
	rr_calculated    = enhanced.get('risk_reward_ratio')

	if rr_calculated:
		rr_ratio = rr_calculated

	dir_emoji  = "⬆️" if direction == "LONG" else "⬇️"
	dir_word   = "above" if direction == "SHORT" else "below"
	strength   = _score_strength(confidence)
	expiry_str = "8h"
	if expires_at:
		expiry_str = _format_expiration(expires_at)

	ref_short  = str(ref)[:8] if ref and ref != 'N/A' else 'N/A'
	sl_str     = _format_price(stop_loss, asset)
	rr_str     = f"1:{rr_ratio:.1f}" if rr_ratio else "N/A"

	# Entry zone line
	try:
		if entry_zone_low and entry_zone_high:
			ez_lo = float(entry_zone_low)
			ez_hi = float(entry_zone_high)
			if abs(ez_hi - ez_lo) > abs(ez_lo) * 0.0001:
				entry_line = f"📍 Entry Zone: {_format_price(ez_lo, asset)} – {_format_price(ez_hi, asset)}"
			else:
				entry_line = f"📍 Entry: {_format_price(entry_raw, asset)}"
		else:
			entry_line = f"📍 Entry: {_format_price(entry_raw, asset)}"
	except Exception:
		entry_line = f"📍 Entry: {_format_price(entry_raw, asset)}"

	# TP lines
	tp_lines = ""
	if len(tp_levels) >= 3:
		tp_lines = (
			f"🎯 TP1: {_format_price(tp_levels[0], asset)}\n"
			f"🎯 TP2: {_format_price(tp_levels[1], asset)}\n"
			f"🎯 TP3: {_format_price(tp_levels[2], asset)}\n"
		)
	elif len(tp_levels) == 2:
		tp_lines = (
			f"🎯 TP1: {_format_price(tp_levels[0], asset)}\n"
			f"🎯 TP2: {_format_price(tp_levels[1], asset)}\n"
		)
	elif len(tp_levels) == 1:
		tp_lines = f"🎯 TP1: {_format_price(tp_levels[0], asset)}\n"
	else:
		tp_lines = "🎯 Take Profit: N/A\n"

	# Confluence line
	conf_str = ""
	if conf_count is not None:
		try:
			conf_str = f"\n🧠 Confluence: {int(conf_count)}/{int(conf_total)}"
		except Exception:
			conf_str = ""

	# Drivers line
	drivers_str = ""
	if conf_drivers:
		try:
			drivers_str = f"\n💡 Drivers: {', '.join(str(d) for d in conf_drivers[:3])}"
		except Exception:
			drivers_str = ""

	# Invalidation price: SL price as the level to watch
	try:
		invalid_price = _format_price(stop_loss, asset)
		invalid_line = f"\n❌ Invalidation: Close {dir_word} {invalid_price}"
	except Exception:
		invalid_line = ""

	msg = (
		"━━━━━━━━━━━━━━━━━━━━━━━\n"
		"💎 SIGNAL ALERT — VIP\n"
		"━━━━━━━━━━━━━━━━━━━━━━━\n"
		f"📌 {asset} | {timeframe} | {direction} {dir_emoji}\n"
		f"🔥 Confidence: {confidence}/100 — {strength}\n"
		"\n"
		f"{entry_line}\n"
		f"🛡️ Stop Loss: {sl_str}\n"
	)
	msg += tp_lines
	msg += (
		f"📊 Risk/Reward: {rr_str}\n"
		"\n"
		f"📈 HTF Bias: {htf_bias}\n"
	)
	msg += conf_str + drivers_str + "\n"
	msg += (
		f"📉 Market Regime: {regime}\n"
		f"📈 Strategy: {strategy}\n"
		f"\n🧠 Trade Logic: {tech_reason}"
	)
	msg += invalid_line + "\n"

	if expected_profit is not None:
		msg += f"\n📈 Expected Profit: +{expected_profit:.2f}%"
	if expected_loss is not None:
		loss_display = expected_loss if expected_loss < 0 else -abs(expected_loss)
		msg += f"\n📉 Max Loss: {loss_display:.2f}%"

	msg += (
		f"\n⏰ Expires: {expiry_str}\n"
		"\n"
		f"🔖 Ref: SIG-{ref_short}\n"
		f"📋 Track: /outcome {ref_short}\n"
		"━━━━━━━━━━━━━━━━━━━━━━━"
	)
	return msg

def format_signal_legacy(signal, display_tier: str | None = None, limited: bool = False):
	"""DEPRECATED: Legacy format_signal function. Use new tier-based formatters instead.
	
	This function is kept for backwards compatibility only.
	New code should use format_signal() with user_tier parameter.
	"""
	# Redirect to new format_signal
	return format_signal(signal, display_tier=display_tier, limited=limited, user_tier=display_tier)


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
