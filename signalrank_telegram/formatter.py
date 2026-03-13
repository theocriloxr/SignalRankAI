from engine.tier_notifications import TierNotificationManager
from datetime import datetime, timezone
import os
from core.tier_constants import TIER_SCORE_THRESHOLDS

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
	try:
		min_score = float(TIER_SCORE_THRESHOLDS.get(tier, 70) or 70)
	except Exception:
		min_score = 70.0
	return float(score or 0) >= min_score

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
	"""Format price with proper decimal places."""
	try:
		p = float(price)
		# Crypto: 2 decimals for BTC, 4 for alts
		if 'BTC' in asset.upper() or 'ETH' in asset.upper():
			return f"${p:,.2f}"
		elif 'USD' in asset.upper():
			# Forex: 4-5 decimals
			return f"{p:.5f}"
		else:
			# Stocks and alts: 4 decimals
			return f"${p:,.4f}"
	except Exception as e:
		import logging
		logging.debug(f"[formatter] Failed to format price {price}: {e}")
		return str(price)

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

def format_signal_free_new(signal: dict, signals_sent_today: int = 0, daily_limit: int = 2) -> str:
	"""Format signal for FREE tier with locked fields."""
	asset = signal.get('asset', 'UNKNOWN')
	direction = signal.get('direction', 'LONG').upper()
	timeframe = signal.get('timeframe', 'N/A')
	entry = signal.get('entry', 'N/A')
	confidence = int(signal.get('score', 0))
	remaining = max(0, int(daily_limit) - int(signals_sent_today))
	
	direction_emoji = "⬆️" if direction == "LONG" else "⬇️"
	
	# Signal age indicator
	age_indicator = _get_signal_age_indicator(signal)
	
	lines = [
		"┏━━━━━━━━━━ SIGNAL ALERT ━━━━━━━━━━┓",
		"┃ TIER: FREE",
	]
	if age_indicator:
		lines.append(f"┃ {age_indicator}")
	lines += [
		"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
		f"┃ Asset: {asset}",
		f"┃ Direction: {direction} {direction_emoji}",
		f"┃ Timeframe: {timeframe}",
		f"┃ Entry: {_format_price(entry, asset)}",
		f"┃ Confidence: {confidence}/100",
		"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
		"┃ Target: 🔒 Premium",
		"┃ Stop Loss: 🔒 Premium",
		"┃ R/R: 🔒 Premium",
		"┃ Risk: 🔒 Premium",
		"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
		f"┃ Signals left today: {remaining}/{daily_limit}",
		"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
		"/upgrade to unlock full details",
	]
	return "\n".join(lines)

def format_signal_premium_new(signal: dict) -> str:
	"""Format signal for PREMIUM tier with full details and enhanced data."""
	from engine.signal_calculations import format_enhanced_signal_data
	
	asset = signal.get('asset', 'UNKNOWN')
	direction = signal.get('direction', 'LONG').upper()
	timeframe = signal.get('timeframe', 'N/A')
	entry = signal.get('entry', 'N/A')
	stop_loss = signal.get('stop_loss', 'N/A')
	take_profit = signal.get('take_profit', 'N/A')
	rr_ratio = signal.get('rr_ratio')
	if rr_ratio in (0, 0.0, "0", "0.0"):
		rr_ratio = None
	if rr_ratio is None:
		rr_ratio = signal.get('rr_estimate')
		if rr_ratio in (0, 0.0, "0", "0.0"):
			rr_ratio = None
	confidence = int(signal.get('score', 0))
	strategy = signal.get('strategy_name') or signal.get('strategy', 'Multi-Strategy')
	regime = signal.get('regime', 'N/A')
	expires_at = signal.get('expires_at')
	ref = signal.get('signal_id', 'N/A')
	
	# Get enhanced data
	enhanced = format_enhanced_signal_data(signal)
	expected_profit = enhanced.get('expected_profit_pct')
	expected_loss = enhanced.get('expected_loss_pct')
	rr_calculated = enhanced.get('risk_reward_ratio')
	signal_age = enhanced.get('signal_age_minutes')
	price_indicator = enhanced.get('price_status_indicator', 'ℹ️')
	current_price = signal.get('current_price')
	
	# Use calculated RR if available
	if rr_calculated:
		rr_ratio = rr_calculated
	
	direction_emoji = "⬆️" if direction == "LONG" else "⬇️"
	
	# Format expiration
	expiry_str = "8h"
	if expires_at:
		expiry_str = _format_expiration(expires_at)
	
	# Signal age indicator
	age_indicator = _get_signal_age_indicator(signal)
	
	# Price context
	price_context = _get_price_context(signal)
	
	# Build message with enhanced data
	lines = [
		"┏━━━━━━━━━━ SIGNAL ALERT ━━━━━━━━━━┓",
		"┃ TIER: PREMIUM",
	]
	if age_indicator:
		lines.append(f"┃ {age_indicator}")
	lines += [
		"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
		f"┃ Asset: {asset}",
		f"┃ Direction: {direction} {direction_emoji}",
		f"┃ Timeframe: {timeframe}",
		f"┃ Entry: {_format_price(entry, asset)}",
	]
	if price_context:
		lines.append(f"┃ {price_context}")
	elif current_price:
		lines.append(f"┃ Current: {_format_price(current_price, asset)} {price_indicator}")
	
	_prem_tp = _parse_tp_list(take_profit)
	lines.append("┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫")
	lines.append(f"┃ Stop Loss: {_format_price(stop_loss, asset)}")
	if len(_prem_tp) >= 2:
		lines.append(f"┃ Target 1: {_format_price(_prem_tp[0], asset)}")
		lines.append(f"┃ Target 2: {_format_price(_prem_tp[1], asset)}")
	elif len(_prem_tp) == 1:
		lines.append(f"┃ Target: {_format_price(_prem_tp[0], asset)}")
	else:
		lines.append("┃ Target: N/A")

	# Add profit/loss expectations
	if expected_profit is not None:
		lines.append(f"┃ Expected Profit: +{expected_profit:.2f}%")
	if expected_loss is not None:
		loss_display = expected_loss if expected_loss < 0 else -abs(expected_loss)
		lines.append(f"┃ Expected Loss: {loss_display:.2f}%")

	# Compute RR if still missing
	if rr_ratio is None:
		try:
			_entry = float(entry)
			_sl = float(stop_loss)
			_tp0 = float(_prem_tp[0]) if _prem_tp else None
			if _tp0 is not None and _entry and _sl:
				_rr = abs(_tp0 - _entry) / max(1e-9, abs(_entry - _sl))
				rr_ratio = _rr
		except Exception:
			rr_ratio = None
	if rr_ratio is not None:
		lines.append(f"┃ R/R: 1:{float(rr_ratio):.1f}")
	else:
		lines.append("┃ R/R: N/A")
	lines.append(f"┃ Confidence: {confidence}/100")
	
	# Add pips for FX pairs
	pips_to_tp = enhanced.get('pips_to_tp')
	pips_to_sl = enhanced.get('pips_to_sl')
	if pips_to_tp:
		lines.append(f"┃ Pips: TP {pips_to_tp:.1f} | SL {pips_to_sl:.1f}")
	
	lines += [
		"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
		f"┃ Strategy: {strategy}",
		f"┃ Regime: {regime}",
		f"┃ Expires: {expiry_str}",
	]

	# 🧠 AI Confluence block (injected when available from confluence engine)
	_cv  = signal.get('confluence_vote_count')
	_ct  = signal.get('confluence_total') or 15
	_cdr = signal.get('confluence_drivers') or []
	if _cv is not None:
		lines.append(f"┃ AI Confluence: {int(_cv)}/{int(_ct)} agree")
		if _cdr:
			lines.append(f"┃ Drivers: {', '.join(str(d) for d in _cdr[:3])}")

	# Add signal age if available
	if signal_age is not None:
		lines.append(f"┃ Age: {signal_age} min ago")

	lines += [
		"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
		f"┃ Ref: SIG-{str(ref)[:8]}",
		"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
	]

	return "\n".join(lines)

def format_signal_vip_new(signal: dict) -> str:
	"""Format signal for VIP tier with everything + extras and enhanced data."""
	from engine.signal_calculations import format_enhanced_signal_data
	
	asset = signal.get('asset', 'UNKNOWN')
	direction = signal.get('direction', 'LONG').upper()
	timeframe = signal.get('timeframe', 'N/A')
	entry = signal.get('entry', 'N/A')
	stop_loss = signal.get('stop_loss', 'N/A')
	
	# Multiple TPs — parse robustly from tp_levels or take_profit (handles DB string, list, float)
	_tp_raw = signal.get('tp_levels') or signal.get('take_profit')
	tp_levels = _parse_tp_list(_tp_raw)

	rr_ratio = signal.get('rr_ratio')
	if rr_ratio in (0, 0.0, "0", "0.0"):
		rr_ratio = None
	if rr_ratio is None:
		rr_ratio = signal.get('rr_estimate')
		if rr_ratio in (0, 0.0, "0", "0.0"):
			rr_ratio = None
	confidence = int(signal.get('score', 0))
	ml_probability = signal.get('ml_probability', 0)
	confluence = signal.get('confluence_count', 0) or signal.get('confluence', 0)
	strategy = signal.get('strategy_name') or signal.get('strategy', 'Multi-Strategy')
	regime = signal.get('regime', 'N/A')
	expires_at = signal.get('expires_at')
	ref = signal.get('signal_id', 'N/A')
	entry_zone_low = signal.get('entry_zone_low', entry)
	entry_zone_high = signal.get('entry_zone_high', entry)
	
	# Get enhanced data
	enhanced = format_enhanced_signal_data(signal)
	expected_profit = enhanced.get('expected_profit_pct')
	expected_loss = enhanced.get('expected_loss_pct')
	rr_calculated = enhanced.get('risk_reward_ratio')
	suggested_position = enhanced.get('suggested_position_size')
	signal_age = enhanced.get('signal_age_minutes')
	price_indicator = enhanced.get('price_status_indicator', 'ℹ️')
	current_price = signal.get('current_price')
	
	# Use calculated RR if available
	if rr_calculated:
		rr_ratio = rr_calculated
	
	direction_emoji = "⬆️" if direction == "LONG" else "⬇️"
	
	# Format expiration
	expiry_str = "8h"
	if expires_at:
		expiry_str = _format_expiration(expires_at)
	
	# Freshness badge
	freshness = _get_freshness_badge(signal)
	
	# Signal age indicator
	age_indicator = _get_signal_age_indicator(signal)
	
	# Price context
	price_context = _get_price_context(signal)
	
	# Score explanation
	score_explanation = _get_score_explanation(signal)

	# Entry zone: only show low–high range if they differ meaningfully (>0.01%)
	try:
		_ez_lo_f, _ez_hi_f = float(entry_zone_low), float(entry_zone_high)
		_entry_zone_str = (
			f"Entry Zone: {_format_price(_ez_lo_f, asset)} – {_format_price(_ez_hi_f, asset)}\n"
			if abs(_ez_hi_f - _ez_lo_f) > abs(_ez_lo_f) * 0.0001 else ""
		)
	except Exception:
		_entry_zone_str = ""

	lines = [
		"┏━━━━━━━━━━ SIGNAL ALERT ━━━━━━━━━━┓",
		"┃ TIER: VIP",
	]
	if age_indicator:
		lines.append(f"┃ {age_indicator}")
	lines += [
		"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
		f"┃ Asset: {asset}",
		f"┃ Direction: {direction} {direction_emoji}",
		f"┃ Timeframe: {timeframe}",
	]
	if _entry_zone_str:
		lines.append(f"┃ {_entry_zone_str.strip()}")
	lines.append(f"┃ Entry: {_format_price(entry, asset)}")
	if price_context:
		lines.append(f"┃ {price_context}")
	elif current_price:
		lines.append(f"┃ Current: {_format_price(current_price, asset)} {price_indicator}")
	lines.append("┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫")
	lines.append(f"┃ Stop Loss: {_format_price(stop_loss, asset)}")
	
	# Add multiple TPs
	if len(tp_levels) >= 3:
		lines.append(f"┃ TP1: {_format_price(tp_levels[0], asset)} (33%)")
		lines.append(f"┃ TP2: {_format_price(tp_levels[1], asset)} (33%)")
		lines.append(f"┃ TP3: {_format_price(tp_levels[2], asset)} (34%)")
	elif len(tp_levels) == 2:
		lines.append(f"┃ TP1: {_format_price(tp_levels[0], asset)} (50%)")
		lines.append(f"┃ TP2: {_format_price(tp_levels[1], asset)} (50%)")
	elif len(tp_levels) == 1:
		lines.append(f"┃ Target: {_format_price(tp_levels[0], asset)}")
	else:
		lines.append("┃ Target: N/A")
	
	# Add profit/loss expectations
	if expected_profit is not None:
		lines.append(f"┃ Expected Profit: +{expected_profit:.2f}%")
	if expected_loss is not None:
		loss_display = expected_loss if expected_loss < 0 else -abs(expected_loss)
		lines.append(f"┃ Expected Loss: {loss_display:.2f}%")

	# Compute RR if still missing
	if rr_ratio is None:
		try:
			_entry = float(entry)
			_sl = float(stop_loss)
			_tp0 = float(tp_levels[0]) if tp_levels else None
			if _tp0 is not None and _entry and _sl:
				_rr = abs(_tp0 - _entry) / max(1e-9, abs(_entry - _sl))
				rr_ratio = _rr
		except Exception:
			rr_ratio = None
	if rr_ratio is not None:
		lines.append(f"┃ R/R: 1:{float(rr_ratio):.1f}")
	else:
		lines.append("┃ R/R: N/A")
	lines.append(f"┃ Confidence: {confidence}/100")
	
	if ml_probability:
		lines.append(f"┃ ML Probability: {int(ml_probability)}%")
	
	if confluence:
		lines.append(f"┃ Confluence: {int(confluence)}%")
	
	# Add pips for FX pairs
	pips_to_tp = enhanced.get('pips_to_tp')
	pips_to_sl = enhanced.get('pips_to_sl')
	if pips_to_tp:
		lines.append(f"┃ Pips: TP {pips_to_tp:.1f} | SL {pips_to_sl:.1f}")
	
	# Add suggested position size
	if suggested_position:
		lines.append(f"┃ Suggested Size: {suggested_position:.2f} units (1% risk)")
	
	lines += [
		"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
		f"┃ Strategy: {strategy}",
		f"┃ Regime: {regime}",
		f"┃ Score: {score_explanation}",
		f"┃ Freshness: {freshness}",
		f"┃ Expires: {expiry_str}",
	]

	# 🧠 AI Confluence block (injected when available from confluence engine)
	_cv  = signal.get('confluence_vote_count')
	_ct  = signal.get('confluence_total') or 15
	_cdr = signal.get('confluence_drivers') or []
	if _cv is not None:
		_cv_int = int(_cv)
		_ct_int = int(_ct)
		_strength = "Strong" if _cv_int >= 12 else ("Moderate" if _cv_int >= 10 else "Weak")
		lines.append(f"┃ AI Confluence: {_cv_int}/{_ct_int} ({_strength})")
		if _cdr:
			lines.append(f"┃ Drivers: {', '.join(str(d) for d in _cdr[:3])}")
		_lv = signal.get('long_votes', 0)
		_sv = signal.get('short_votes', 0)
		if _lv or _sv:
			lines.append(f"┃ Votes: ⬆️{_lv} LONG / ⬇️{_sv} SHORT")

	# Add signal age if available
	if signal_age is not None:
		lines.append(f"┃ Age: {signal_age} min ago")

	lines += [
		"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫",
		f"┃ Ref: SIG-{str(ref)[:8]}",
		"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
	]

	return "\n".join(lines)

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
