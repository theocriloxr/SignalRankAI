# /pricing command
import os
import logging
import inspect
import socket
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from core.redis_state import state
from .access import resolve_user_tier


_audit_logger = logging.getLogger("audit")

_BOOT_TS = datetime.now(timezone.utc).isoformat()


async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if update.message is None or update.effective_user is None:
		return
	# Owner-only (avoid exposing deployment fingerprints publicly)
	if _effective_tier(update.effective_user.id) != "OWNER":
		return
	# Non-sensitive fingerprint to confirm which build is running.
	mode = (os.getenv("RUN_MODE") or "engine").strip().lower()
	lines = [
		"SignalRankAI /version",
		f"boot_utc: {_BOOT_TS}",
		f"run_mode: {mode}",
		f"host: {socket.gethostname()}",
		f"railway_service: {os.getenv('RAILWAY_SERVICE_NAME')}",
		f"railway_env: {os.getenv('RAILWAY_ENVIRONMENT')}",
		f"railway_deployment: {os.getenv('RAILWAY_DEPLOYMENT_ID')}",
		f"git_sha: {os.getenv('RAILWAY_GIT_COMMIT_SHA')}",
	]
	await update.message.reply_text("\n".join(lines))


def _effective_tier(user_id: int) -> str:
	try:
		t = resolve_user_tier(user_id)
	except Exception:
		t = "FREE"
	try:
		if state.has_temp_owner_sync(user_id):
			return "OWNER"
	except Exception:
		pass
	return (t or "FREE").upper()


async def _public_guard(update: Update) -> bool:
	"""Return True if request should be blocked (kill-switch/rate-limit)."""
	if update.effective_user is None or update.message is None:
		return True
	user_id = update.effective_user.id
	# Kill-switch blocks signal-related actions globally
	try:
		if state.get_killswitch_sync().enabled:
			await update.message.reply_text("🚨 Signals are temporarily paused.")
			return True
	except Exception:
		pass
	# Rate limit public commands (30/min)
	try:
		if state.rate_limited_sync(user_id, limit=30, window_seconds=60):
			await update.message.reply_text("Rate limit exceeded. Please wait.")
			return True
	except Exception:
		pass
	return False


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if await _public_guard(update):
		return
	msg = (
		"🤖 SignalRankAI Commands\n\n"
		"🆓 FREE\n"
		"/start – Start\n"
		"/help – This menu\n"
		"/about – About SignalRankAI\n"
		"/faq – FAQs\n"
		"/disclaimer – Risk disclaimer\n"
		"/pricing – Pricing\n"
		"/upgrade – Subscribe\n"
		"/signals – Latest signals (limited for Free)\n"
		"/signal – Lookup a signal by reference (/signal <ref> or /signal all)\n"
		"/outcome – Check outcome by reference (/outcome <ref>)\n"
		"/invite – Invite friends\n"
		"/policy – Subscription & refund policy\n"
		"/refunds – Same as /policy\n"
		"/recap – Weekly recap\n"
		"/buy_extra_signals – Buy extra daily signals (Free-only, ₦300 each, 24h)\n\n"
		"🟡 PREMIUM (subscribers)\n"
		"/performance – Full performance stats\n"
		"/stats – Stats summary\n"
		"/history – Recent signal history\n"
		"/risk – Risk guidance\n"
		"/alerts – TP/SL + quiet hours\n\n"
		"🔴 VIP (subscribers)\n"
		"/elite – VIP feed\n"
		"/early – Early alerts\n"
		"/report – Reports\n\n"
		"📌 Notes\n"
		"• Signals are deduped per-user; repeats are suppressed.\n"
		"• Free users get delayed summaries unless extra signals are purchased.\n"
		"• Use /upgrade to activate Premium/VIP.\n\n"
		"⚠️ Educational only. Not financial advice. Trading involves risk."
	)
	if update.message is not None:
		await update.message.reply_text(msg)


async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	"""Show user's signals with tier-specific formatting.
	
	FREE: Show signals they received (delivered)
	PREMIUM/VIP: Show unresolved signals (ongoing trades)
	"""
	if await _public_guard(update):
		return
	user_id = update.effective_user.id
	tier = _effective_tier(user_id)

	# Owner and admin always get VIP format
	if tier.lower() in {"owner", "admin"}:
		tier = "VIP"

	signals_list: list[dict] = []
	
	# FREE tier: show delivered signals only - SHOW ALL SIGNALS SENT TODAY (NO LIMIT)
	if tier_rank(tier) < tier_rank("PREMIUM"):
		try:
			from db.session import ENGINE, get_session
			if ENGINE is not None:
				from db.pg_features import list_signals_sent_today
				async with get_session() as session:
					# Fetch ALL signals delivered to user today (no limit)
					rows = await list_signals_sent_today(session, telegram_user_id=int(user_id))
					signals_list = [
						{
							"signal_id": r.signal_id,
							"asset": r.asset,
							"timeframe": r.timeframe,
							"direction": r.direction,
							"entry": r.entry,
							"stop_loss": r.stop_loss,
							"take_profit": r.take_profit,
							"rr_ratio": r.rr_estimate,
							"score": r.score,
						}
						for r in rows
					]
		except Exception as e:
			_audit_logger.error(f"Error fetching delivered signals for {user_id}: {e}")
			signals_list = []
		
		if not signals_list:
			if update.message is not None:
				await update.message.reply_text("✅ No signals delivered today.")
			return
		
		# Show ALL signals for free users (removed the [:5] limit)
		total_signals = len(signals_list)
		lines = [f"🆓 Today's Signals ({total_signals} total)", ""]
		for i, s in enumerate(signals_list, 1):
			entry = float(s.get('entry') or 0)
			sig_id = s.get('signal_id', 'N/A')
			sig_id_short = sig_id[:8]
			lines.append(
				f"{i}. {s.get('asset')} {s.get('timeframe')} {s.get('direction').upper()}\n"
				f"   Reference: `{sig_id_short}...` | Entry: {entry:.4f}\n"
				f"   /outcome {sig_id_short}"
			)
		lines += ["", "💡 Use /outcome <reference> to check if you hit TP/SL", "👆 Upgrade to PREMIUM for full signal details."]
		if update.message is not None:
			await update.message.reply_text("\n".join(lines))
		return
	
	# PREMIUM/VIP: show unresolved signals (ongoing trades)
	unresolved_signals: list[dict] = []
	try:
		from db.session import ENGINE, get_session
		if ENGINE is not None:
			from db.pg_features import list_unresolved_signals_for_user
			async with get_session() as session:
				rows = await list_unresolved_signals_for_user(session, telegram_user_id=int(user_id))
				unresolved_signals = [
					{
						"signal_id": r.signal_id,
						"asset": r.asset,
						"timeframe": r.timeframe,
						"direction": r.direction,
						"entry": r.entry,
						"stop_loss": r.stop_loss,
						"take_profit": r.take_profit,
						"rr_ratio": r.rr_estimate,
						"score": r.score,
						"confidence": getattr(r, 'confidence', 0.5),
						"regime": getattr(r, 'regime', 'NEUTRAL'),
						"strength": getattr(r, 'strength', 0.5),
						"ml_probability": getattr(r, 'ml_probability', 0.5),
						"strategy_name": r.strategy_name,
						"strategy_group": r.strategy_group,
						"created_at": r.created_at,
					}
					for r in rows
				]
	except Exception as e:
		_audit_logger.error(f"Error fetching unresolved signals for {user_id}: {e}")
		unresolved_signals = []

	if not unresolved_signals:
		if update.message is not None:
			await update.message.reply_text("✅ No unresolved signals. All trades resolved or archived.")
		return

	# PREMIUM/VIP: detailed formatting per tier - SHOW ALL UNRESOLVED SIGNALS (NO LIMIT)
	from .formatter import format_signal
	import json
	
	total_active = len(unresolved_signals)
	if update.message is not None and total_active > 0:
		await update.message.reply_text(f"📊 Your Active Signals ({total_active} unresolved):\n\n")
	
	for idx, s in enumerate(unresolved_signals, 1):
		try:
			# Ensure numeric fields are floats
			score = float(s.get('score') or 0)
			confidence = float(s.get('confidence') or 0.5)
			rr = float(s.get('rr_ratio') or 1.5)
			entry = float(s.get('entry') or 0)
			stop_loss = float(s.get('stop_loss') or 0)
			sig_id = s.get('signal_id', 'N/A')
			# Parse take_profit (JSON array) and get first value
			tp_raw = s.get('take_profit')
			try:
				if isinstance(tp_raw, str):
					tp_list = json.loads(tp_raw)
					take_profit = float(tp_list[0]) if tp_list else 0.0
				elif isinstance(tp_raw, list):
					take_profit = float(tp_raw[0]) if tp_raw else 0.0
				else:
					take_profit = float(tp_raw or 0)
			except Exception:
				take_profit = 0.0
			
			regime = s.get('regime', 'NEUTRAL')
			ml_prob = float(s.get('ml_probability') or 0.5)
			
			# Calculate entry/exit advice
			if s.get('direction', '').upper() == 'LONG':
				entry_advice = f"Buy on dip to {entry:.4f}"
				exit_advice = f"Take partial profit at {take_profit:.4f}, trail SL to {stop_loss:.4f}"
			else:
				entry_advice = f"Sell on rally to {entry:.4f}"
				exit_advice = f"Take partial profit at {take_profit:.4f}, trail SL to {stop_loss:.4f}"
			
			if tier in {"owner", "admin", "vip"}:
				# Full advice for VIP
				msg = (
					f"🟢 VIP Signal: {s.get('asset')} ({s.get('timeframe')})\n"
					f"ID: `{sig_id}`\n\n"
					f"Setup: {s.get('direction').upper()} {s.get('strategy_name')}\n"
					f"Regime: {regime} | **Score**: {score:.1f}/100\n\n"
					f"Entry: {entry:.4f}\n"
					f"SL: {stop_loss:.4f}\n"
					f"TP: {take_profit:.4f}\n"
					f"R/R: {rr:.2f}:1\n\n"
					f"Confidence: {confidence*100:.0f}% | ML: {ml_prob*100:.0f}%\n\n"
					f"📌 Entry Strategy: {entry_advice}\n"
					f"📌 Exit Strategy: {exit_advice}\n"
					f"📌 Risk: {stop_loss:.4f} - {entry:.4f} = {abs(entry - stop_loss):.4f} pips\n\n"
					f"📍 /outcome {sig_id[:8]} for current position"
				)
			else:
				# Limited advice for PREMIUM
				msg = (
					f"PREMIUM Signal: {s.get('asset')} ({s.get('timeframe')})\n"
					f"ID: `{sig_id}`\n\n"
					f"Setup: {s.get('direction').upper()}\n"
					f"Entry: {entry:.4f}\n"
					f"SL: {stop_loss:.4f}\n"
					f"TP: {take_profit:.4f}\n"
					f"Score: {score:.1f} | **R/R**: {rr:.2f}:1\n\n"
					f"📌 {entry_advice}\n"
					f"📌 {exit_advice}\n\n"
					f"📍 /outcome {sig_id[:8]} for current position"
				)
			
			if update.message is not None:
				await update.message.reply_text(msg)
		except Exception as e:
			_audit_logger.error(f"Error formatting signal for {user_id}: {e}")
			continue


async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	tier = _effective_tier(user_id)
	arg = (context.args[0] if context.args else "").strip() if context.args else ""
	if not arg:
		await update.message.reply_text("Usage: /signal <reference> OR /signal all")
		return

	def _as_float(v):
		try:
			return float(v)
		except Exception:
			return None

	def _parse_tp(tp_raw):
		if tp_raw is None:
			return None
		if isinstance(tp_raw, (int, float)):
			return float(tp_raw)
		s = str(tp_raw).strip()
		if not s:
			return None
		try:
			import json
			data = json.loads(s)
			if isinstance(data, list) and data:
				return float(data[0])
			if isinstance(data, (int, float)):
				return float(data)
		except Exception:
			pass
		try:
			return float(s)
		except Exception:
			return None

	def _is_crypto(symbol: str) -> bool:
		s = (symbol or "").upper().strip()
		return s.endswith("USDT") or s.endswith("USDC") or s.endswith("BUSD")

	def _binance_symbol(asset: str) -> str:
		a = (asset or "").upper().strip()
		# BTCUSDT -> BTC/USDT
		if a.endswith("USDT"):
			return a[:-4] + "/USDT"
		if a.endswith("USDC"):
			return a[:-4] + "/USDC"
		if a.endswith("BUSD"):
			return a[:-4] + "/BUSD"
		# fallback
		return a.replace("USD", "/USDT")

	def _binance_symbol_rest(asset: str) -> str:
		a = (asset or "").upper().strip()
		a = a.replace("/", "").replace("-", "")
		# Normalize USD suffix to USDT
		if a.endswith("USD") and not a.endswith("USDT"):
			a = a[:-3] + "USDT"
		return a

	def _current_price(asset: str) -> float | None:
		if not _is_crypto(asset):
			return None
		try:
			import requests
			# First try Binance (fast, direct) then fall back to CryptoCompare when
			# Binance is geo-blocked (HTTP 451) or otherwise unreachable.
			sym = _binance_symbol_rest(asset)
			if not sym:
				return None
			resp = requests.get(
				"https://api.binance.com/api/v3/ticker/price",
				params={"symbol": sym},
				timeout=8,
			)
			if resp.ok:
				payload = resp.json() if resp.ok else {}
				price = payload.get("price")
				return float(price) if price is not None else None

			# Fallback: CryptoCompare simple price endpoint.
			base = sym
			quote = "USDT"
			for q in ("USDT", "USDC", "BUSD", "USD"):
				if base.endswith(q) and len(base) > len(q):
					base = base[: -len(q)]
					quote = q
					break
			base = (base or "").upper().strip()
			quote = (quote or "").upper().strip()
			if not base or not quote:
				return None

			headers = {}
			api_key = (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip()
			if api_key:
				headers["authorization"] = f"Apikey {api_key}"

			url = "https://min-api.cryptocompare.com/data/price"
			# Ask for a few quotes; use the first available.
			params = {"fsym": base, "tsyms": ",".join([quote, "USDT", "USD", "USDC", "BUSD"])}
			resp2 = requests.get(url, params=params, headers=headers, timeout=10)
			if not resp2.ok:
				return None
			payload2 = resp2.json() if resp2.ok else {}
			if not isinstance(payload2, dict):
				return None
			for q in (quote, "USDT", "USD", "USDC", "BUSD"):
				try:
					v = payload2.get(q)
					if v is None:
						continue
					return float(v)
				except Exception:
					continue
			return None
		except Exception:
			return None

	def _position_advice(*, direction: str, entry: float, sl: float, tp: float, price: float) -> tuple[str, dict]:
		"""Return (advice_text, metrics)."""
		direction = (direction or "").lower().strip()
		risk = abs(entry - sl)
		reward = abs(tp - entry)
		metrics: dict = {"risk": risk, "reward": reward}
		if risk <= 0 or reward <= 0:
			return ("Manage risk carefully. Consider waiting for clearer conditions.", metrics)

		if direction == "long":
			pl_pct = ((price - entry) / entry) * 100.0
			progress = (price - entry) / (tp - entry) if (tp - entry) != 0 else 0.0
			dist_to_sl = (price - sl)
		else:
			pl_pct = ((entry - price) / entry) * 100.0
			progress = (entry - price) / (entry - tp) if (entry - tp) != 0 else 0.0
			dist_to_sl = (sl - price)

		metrics.update({"pl_pct": pl_pct, "progress": progress})
		near_sl = (dist_to_sl / risk) <= 0.2
		if progress >= 1.0:
			return ("✅ Target zone reached. Consider taking profit (full or partial) and managing trailing risk.", metrics)
		if progress >= 0.75:
			return ("📌 Close to TP. Consider partial take-profit and move SL to breakeven if your plan allows.", metrics)
		if progress >= 0.30:
			return ("⏳ In profit but not near TP yet. Consider waiting for full TP, or take partial if volatility is high.", metrics)
		# Not in meaningful profit
		if near_sl:
			return ("⚠️ Price is close to SL zone. Consider reducing exposure or exiting early to avoid a full SL hit.", metrics)
		return ("⏳ Still developing. Consider waiting; avoid moving SL further away.", metrics)

	# Postgres-backed lookup (required for per-user delivery protection)
	try:
		from db.session import ENGINE, get_session
		if ENGINE is None:
			raise RuntimeError("Postgres not configured")
		from db.pg_features import list_signals_sent_today, get_delivered_signal_by_ref
		from .formatter import format_signal, format_signal_free_limited

		if arg.lower() == "all":
			async with get_session() as session:
				rows = await list_signals_sent_today(session, telegram_user_id=int(user_id))
				await session.commit()
			if not rows:
				await update.message.reply_text("No signals delivered to you today.")
				return
			lines = ["📌 Today’s signals:", ""]
			for s in rows[:20]:
				ref = str(getattr(s, "signal_id", "") or "")
				lines.append(f"• {ref} — {s.asset} {s.timeframe} {s.direction}")
			await update.message.reply_text("\n".join(lines))
			return

		async with get_session() as session:
			sig = await get_delivered_signal_by_ref(session, telegram_user_id=int(user_id), ref=str(arg))
			oc = None
			if sig is not None:
				try:
					from db.pg_features import get_outcome_for_signal
					oc = await get_outcome_for_signal(session, str(sig.signal_id))
				except Exception:
					oc = None
			await session.commit()
		if sig is None:
			await update.message.reply_text("Signal not found (or not delivered to you).")
			return

		sig_dict = {
			"signal_id": sig.signal_id,
			"asset": sig.asset,
			"timeframe": sig.timeframe,
			"direction": sig.direction,
			"entry": sig.entry,
			"stop_loss": sig.stop_loss,
			"take_profit": sig.take_profit,
			"rr_ratio": getattr(sig, "rr_estimate", None),
			"score": sig.score,
			"regime": getattr(sig, "regime", None),
			"strength": getattr(sig, "strength", None),
			"strategy_name": getattr(sig, "strategy_name", None),
			"strategy_group": getattr(sig, "strategy_group", None),
		}
		# Enrich with outcome/live position (best-effort)
		entry = _as_float(sig_dict.get("entry"))
		sl = _as_float(sig_dict.get("stop_loss"))
		tp = _parse_tp(sig_dict.get("take_profit"))
		price = None
		advice_line = None
		position_lines: list[str] = []
		if oc is not None:
			status = str(getattr(oc, "status", "") or "").lower()
			r = getattr(oc, "r_multiple", None)
			pct = getattr(oc, "percent", None)
			label = "PROFIT" if status.startswith("tp") else ("LOSS" if status == "sl" else status.upper())
			position_lines.append(f"Outcome: {label} ({status})")
			if r is not None:
				position_lines.append(f"R-multiple: {float(r):.2f}R")
			if pct is not None:
				position_lines.append(f"Move: {float(pct):.2f}%")
			advice_line = "This signal has a recorded outcome."
		else:
			# Live estimate (crypto only)
			if entry is not None and sl is not None and tp is not None:
				price = _current_price(str(sig_dict.get("asset") or ""))
				if price is not None:
					adv, metrics = _position_advice(
						direction=str(sig_dict.get("direction") or ""),
						entry=float(entry),
						sl=float(sl),
						tp=float(tp),
						price=float(price),
					)
					position_lines.append(f"Current price: {price:.6g}")
					try:
						position_lines.append(f"P/L (est.): {float(metrics.get('pl_pct')):.2f}%")
					except Exception:
						pass
					try:
						position_lines.append(f"Progress to TP (est.): {max(0.0, min(1.0, float(metrics.get('progress')))) * 100.0:.0f}%")
					except Exception:
						pass
					advice_line = adv
				else:
					position_lines.append("Live position: unavailable right now.")
					advice_line = "Check later for a live update."

		if tier_rank(tier) < tier_rank("PREMIUM"):
			base = format_signal_free_limited(sig_dict)
			if position_lines or advice_line:
				base += "\n\n📍 Position (best-effort)\n" + "\n".join(position_lines)
				if advice_line:
					base += "\n\n🧠 Suggestion\n" + str(advice_line)
			await update.message.reply_text(base)
			return

		base = format_signal(sig_dict)
		if position_lines or advice_line:
			base += "\n\n📍 Position (best-effort)\n" + "\n".join(position_lines)
			if advice_line:
				base += "\n\n🧠 Suggestion\n" + str(advice_line)
		await update.message.reply_text(base)
		return
	except Exception:
		await update.message.reply_text("Signal lookup is temporarily unavailable.")
		return


async def outcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	arg = (context.args[0] if context.args else "").strip() if context.args else ""
	if not arg:
		await update.message.reply_text("Usage: /outcome <reference>")
		return

	try:
		from db.session import ENGINE, get_session
		if ENGINE is None:
			raise RuntimeError("Postgres not configured")
		from db.pg_features import get_delivered_signal_by_ref, get_outcome_for_signal, get_or_create_user
		from db.models import Signal, User
		from sqlalchemy import select
		import json
		import os
		
		async with get_session() as session:
			# Get user and their tier
			user = await get_or_create_user(session, telegram_user_id=int(user_id))
			user_tier = str(user.tier or "free").strip().lower()
			
			# Owner and admin always get VIP format
			if user_tier in {"owner", "admin"}:
				user_tier = "vip"
			sig = await get_delivered_signal_by_ref(session, telegram_user_id=int(user_id), ref=str(arg))
			
			# If signal not delivered to user, check if it exists at all
			if sig is None:
				# Try to find the signal by ref without delivery check
				ref = (arg or "").strip()
				query = select(Signal)
				if len(ref) >= 32:
					query = query.where(Signal.signal_id == ref)
				else:
					query = query.where(Signal.signal_id.like(f"{ref}%"))
				query = query.order_by(Signal.created_at.desc()).limit(1)
				
				res_undelivered = await session.execute(query)
				undelivered_sig = res_undelivered.scalars().first()
				
				if undelivered_sig is not None:
					await update.message.reply_text("⚠️ This is not your signal. You were not sent this trade.")
					return
				else:
					await update.message.reply_text("Signal not found.")
					return
			
			# Signal was delivered to user, now check for outcome
			oc = await get_outcome_for_signal(session, str(sig.signal_id))
			await session.commit()
		
		# If outcome exists, show it
		if oc is not None:
			status = str(getattr(oc, "status", "") or "").lower()
			r = getattr(oc, "r_multiple", None)
			pct = getattr(oc, "percent", None)
			label = "PROFIT" if status.startswith("tp") else ("LOSS" if status == "sl" else status.upper())
			lines = [
				"📣 Outcome",
				"",
				f"Reference: {sig.signal_id}",
				f"{sig.asset} {sig.timeframe} {sig.direction.upper()}",
				f"Result: {label} ({status})",
			]
			if r is not None:
				lines.append(f"R-multiple: {float(r):.2f}R")
			if pct is not None:
				lines.append(f"Move: {float(pct):.2f}%")
			await update.message.reply_text("\n".join(lines))
			return
		
		# If outcome not yet determined, show current signal details based on tier
		# Determine what to show based on tier
		try:
			vip_cut = float((os.getenv("VIP_SCORE_THRESHOLD") or "72").strip())
		except Exception:
			vip_cut = 72.0
		
		# Owner always gets VIP format
		if user_tier in {"owner", "admin"}:
			user_tier = "vip"
		
		show_levels = user_tier in {"vip", "premium"}
		show_strategy = user_tier in {"vip"}
		show_strength = user_tier in {"vip"}
		
		lines = ["🔄 Signal In Progress", ""]
		
		# Reference
		lines.append(f"Reference: {sig.signal_id}")
		
		# Basic info (all tiers)
		lines.extend([
			f"Asset: {sig.asset}",
			f"Timeframe: {sig.timeframe}",
			f"Direction: {sig.direction.upper()}",
		])
		
		# Levels and regime (premium+)
		if show_levels:
			lines.extend([
				f"Entry: {sig.entry}",
				f"Stop Loss: {sig.stop_loss}",
			])
			
			# Parse take_profit (JSON-encoded list)
			try:
				tp_list = json.loads(sig.take_profit) if isinstance(sig.take_profit, str) else sig.take_profit
				if isinstance(tp_list, list) and len(tp_list) > 0:
					for i, tp in enumerate(tp_list, 1):
						lines.append(f"Take Profit {i}: {tp}")
				else:
					lines.append(f"Take Profit: {sig.take_profit}")
			except Exception:
				lines.append(f"Take Profit: {sig.take_profit}")
			
			if sig.regime:
				lines.append(f"Regime: {sig.regime}")
		
		# Score (premium+ only, not FREE)
		if show_levels:
			lines.append("")
			lines.append(f"Score: {sig.score:.2f}")
		
		# RR Estimate (premium+)
		if show_levels and sig.rr_estimate is not None:
			lines.append(f"RR Estimate: {sig.rr_estimate:.2f}")
		
		# Strategy and strength (VIP+)
		if show_strategy:
			lines.append(f"Strategy: {sig.strategy_name}")
			if sig.strategy_group:
				lines.append(f"Group: {sig.strategy_group}")
		
		if show_strength and sig.strength is not None:
			lines.append(f"Strength: {sig.strength}")
		
		# Current position (live price and advice) - for all tiers
		lines.append("")
		lines.append("📍 Current Position")
		
		# Get live price and calculate position
		def _as_float(v):
			try:
				return float(v)
			except Exception:
				return None
		
		def _parse_tp(tp_raw):
			if tp_raw is None:
				return None
			if isinstance(tp_raw, (int, float)):
				return float(tp_raw)
			s = str(tp_raw).strip()
			if not s:
				return None
			try:
				data = json.loads(s)
				if isinstance(data, list) and data:
					return float(data[0])
				if isinstance(data, (int, float)):
					return float(data)
			except Exception:
				pass
			try:
				return float(s)
			except Exception:
				return None
		
		def _is_crypto(symbol: str) -> bool:
			s = (symbol or "").upper().strip()
			return s.endswith("USDT") or s.endswith("USDC") or s.endswith("BUSD")
		
		def _binance_symbol_rest(asset: str) -> str:
			a = (asset or "").upper().strip()
			a = a.replace("/", "").replace("-", "")
			if a.endswith("USD") and not a.endswith("USDT"):
				a = a[:-3] + "USDT"
			return a
		
		def _current_price(asset: str) -> float | None:
			if not _is_crypto(asset):
				return None
			try:
				import requests
				sym = _binance_symbol_rest(asset)
				if not sym:
					return None
				resp = requests.get(
					"https://api.binance.com/api/v3/ticker/price",
					params={"symbol": sym},
					timeout=8,
				)
				if resp.ok:
					payload = resp.json() if resp.ok else {}
					price = payload.get("price")
					return float(price) if price is not None else None
				
				# Fallback: CryptoCompare
				base = sym
				quote = "USDT"
				for q in ("USDT", "USDC", "BUSD", "USD"):
					if base.endswith(q) and len(base) > len(q):
						base = base[: -len(q)]
						quote = q
						break
				base = (base or "").upper().strip()
				quote = (quote or "").upper().strip()
				if not base or not quote:
					return None
				
				headers = {}
				api_key = (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip()
				if api_key:
					headers["authorization"] = f"Apikey {api_key}"
				
				url = "https://min-api.cryptocompare.com/data/price"
				params = {"fsym": base, "tsyms": ",".join([quote, "USDT", "USD", "USDC", "BUSD"])}
				resp2 = requests.get(url, params=params, headers=headers, timeout=10)
				if not resp2.ok:
					return None
				payload2 = resp2.json() if resp2.ok else {}
				if not isinstance(payload2, dict):
					return None
				for q in (quote, "USDT", "USD", "USDC", "BUSD"):
					try:
						v = payload2.get(q)
						if v is None:
							continue
						return float(v)
					except Exception:
						continue
				return None
			except Exception:
				return None
		
		def _position_advice(*, direction: str, entry: float, sl: float, tp: float, price: float) -> tuple[str, dict]:
			"""Return (advice_text, metrics)."""
			direction = (direction or "").lower().strip()
			risk = abs(entry - sl)
			reward = abs(tp - entry)
			metrics: dict = {"risk": risk, "reward": reward}
			if risk <= 0 or reward <= 0:
				return ("Manage risk carefully. Consider waiting for clearer conditions.", metrics)
			
			if direction == "long":
				pl_pct = ((price - entry) / entry) * 100.0
				progress = (price - entry) / (tp - entry) if (tp - entry) != 0 else 0.0
				dist_to_sl = (price - sl)
			else:
				pl_pct = ((entry - price) / entry) * 100.0
				progress = (entry - price) / (entry - tp) if (entry - tp) != 0 else 0.0
				dist_to_sl = (sl - price)
			
			metrics.update({"pl_pct": pl_pct, "progress": progress})
			near_sl = (dist_to_sl / risk) <= 0.2
			if progress >= 1.0:
				return ("✅ Target zone reached. Consider taking profit (full or partial) and managing trailing risk.", metrics)
			if progress >= 0.75:
				return ("📌 Close to TP. Consider partial take-profit and move SL to breakeven if your plan allows.", metrics)
			if progress >= 0.30:
				return ("⏳ In profit but not near TP yet. Consider waiting for full TP, or take partial if volatility is high.", metrics)
			if near_sl:
				return ("⚠️ Price is close to SL zone. Consider reducing exposure or exiting early to avoid a full SL hit.", metrics)
			return ("⏳ Still developing. Consider waiting; avoid moving SL further away.", metrics)
		
		# Calculate current position
		entry = _as_float(sig.entry)
		sl = _as_float(sig.stop_loss)
		tp = _parse_tp(sig.take_profit)
		
		if entry is not None and sl is not None and tp is not None:
			price = _current_price(str(sig.asset))
			if price is not None:
				advice, metrics = _position_advice(
					direction=str(sig.direction),
					entry=float(entry),
					sl=float(sl),
					tp=float(tp),
					price=float(price),
				)
				lines.append(f"Current Price: {price:.6g}")
				try:
					pl_pct = metrics.get('pl_pct', 0)
					progress = metrics.get('progress', 0)
					lines.append(f"P/L: {float(pl_pct):.2f}%")
					lines.append(f"Progress to TP: {max(0.0, min(1.0, float(progress))) * 100.0:.0f}%")
				except Exception:
					pass
				lines.append("")
				lines.append(f"💡 {advice}")
			else:
				lines.append("Current Price: Unavailable (check later)")
		else:
			lines.append("Position data incomplete")
		
		# Status message
		lines.extend(["", "⏳ Outcome not determined yet."])
		
		await update.message.reply_text("\n".join(lines))
		return
	except Exception:
		await update.message.reply_text("Outcome lookup is temporarily unavailable.")
		return


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	code = None
	progress = None
	try:
		from db.session import ENGINE, get_session
		if ENGINE is not None:
			from db.pg_features import get_or_create_referral_code, get_referral_progress
			async with get_session() as session:
				code = await get_or_create_referral_code(session, referrer_telegram_user_id=int(user_id))
				progress = await get_referral_progress(session, referrer_telegram_user_id=int(user_id))
				await session.commit()
		else:
			raise RuntimeError("DATABASE_URL not configured. Postgres is required.")
	except Exception:
		code = None
		progress = None

	bot_username = None
	try:
		me = await context.bot.get_me()
		bot_username = getattr(me, "username", None)
	except Exception:
		bot_username = os.getenv("BOT_USERNAME")
	progress_line = ""
	if progress:
		need = int(progress.get("needed_for_next", 0) or 0)
		toward = int(progress.get("toward_next", 0) or 0)
		total = int(progress.get("total", 0) or 0)
		# If you're exactly on a multiple of 3, you already earned the previous reward;
		# the next reward needs 3 more invites.
		if toward == 0:
			progress_line = f"\n\nProgress: 0/3 (invite 3 more people to earn +7 days Premium). Total invites: {total}."
		else:
			progress_line = f"\n\nProgress: {toward}/3 (invite {need} more to earn +7 days Premium). Total invites: {total}."

	if bot_username and code:
		link = f"https://t.me/{bot_username}?start=ref_{code}"
		await update.message.reply_text(
			f"🎁 Invite link:\n{link}\n\n"
			"Reward: invite 3 new users → get +7 days Premium."
			f"{progress_line}"
		)
		return

	if code:
		await update.message.reply_text(
			f"🎁 Your invite code: {code}\n\n"
			"Reward: invite 3 new users → get +7 days Premium.\n"
			"Invite link is unavailable (bot username not resolved)."
			f"{progress_line}"
		)
	else:
		await update.message.reply_text("Invite system is temporarily unavailable.")

async def pricing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if await _public_guard(update):
		return
	# VIP seat info from Postgres (best-effort)
	try:
		from db.session import ENGINE, get_session
		from db.repository import count_active_vip_users
		if ENGINE is not None:
			async with get_session() as session:
				used = await count_active_vip_users(session, exclude_telegram_user_ids=set())
				await session.commit()
			limit = int(os.getenv("VIP_SEAT_LIMIT", "15") or "15")
			remaining = max(0, limit - used)
		else:
			used, remaining, limit = 0, 15, 15
	except Exception:
		used, remaining, limit = 0, 15, 15
	vip_line = f"VIP seats remaining: {remaining}/{limit}"
	msg = (
		"💎 SignalRankAI Pricing\n\n"
		"🆓 FREE\n"
		"• 1–2 delayed signal summaries per day\n"
		"• Outcome notifications (no exact prices)\n"
		"• Daily performance summary (limited)\n"
		"• Access to /pricing and /upgrade\n\n"
		"• Optional: buy extra daily signals (₦300 each, 24h access)\n\n"
		"🟡 PREMIUM\n"
		"₦4,000 / week\n"
		"₦12,000 / month\n"
		"₦28,000 / 3 months\n"
		"• Real-time signals (5m → 24h)\n"
		"• Exact Entry, SL, TP\n"
		"• Confidence score per trade\n"
		"• TP/SL hit notifications\n"
		"• Daily & weekly performance stats\n"
		"• Access to /performance\n\n"
		"🔴 VIP / ELITE\n"
		"₦20,000 / month (limited seats)\n"
		+ vip_line + "\n"
		"• Highest confidence signals only (score ≥ 85)\n"
		"• Reduced frequency (quality > quantity)\n"
		"• Early alerts + priority notifications\n"
		"• Monthly performance report\n\n"
		"📌 No hype. Transparent tracking.\n"
		"Use /upgrade to subscribe.\n\n"
		"⚠️ Disclaimer: Educational only. Not financial advice. Trading involves risk."
	)
	if update.message is not None:
		await update.message.reply_text(msg)


async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if await _public_guard(update):
		return
	"""Generates Paystack payment links for subscriptions.

	Note: In production, configure Paystack Plans and store plan codes in env.
	This function still works with the current hosted-payment-link stub.
	"""
	user_id = update.effective_user.id
	from paystack.paystack import generate_paystack_link
	
	# Plan codes (optional; used later when wiring Paystack plans properly)
	premium_monthly_code = os.getenv("PAYSTACK_PLAN_CODE_PREMIUM_MONTHLY")
	premium_quarterly_code = os.getenv("PAYSTACK_PLAN_CODE_PREMIUM_QUARTERLY")
	premium_semiannual_code = os.getenv("PAYSTACK_PLAN_CODE_PREMIUM_SEMIANNUAL")
	vip_monthly_code = os.getenv("PAYSTACK_PLAN_CODE_VIP_MONTHLY")

	links = []
	links.append(
		("Premium (₦4,000 / 7 days)", generate_paystack_link(user_id, 4000, tier="premium", duration_days=7, plan_code=os.getenv("PAYSTACK_PLAN_CODE_PREMIUM_WEEKLY")))
	)
	links.append(
		("Premium (₦12,000 / 30 days)", generate_paystack_link(user_id, 12000, tier="premium", duration_days=30, plan_code=premium_monthly_code))
	)
	links.append(
		("Premium (₦28,000 / 90 days)", generate_paystack_link(user_id, 28000, tier="premium", duration_days=90, plan_code=premium_quarterly_code))
	)
	# VIP link only if seats available (or user is owner/bypassed/already VIP)
	try:
		from db.session import ENGINE, get_session
		from db.repository import count_active_vip_users, get_active_subscription
		from config import OWNER_IDS
		if ENGINE is not None:
			async with get_session() as session:
				used = await count_active_vip_users(session, exclude_telegram_user_ids=set())
				limit = int(os.getenv("VIP_SEAT_LIMIT", "15") or "15")
				remaining = max(0, limit - used)
				sub = await get_active_subscription(session, telegram_user_id=user_id, tier="vip")
				already_vip = sub is not None
				await session.commit()
		else:
			remaining, limit, already_vip = 15, 15, False
		try:
			bypassed = bool(await state.has_temp_owner(user_id))
		except Exception:
			bypassed = False
		is_owner = user_id in OWNER_IDS
		can_offer_vip = (remaining > 0) or already_vip or bypassed or is_owner
	except Exception:
		can_offer_vip = True
		remaining = None
		limit = None

	if can_offer_vip:
		links.append(
			("VIP (₦20,000 / 30 days)", generate_paystack_link(user_id, 20000, tier="vip", duration_days=30, plan_code=vip_monthly_code))
		)
	else:
		links.append(("VIP (SOLD OUT)", "VIP seats are currently full. Check /pricing later."))

	msg = "📌 Choose a plan:\n\n" + "\n".join([f"• {label}: {url}" for (label, url) in links])
	msg += "\n\nPayments are processed by Paystack. No access to your funds."
	msg += "\n⚠️ Educational only. Not financial advice."
	if update.message is not None:
		await update.message.reply_text(msg)
# --- Extra Signal Purchase Logic ---
from telegram import Update

async def buy_extra_signals(update, context):
	user_id = update.effective_user.id
	# Use Postgres tier resolution
	from signalrank_telegram.access import resolve_user_tier
	tier = resolve_user_tier(user_id)
	if tier != "FREE":
		await update.message.reply_text(
			"Extra daily signals are only available for Free users.\n"
			"Use /upgrade to subscribe if you want unlimited access."
		)
		return
	if not context.args or len(context.args) != 1:
		await update.message.reply_text(
			"Usage: /buy_extra_signals <count>\n"
			"Example: /buy_extra_signals 2\n\n"
			"₦300 per extra signal. Extra access lasts 24 hours."
		)
		return
	try:
		count = int(context.args[0])
		if count < 1 or count > 5:
			await update.message.reply_text("Count must be between 1 and 5.")
			return
	except ValueError:
		await update.message.reply_text("Count must be a number.")
		return
	price = 300 * count
	from paystack.paystack import generate_paystack_link
	paywall_link = generate_paystack_link(user_id, price, tier="PREMIUM", extra_count=count)
	await update.message.reply_text(
		f"To unlock {count} extra signals for the next 24 hours, pay ₦{price}: {paywall_link}\n\n"
		"After payment verification, your extra signals will be delivered in real time.\n"
		"All payments are final and non-refundable.\n\n"
		"For questions, use /faq or contact support."
	)


# /policy or /refunds command
async def policy_command(update, context):
	if await _public_guard(update):
		return
	msg = (
		"📄 Subscription & Refund Policy\n\n"
		"• Due to the digital and time-sensitive nature of the service, payments are non-refundable.\n"
		"• If technical issues prevent delivery, subscription time may be extended.\n\n"
		"Subscriptions activate after successful verification and expire at the end of the purchased period.\n\n"
		"⚠️ Disclaimer: Educational only. Not financial advice. Trading involves risk."
	)
	await update.message.reply_text(msg)

# /recap command (weekly recap)
async def recap_command(update, context):
	if await _public_guard(update):
		return
	user_id = update.effective_user.id
	# Postgres-first recap (delivery-based)
	try:
		from db.session import ENGINE, get_session
		if ENGINE is not None:
			from db.pg_features import get_weekly_recap_stats
			async with get_session() as session:
				stats = await get_weekly_recap_stats(session, int(user_id))
				await session.commit()
			total = int((stats or {}).get("total") or 0)
			if total <= 0:
				await update.message.reply_text(
					"\U0001F4CA SignalRankAI Weekly Recap\n\n"
					"No signals were sent to you this week.\n\n"
					"Thank you for trading responsibly."
				)
				return
			most_active = ", ".join(list((stats or {}).get("top_assets") or [])[:2]) or "N/A"
			best_strategy = ", ".join(list((stats or {}).get("top_strategies") or [])[:1]) or "N/A"
			await update.message.reply_text(
				"\U0001F4CA SignalRankAI Weekly Recap\n\n"
				"Here’s a quick overview of your past week:\n\n"
				f"• Total signals delivered: {total}\n"
				f"• Markets most active: {most_active}\n"
				f"• Best-performing strategy: {best_strategy}\n\n"
				"Thank you for trading responsibly."
			)
			return
	except Exception:
		pass

	# SQLite fallback
	trades = []  # Postgres-only
	total_signals = len(trades)
	if total_signals == 0:
		await update.message.reply_text(
			"\U0001F4CA SignalRankAI Weekly Recap\n\n"
			"No signals were sent to you this week.\n\n"
			"Thank you for trading responsibly."
		)
		return
	from collections import Counter
	assets = [t[2] for t in trades]  # asset column
	strategies = [t[9] for t in trades]  # strategy_name column
	most_active = ', '.join([a for a, _ in Counter(assets).most_common(2)]) if assets else 'N/A'
	best_strategy = Counter(strategies).most_common(1)[0][0] if strategies else 'N/A'
	await update.message.reply_text(
		"\U0001F4CA SignalRankAI Weekly Recap\n\n"
		"Here’s a quick overview of your past week:\n\n"
		f"• Total signals sent: {total_signals}\n"
		f"• Markets most active: {most_active}\n"
		f"• Best-performing strategy: {best_strategy}"
	)


TIER_RANKS = {
	"FREE": 0,
	"PREMIUM": 1,
	"VIP": 2,
	"OWNER": 3
}

def tier_rank(tier):
	return TIER_RANKS.get(tier, 0)



from core.performance import strategy_stats

def require_tier(min_tier):
	def wrapper(func):
		async def inner(update, context):
			if update.effective_user is None or update.message is None:
				return
			user_id = update.effective_user.id
			# Global kill-switch
			try:
				ks = state.get_killswitch_sync()
			except Exception:
				ks = type("KS", (), {"enabled": False})()
			if getattr(ks, "enabled", False):
				await update.message.reply_text("🚨 Signals are temporarily paused.")
				return

			# Rate limit (20/min)
			try:
				limited = state.rate_limited_sync(user_id, limit=20, window_seconds=60)
			except Exception:
				limited = False
			if limited:
				await update.message.reply_text("Rate limit exceeded. Please wait.")
				return
			tier = _effective_tier(user_id)
			if tier_rank(tier) < tier_rank(min_tier):
				await update.message.reply_text(
					f"🔒 You can’t access this on {str(tier).upper()} tier.\n"
					"Use /upgrade to subscribe to unlock it."
				)
				return
			result = func(update, context)
			if inspect.isawaitable(result):
				return await result
			return result
		return inner
	return wrapper


# /start or welcome message

async def start_command(update, context):
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	# Do not block user registration on kill-switch.
	# Keep only a light rate limit to prevent abuse.
	try:
		if state.rate_limited_sync(int(user_id), limit=10, window_seconds=30):
			await update.message.reply_text("Rate limit exceeded. Please wait.")
			return
	except Exception:
		pass
	username = None
	try:
		username = update.effective_user.username
	except Exception:
		username = None
	ref_token = None
	try:
		if getattr(context, "args", None):
			ref_token = str(context.args[0])
	except Exception:
		ref_token = None

	is_new = False
	referral_outcome = None
	# Prefer Postgres for user creation + referral attribution + audit (single session)
	try:
		from db.session import ENGINE, get_session
		if ENGINE is not None:
			from db.models import User
			from sqlalchemy import select
			from db.repository import get_or_create_user
			from db.pg_features import record_bot_event
			from db.pg_features import ensure_alert_prefs
			async with get_session() as session:
				res = await session.execute(select(User).where(User.telegram_user_id == int(user_id)))
				existing = res.scalar_one_or_none()
				is_new = existing is None
				await get_or_create_user(session, telegram_user_id=user_id, username=username)
				# Ensure alert preferences row exists for all users.
				try:
					await ensure_alert_prefs(session, int(user_id))
				except Exception:
					pass

				# Referral attribution (only for first-time users)
				code = None
				if ref_token:
					code = str(ref_token)
					if code.startswith("ref_"):
						code = code[4:]
					code = (code or "").strip() or None
				if code:
					try:
						from db.pg_features import process_referral_start as process_referral_start_pg
						referral_outcome = await process_referral_start_pg(
							session,
							referred_telegram_user_id=int(user_id),
							referral_code=str(code),
							is_new_user=bool(is_new),
						)
					except Exception:
						referral_outcome = None

				# Audit: always record the start event when Postgres is available
				try:
					await record_bot_event(
						session,
						telegram_user_id=int(user_id),
						username=username,
						event_type="user_start",
						meta={
							"is_new": bool(is_new),
							"ref_token": str(ref_token) if ref_token else None,
							"referral": referral_outcome,
						},
					)
				except Exception:
					pass

				await session.commit()
		else:
			raise RuntimeError("DATABASE_URL not configured. Postgres is required.")
	except Exception as e:
		# Postgres is required; no fallback. Keep bot alive and emit actionable logs.
		try:
			print(f"[ERROR] /start failed to access Postgres: {type(e).__name__}: {e}", flush=True)
		except Exception:
			pass
		if update.message is not None:
			await update.message.reply_text(
				"Database temporarily unavailable. Please try again in 1–2 minutes."
			)
		return

	# Internal audit log (no user-visible output)
	try:
		if referral_outcome:
			_audit_logger.info(
				"referral_start status=%s referrer_id=%s referred_id=%s days=%s",
				referral_outcome.get("status"),
				referral_outcome.get("referrer_id"),
				user_id,
				referral_outcome.get("days_granted"),
			)
	except Exception:
		pass

	msg = (
		"SignalRankAI provides algorithmic market analysis for educational purposes only. "
		"This is not financial advice. Trading involves risk.\n\n"
		"What you get:\n"
		"• Risk-managed signals filtered for high-probability setups\n"
		"• Outcome tracking (no hype, no guarantees)\n\n"
		"Use /pricing to see plans, or /upgrade to subscribe."
	)
	# Referral feedback (minimal, non-spammy)
	if referral_outcome and update.message is not None:
		status = str(referral_outcome.get("status"))
		if status in {"attributed", "reward_granted"}:
			await update.message.reply_text("✅ Referral applied. Welcome!")
		elif status == "invalid_code":
			await update.message.reply_text("⚠️ Referral code not recognized.")
		# else: silent for self_referral/already_referred/not_new

	# Notify referrer when someone joins with their link or when reward is unlocked
	try:
		if referral_outcome:
			referrer_id = int(referral_outcome.get("referrer_id"))
			status = str(referral_outcome.get("status"))
			
			if status in {"attributed", "reward_granted"}:
				# Send referrer message about their referral count
				referrer_msg = referral_outcome.get("referrer_message")
				if referrer_msg:
					await context.bot.send_message(
						chat_id=referrer_id,
						text=referrer_msg,
					)
			
			# Additional message for reward_granted
			if status == "reward_granted":
				days = int(referral_outcome.get("days_granted"))
				await context.bot.send_message(
					chat_id=referrer_id,
					text=f"🎁 *Bonus Plan Extension*\n\n+{days} premium days have been added to your current plan!\n\nUse /signals to get the latest trading ideas.",
					parse_mode="Markdown"
				)
	except Exception:
		pass

	await update.message.reply_text(msg)

# /about message
async def about_command(update, context):
	msg = (
		"\U0001F4CA About SignalRankAI\n\n"
		"SignalRankAI is a rule-based trading signal platform designed to deliver high-quality, risk-aware trade ideas.\n\n"
		"The system:\n"
		"• Uses multiple market strategies\n"
		"• Filters out weak or risky setups\n"
		"• Ranks signals by quality\n"
		"• Limits signal frequency to avoid noise\n\n"
		"SignalRankAI does not execute trades and does not guarantee profits.\n"
		"All signals are for educational and informational purposes only.\n\n"
		"Trade responsibly."
	)
	if update.message is not None:
		await update.message.reply_text(msg)

# /faq message
async def faq_command(update, context):
	msg = (
		"\u2754 Frequently Asked Questions\n\n"
		"1) Does SignalRankAI place trades for me?\n"
		"No. SignalRankAI only provides trade signals. You decide if and how you trade.\n\n"
		"2) Are profits guaranteed?\n"
		"No. Trading always involves risk. No system can guarantee profits.\n\n"
		"3) How often are signals sent?\n"
		"Only when high-quality setups appear. Some days may have fewer or no signals.\n\n"
		"4) What markets are covered?\n"
		"Major crypto markets and timeframes, depending on current conditions.\n\n"
		"5) What’s the difference between Free, Premium, and VIP?\n"
		"Free users receive delayed summaries.\nPremium and VIP users receive real-time signals, with higher tiers getting more detail and earlier access.\n\n"
		"6) Can I cancel anytime?\n"
		"Yes. Subscriptions expire automatically and do not auto-renew unless stated.\n\n"
		"7) Is this financial advice?\n"
		"No. Signals are for informational purposes only."
	)
	if update.message is not None:
		await update.message.reply_text(msg)

# /disclaimer message
async def disclaimer_command(update, context):
	if await _public_guard(update):
		return
	msg = (
		"⚠️ Disclaimer\n\n"
		"SignalRankAI provides trading signals for informational and educational purposes only.\n\n"
		"Nothing provided by this bot constitutes financial advice, investment advice, or a recommendation to buy or sell any asset.\n\n"
		"Trading involves risk, and you are fully responsible for your trading decisions.\n"
		"Past performance does not guarantee future results.\n\n"
		"By using SignalRankAI, you acknowledge and accept these risks."
	)
	if update.message is not None:
		await update.message.reply_text(msg)


async def performance_command(update, context):
	if await _public_guard(update):
		return
	from datetime import datetime, timedelta
	user_id = update.effective_user.id
	tier = _effective_tier(user_id)

	# Prefer Postgres (deliveries + outcomes)
	try:
		from db.session import ENGINE, get_session
		if ENGINE is not None:
			from db.pg_features import get_user_performance_30d

			async def _fetch() -> dict:
				async with get_session() as session:
					data = await get_user_performance_30d(session, int(user_id))
					await session.commit()
					return data

			try:
				stats = await _fetch()
			except Exception:
				stats = {}

			total = int((stats or {}).get("total") or 0)
			wins = int((stats or {}).get("wins") or 0)
			losses = int((stats or {}).get("losses") or 0)
			win_rate = float((stats or {}).get("win_rate") or 0.0)
			avg_r = (stats or {}).get("avg_r")
			net_r = (stats or {}).get("net_r")
			tracked = int((stats or {}).get("tracked_outcomes") or 0)
			profit_loss = float((stats or {}).get("profit_loss_pct") or 0.0)

			if total <= 0:
				if update.message is not None:
					await update.message.reply_text("No signals in the last 30 days.")
				return

			if tier_rank(tier) < tier_rank("PREMIUM"):
				bucket = "strong" if win_rate >= 0.6 else ("cautious" if win_rate <= 0.4 else "mixed")
				msg = (
					"📊 Performance (limited)\n\n"
					f"Recent trend: {bucket}.\n"
					"Upgrade to Premium for full stats and history."
				)
				if update.message is not None:
					await update.message.reply_text(msg)
				return

			avg_r_str = f"{float(avg_r):.2f}R" if avg_r is not None else "N/A"
			net_r_str = f"{float(net_r):.2f}R" if net_r is not None else "N/A"
			profit_str = f"+{profit_loss:.2f}%" if profit_loss >= 0 else f"{profit_loss:.2f}%"
			profit_emoji = "✅" if profit_loss >= 0 else "⚠️"
			
			msg = (
				"📊 Performance (last 30 days)\n\n"
				f"Signals delivered: {total}\n"
				f"Outcomes tracked: {tracked}/{total}\n"
				f"Wins: {wins} | Losses: {losses}\n"
				f"Win rate: {round(win_rate*100,1)}%\n"
				f"Avg R per trade: {avg_r_str}\n"
				f"Net R (total): {net_r_str}\n"
				f"{profit_emoji} Est. profit/loss: {profit_str}\n\n"
				"💡 Based on 1% risk per signal."
			)
			if update.message is not None:
				await update.message.reply_text(msg)
			return
	except Exception:
		pass

	# Fallback: legacy SQLite (best-effort)
	trades = []  # Postgres-only
	cutoff = datetime.now() - timedelta(days=30)
	def parse_dt(row):
		try:
			return datetime.fromisoformat(row[3]) if isinstance(row[3], str) else cutoff
		except Exception:
			return cutoff
	trades_30d = [t for t in trades if parse_dt(t) >= cutoff]
	total = len(trades_30d)
	if total == 0:
		if update.message is not None:
			await update.message.reply_text("No signals in the last 30 days.")
		return
	win_count = sum(1 for t in trades_30d if (len(t) > 15 and str(t[15]).upper() == 'TP'))
	win_rate = win_count / total if total > 0 else 0
	if tier_rank(tier) < tier_rank("PREMIUM"):
		bucket = "mixed"
		if win_rate >= 0.6:
			bucket = "strong"
		elif win_rate <= 0.4:
			bucket = "cautious"
		msg = (
			"📊 Performance (limited)\n\n"
			f"Recent snapshot: {bucket}.\n"
			"Upgrade to Premium for full stats and history."
		)
		if update.message is not None:
			await update.message.reply_text(msg)
		return
	msg = f"Last 30 days:\n✔ Signals: {total}\n✔ Snapshot win-rate: {round(win_rate*100,1)}%"
	if update.message is not None:
		await update.message.reply_text(msg)


# -------- Premium commands --------
@require_tier("PREMIUM")
async def stats_command(update, context):
	user_id = update.effective_user.id
	# Postgres-first
	try:
		from db.session import ENGINE, get_session
		if ENGINE is not None:
			from db.pg_features import get_weekly_recap_stats, list_signals_sent_today
			async with get_session() as session:
				week = await get_weekly_recap_stats(session, int(user_id))
				today_rows = await list_signals_sent_today(session, int(user_id))
				await session.commit()
			total_week = int((week or {}).get("total") or 0)
			today = len(today_rows or [])
			msg = (
				"📈 Stats (Premium)\n\n"
				f"Signals delivered today: {today}\n"
				f"Signals delivered (last 7 days): {total_week}\n\n"
				"Use /history to view recent signals."
			)
			if update.message is not None:
				await update.message.reply_text(msg)
			return
	except Exception:
		pass

	# SQLite fallback
	trades = []  # Postgres-only
	msg = (
		"📈 Stats (Premium)\n\n"
		f"Signals recorded: {len(trades)}\n"
		"Use /history to view recent signals."
	)
	if update.message is not None:
		await update.message.reply_text(msg)


@require_tier("PREMIUM")
async def history_command(update, context):
	user_id = update.effective_user.id
	asset = None
	tf = None
	if context.args:
		asset = str(context.args[0]).upper()
		if len(context.args) > 1:
			tf = str(context.args[1])

	# Postgres-first
	try:
		from db.session import ENGINE, get_session
		if ENGINE is not None:
			from db.pg_features import list_recent_signals_delivered
			async with get_session() as session:
				rows = await list_recent_signals_delivered(
					session,
					telegram_user_id=int(user_id),
					limit=10,
					asset=asset,
					timeframe=tf,
				)
				await session.commit()
			if not rows:
				if update.message is not None:
					await update.message.reply_text("No history available yet.")
				return
			lines = ["🧾 History (last 10):", ""]
			for s in rows:
				lines.append(
					f"• {s.asset} {s.timeframe} {s.direction} ref={s.signal_id} entry={s.entry} sl={s.stop_loss} tp={s.take_profit}"
				)
			if update.message is not None:
				await update.message.reply_text("\n".join(lines))
			return
	except Exception:
		pass

	# SQLite fallback
	trades = []  # Postgres-only
	filtered = []
	for t in trades:
		try:
			row_asset = str(t[1])
			row_tf = str(t[2])
			if asset and row_asset != asset:
				continue
			if tf and row_tf != tf:
				continue
			filtered.append(t)
		except Exception:
			continue
	filtered = filtered[-10:]
	if not filtered:
		if update.message is not None:
			await update.message.reply_text("No history available yet.")
		return
	lines = ["🧾 History (last 10):", ""]
	for t in filtered:
		try:
			lines.append(f"• {t[1]} {t[2]} {t[3]} entry={t[4]} sl={t[5]} tp={t[6]}")
		except Exception:
			continue
	if update.message is not None:
		await update.message.reply_text("\n".join(lines))


@require_tier("PREMIUM")
async def risk_command(update, context):
	if update.message is None:
		return
	await update.message.reply_text(
		"🛡️ Risk (recommended)\n\n"
		"Suggested risk: ~1% per trade.\n"
		"Keep position sizes consistent and avoid overtrading."
	)


async def alerts_command(update, context):
	if await _public_guard(update):
		return
	user_id = update.effective_user.id

	async def _get_prefs() -> dict:
		try:
			from db.session import ENGINE, get_session
			if ENGINE is not None:
				from db.pg_features import get_alert_prefs
				async with get_session() as session:
					prefs = await get_alert_prefs(session, int(user_id))
					await session.commit()
					return dict(prefs or {})
		except Exception:
			pass
		return dict(get_alert_prefs(user_id) or {})

	async def _set_prefs(*, tp_sl_enabled=None, quiet_start_hour=None, quiet_end_hour=None) -> dict:
		try:
			from db.session import ENGINE, get_session
			if ENGINE is not None:
				from db.pg_features import set_alert_prefs
				async with get_session() as session:
					prefs = await set_alert_prefs(
						session,
						int(user_id),
						tp_sl_enabled=tp_sl_enabled,
						quiet_start_hour=quiet_start_hour,
						quiet_end_hour=quiet_end_hour,
					)
					await session.commit()
					return dict(prefs or {})
		except Exception:
			pass
		return dict(set_alert_prefs(user_id, tp_sl_enabled=tp_sl_enabled, quiet_start_hour=quiet_start_hour, quiet_end_hour=quiet_end_hour) or {})
	
	if not context.args:
		prefs = await _get_prefs()
		qs = prefs.get("quiet_start_hour")
		qe = prefs.get("quiet_end_hour")
		quiet = "off" if qs is None or qe is None else f"{qs}:00–{qe}:00"
		status = "on" if prefs.get("tp_sl_enabled", True) else "off"
		if update.message is not None:
			await update.message.reply_text(f"🔔 Alerts\n\nTP/SL alerts: {status}\nQuiet hours: {quiet}\n\nUsage: /alerts on|off or /alerts quiet <start_hour> <end_hour>")
		return

	cmd = str(context.args[0]).lower()
	if cmd in {"on", "off"}:
		_ = await _set_prefs(tp_sl_enabled=(cmd == "on"))
		if update.message is not None:
			await update.message.reply_text("✅ Updated.")
		return
	if cmd == "quiet" and len(context.args) == 3:
		try:
			qs = int(context.args[1])
			qe = int(context.args[2])
			if not (0 <= qs <= 23 and 0 <= qe <= 23):
				raise ValueError()
			_ = await _set_prefs(quiet_start_hour=qs, quiet_end_hour=qe)
			if update.message is not None:
				await update.message.reply_text("✅ Quiet hours updated.")
			return
		except Exception:
			pass
	if update.message is not None:
		await update.message.reply_text("Usage: /alerts on|off or /alerts quiet <start_hour> <end_hour>")


# -------- VIP commands (hidden from BotFather) --------
@require_tier("VIP")
async def elite_command(update, context):
	signals = []  # Postgres-only
	elite = [s for s in signals if float(s.get("score") or 0) >= 85]
	if not elite:
		if update.message is not None:
			await update.message.reply_text("No elite signals available right now.")
		return
	from .formatter import format_signal
	for s in elite[:5]:
		if update.message is not None:
			await update.message.reply_text(format_signal(s))


@require_tier("VIP")
async def early_command(update, context):
	if update.message is not None:
		await update.message.reply_text("⚡ Early access is automatic for VIP. You’ll receive signals first when available.")


@require_tier("VIP")
async def report_command(update, context):
	# Structured text report (monthly)
	if update.message is None:
		return
	await update.message.reply_text(
		"🗓️ VIP Monthly Report\n\n"
		"Monthly reports are delivered automatically.\n"
		"This command will show the latest report when available."
	)
