# /pricing command
import os
import logging
import inspect

from telegram import Update
from telegram.ext import ContextTypes

from core.redis_state import state
from .access import resolve_user_tier


_audit_logger = logging.getLogger("audit")


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
	user_id = update.effective_user.id
	tier = _effective_tier(user_id)

	public_cmds = [
		("/start", "Start and register your account"),
		("/help", "Show commands by tier"),
		("/pricing", "View plans and seat limits"),
		("/upgrade", "Get Paystack checkout links"),
		("/signals", "Today’s signals sent to you"),
		("/performance", "Performance summary"),
		("/invite", "Your referral link"),
	]
	premium_cmds = [
		("/stats", "Signal stats"),
		("/history", "Your signal history"),
		("/risk", "Risk guidance for current regime"),
		("/alerts", "Alert preferences (quiet hours, TP/SL)"),
	]
	vip_cmds = [
		("/elite", "Highest-confidence signals"),
		("/early", "Early alerts"),
		("/report", "Monthly report"),
	]

	lines = ["📌 Commands", "", "🆓 Public:"]
	lines += [f"• {cmd} — {desc}" for (cmd, desc) in public_cmds]
	if tier_rank(tier) >= tier_rank("PREMIUM"):
		lines += ["", "🟡 Premium:"] + [f"• {cmd} — {desc}" for (cmd, desc) in premium_cmds]
	if tier_rank(tier) >= tier_rank("VIP"):
		lines += ["", "🔴 VIP:"] + [f"• {cmd} — {desc}" for (cmd, desc) in vip_cmds]
	lines += ["", "⚠️ Educational only. Not financial advice. Trading involves risk."]
	if update.message is not None:
		await update.message.reply_text("\n".join(lines))


async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if await _public_guard(update):
		return
	user_id = update.effective_user.id
	tier = _effective_tier(user_id)

	signals: list[dict] = []
	# Prefer Postgres-backed daily history when configured.
	try:
		from db.session import ENGINE, get_session
		if ENGINE is not None:
			from db.pg_features import list_signals_sent_today
			async with get_session() as session:
				rows = await list_signals_sent_today(session, telegram_user_id=int(user_id))
				signals = [
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
						"regime": r.regime,
						"strength": r.strength,
						"strategy_name": r.strategy_name,
						"strategy_group": r.strategy_group,
					}
					for r in rows
				]
	except Exception:
		signals = []

	# SQLite fallback (legacy)
	if not signals:
		try:
			from db.database import get_unreleased_signals
			signals = get_unreleased_signals()[:10]
		except Exception:
			signals = []

	if not signals:
		if update.message is not None:
			await update.message.reply_text("No signals sent to you today yet. Check back later.")
		return

	if tier_rank(tier) < tier_rank("PREMIUM"):
		lines = ["🆓 Today’s signals (summary):", ""]
		for s in signals[:10]:
			lines.append(
				f"• {s.get('asset')} {s.get('timeframe')} {s.get('direction')} (score {int(s.get('score', 0) or 0)})"
			)
		lines += ["", "Upgrade to Premium to receive real-time entries, SL/TP, and alerts."]
		if update.message is not None:
			await update.message.reply_text("\n".join(lines))
		return

	from .formatter import format_signal
	for s in signals[:10]:
		try:
			if update.message is not None:
				await update.message.reply_text(format_signal(s))
		except Exception:
			continue


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
			raise RuntimeError("no postgres")
	except Exception:
		try:
			from db.database import generate_referral_code, get_referral_progress
			code = generate_referral_code(user_id)
			progress = get_referral_progress(user_id)
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
			progress_line = f"\n\nProgress: 0/3 (invite 3 more to earn +7 days Premium). Total invites: {total}."
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
	from db.database import count_active_vip_seats
	used, remaining, limit = count_active_vip_seats()
	vip_line = f"VIP seats remaining: {remaining}/{limit}"
	msg = (
		"💎 SignalRankAI Pricing\n\n"
		"🆓 FREE\n"
		"• 1–2 delayed signal summaries per day\n"
		"• Outcome notifications (no exact prices)\n"
		"• Daily performance summary (limited)\n"
		"• Access to /pricing and /upgrade\n\n"
		"🟡 PREMIUM\n"
		"₦5,000 / month\n"
		"₦12,000 / 3 months\n"
		"₦20,000 / 6 months\n"
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
		("Premium (₦5,000 / 30 days)", generate_paystack_link(user_id, 5000, tier="premium", duration_days=30, plan_code=premium_monthly_code))
	)
	links.append(
		("Premium (₦12,000 / 90 days)", generate_paystack_link(user_id, 12000, tier="premium", duration_days=90, plan_code=premium_quarterly_code))
	)
	links.append(
		("Premium (₦20,000 / 180 days)", generate_paystack_link(user_id, 20000, tier="premium", duration_days=180, plan_code=premium_semiannual_code))
	)
	# VIP link only if seats available (or user is owner/bypassed/already VIP)
	try:
		from db.database import count_active_vip_seats, get_subscription, OWNER_IDS
		_, remaining, limit = count_active_vip_seats()
		sub = get_subscription(user_id)
		already_vip = bool(sub and not sub.get('expired', True) and str(sub.get('tier', '')).upper().startswith('VIP'))
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
from db.database import get_user_tier

async def buy_extra_premium(update, context):
	user_id = update.effective_user.id
	tier = get_user_tier(user_id)
	if tier != "FREE":
		await update.message.reply_text(
			"Extra Premium signals are only available for Free users.\n"
			"Upgrade to Premium or VIP for unlimited real-time access."
		)
		return
	if not context.args or len(context.args) != 1:
		await update.message.reply_text(
			"Usage: /buy_extra_premium <count>\n"
			"Example: /buy_extra_premium 2\n\n"
			"You can buy up to 5 extra signals per day."
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
		f"To unlock {count} extra Premium signals for today, pay ₦{price}: {paywall_link}\n\n"
		"After payment, your extra signals will be delivered instantly.\n"
		"All payments are final and non-refundable.\n\n"
		"For questions, use /faq or contact support."
	)

async def buy_extra_vip(update, context):
	user_id = update.effective_user.id
	tier = get_user_tier(user_id)
	if tier != "FREE":
		await update.message.reply_text(
			"Extra VIP signals are only available for Free users.\n"
			"Upgrade to VIP for unlimited real-time access."
		)
		return
	if not context.args or len(context.args) != 1:
		await update.message.reply_text(
			"Usage: /buy_extra_vip <count>\n"
			"Example: /buy_extra_vip 1\n\n"
			"You can buy up to 3 extra VIP signals per day."
		)
		return
	try:
		count = int(context.args[0])
		if count < 1 or count > 3:
			await update.message.reply_text("Count must be between 1 and 3.")
			return
	except ValueError:
		await update.message.reply_text("Count must be a number.")
		return
	price = 500 * count
	from paystack.paystack import generate_paystack_link
	paywall_link = generate_paystack_link(user_id, price, tier="VIP", extra_count=count)
	await update.message.reply_text(
		f"To unlock {count} extra VIP signals for today, pay ₦{price}: {paywall_link}\n\n"
		"After payment, your extra signals will be delivered instantly.\n"
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
	from db.database import fetch_user_trades
	user_id = update.effective_user.id
	trades = fetch_user_trades(user_id)
	total_signals = len(trades)
	if total_signals == 0:
		recap_msg = (
			"\U0001F4CA SignalRankAI Weekly Recap\n\n"
			"No signals were sent to you this week.\n\n"
			"Remember: No signals is sometimes better than bad signals.\n\n"
			"Thank you for trading responsibly."
		)
	else:
		from collections import Counter
		assets = [t[2] for t in trades]  # asset column
		strategies = [t[9] for t in trades]  # strategy_name column
		rr_ratios = [t[7] for t in trades if t[7] is not None]
		most_active = ', '.join([a for a, _ in Counter(assets).most_common(2)]) if assets else 'N/A'
		best_strategy = Counter(strategies).most_common(1)[0][0] if strategies else 'N/A'
		avg_rr = round(sum(rr_ratios)/len(rr_ratios), 2) if rr_ratios else 'N/A'
		recap_msg = (
			f"\U0001F4CA SignalRankAI Weekly Recap\n\n"
			f"Here’s a quick overview of your past week:\n\n"
			f"• Total signals sent: {total_signals}\n"
			f"• Markets most active: {most_active}\n"
			f"• Best-performing strategy: {best_strategy}\n"
			f"• Average risk/reward: {avg_rr}\n\n"
			"Market conditions were mixed, so signal frequency was intentionally limited.\n\n"
			"Remember:\nNo signals is sometimes better than bad signals.\n\n"
			"Thank you for trading responsibly."
		)
		await update.message.reply_text(recap_msg)


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
			tier = resolve_user_tier(user_id)
			try:
				if state.has_temp_owner_sync(user_id):
					tier = "OWNER"
			except Exception:
				pass
			if tier_rank(tier) < tier_rank(min_tier):
				await update.message.reply_text("Upgrade required.")
				return
			result = func(update, context)
			if inspect.isawaitable(result):
				return await result
			return result
		return inner
	return wrapper


# /start or welcome message

async def start_command(update, context):
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
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
	# Prefer Postgres for "new user" determination when configured.
	try:
		from db.session import ENGINE, get_session
		from db.models import User
		from sqlalchemy import select
		from db.repository import get_or_create_user
		if ENGINE is not None:
			async with get_session() as session:
				res = await session.execute(select(User).where(User.telegram_user_id == int(user_id)))
				existing = res.scalar_one_or_none()
				is_new = existing is None
				await get_or_create_user(session, telegram_user_id=user_id, username=username)
				await session.commit()
		else:
			raise RuntimeError("no postgres")
	except Exception:
		try:
			from db.database import record_user_seen
			is_new = record_user_seen(user_id, username=username)
		except Exception:
			is_new = False

	# Referral attribution (only for first-time users)
	referral_outcome = None
	if ref_token:
		code = ref_token
		if code.startswith("ref_"):
			code = code[4:]
		if code:
			try:
				from db.session import ENGINE, get_session
				if ENGINE is not None:
					from db.pg_features import process_referral_start as process_referral_start_pg
					async with get_session() as session:
						referral_outcome = await process_referral_start_pg(
							session,
							referred_telegram_user_id=int(user_id),
							referral_code=str(code),
							is_new_user=bool(is_new),
						)
						await session.commit()
				else:
					raise RuntimeError("no postgres")
			except Exception:
				try:
					from db.database import process_referral_start
					referral_outcome = process_referral_start(user_id, code, is_new_user=bool(is_new))
				except Exception:
					referral_outcome = None

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

	# Notify referrer on reward
	try:
		if referral_outcome and str(referral_outcome.get("status")) == "reward_granted":
			referrer_id = int(referral_outcome.get("referrer_id"))
			days = int(referral_outcome.get("days_granted"))
			await context.bot.send_message(
				chat_id=referrer_id,
				text=f"🎉 Referral reward unlocked: +{days} days added to your subscription.\n\nUse /signals to get the latest ideas.",
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
		"\u26A0\uFE0F Disclaimer\n\n"
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
	from db.database import fetch_user_trades
	from datetime import datetime, timedelta
	user_id = update.effective_user.id
	tier = _effective_tier(user_id)
	trades = fetch_user_trades(user_id)
	# Filter trades from last 30 days
	cutoff = datetime.now() - timedelta(days=30)
	def parse_dt(row):
		# Try to parse timestamp from row, fallback to all if missing
		try:
			return datetime.fromisoformat(row[3]) if isinstance(row[3], str) else cutoff
		except Exception:
			return cutoff
	trades_30d = [t for t in trades if parse_dt(t) >= cutoff]
	total = len(trades_30d)
	if total == 0:
		msg = "No signals in the last 30 days."
		if update.message is not None:
			await update.message.reply_text(msg)
		return

	# Win rate: best-effort parse (legacy DB may not store outcomes)
	win_count = sum(1 for t in trades_30d if (len(t) > 15 and t[15] == 'TP'))
	win_rate = win_count / total if total > 0 else 0
	rr_ratios = [t[7] for t in trades_30d if t[7] is not None]
	avg_rr = round(sum(rr_ratios)/len(rr_ratios), 2) if rr_ratios else None

	if tier_rank(tier) < tier_rank("PREMIUM"):
		# Limited snapshot: no raw numbers
		bucket = "mixed"
		if win_rate >= 0.6:
			bucket = "strong"
		elif win_rate <= 0.4:
			bucket = "cautious"
		msg = (
			"📊 Performance (limited)\n\n"
			f"Recent snapshot: {bucket}.\n"
			"Outcome-tracked transparently, no profit promises.\n\n"
			"Upgrade to Premium for full stats and history."
		)
		if update.message is not None:
			await update.message.reply_text(msg)
		return

	avg_rr_str = str(avg_rr) if avg_rr is not None else "N/A"
	msg = f"Last 30 days:\n✔ Win rate: {round(win_rate*100,1)}%\n✔ Avg RR: {avg_rr_str}\n✔ Signals: {total}"
	if update.message is not None:
		await update.message.reply_text(msg)


# -------- Premium commands --------
@require_tier("PREMIUM")
async def stats_command(update, context):
	from db.database import fetch_user_trades
	user_id = update.effective_user.id
	trades = fetch_user_trades(user_id)
	msg = (
		"📈 Stats (Premium)\n\n"
		f"Signals recorded: {len(trades)}\n"
		"Use /history to view recent signals."
	)
	if update.message is not None:
		await update.message.reply_text(msg)


@require_tier("PREMIUM")
async def history_command(update, context):
	from db.database import fetch_user_trades
	user_id = update.effective_user.id
	trades = fetch_user_trades(user_id)

	asset = None
	tf = None
	if context.args:
		asset = context.args[0].upper()
		if len(context.args) > 1:
			tf = context.args[1]

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
	from db.database import get_alert_prefs, set_alert_prefs
	user_id = update.effective_user.id
	
	if not context.args:
		prefs = get_alert_prefs(user_id)
		qs = prefs.get("quiet_start_hour")
		qe = prefs.get("quiet_end_hour")
		quiet = "off" if qs is None or qe is None else f"{qs}:00–{qe}:00"
		status = "on" if prefs.get("tp_sl_enabled", True) else "off"
		if update.message is not None:
			await update.message.reply_text(f"🔔 Alerts\n\nTP/SL alerts: {status}\nQuiet hours: {quiet}\n\nUsage: /alerts on|off or /alerts quiet <start_hour> <end_hour>")
		return

	cmd = str(context.args[0]).lower()
	if cmd in {"on", "off"}:
		prefs = set_alert_prefs(user_id, tp_sl_enabled=(cmd == "on"))
		if update.message is not None:
			await update.message.reply_text("✅ Updated.")
		return
	if cmd == "quiet" and len(context.args) == 3:
		try:
			qs = int(context.args[1])
			qe = int(context.args[2])
			if not (0 <= qs <= 23 and 0 <= qe <= 23):
				raise ValueError()
			set_alert_prefs(user_id, quiet_start_hour=qs, quiet_end_hour=qe)
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
	from db.database import get_unreleased_signals
	signals = get_unreleased_signals()[:10]
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
