from telegram import Update
from telegram.ext import ContextTypes
from db.session import get_session, get_engine_for_event_loop
from config import config
from db.repository import get_active_subscription
from engine.market_state import get_market_state_async
from engine.strategies.signal_generator import SignalGenerator
from data.news import get_news_sentiment, fetch_news_headlines
import inspect
from core.redis_state import KillSwitchState, state

TIER_RANKS: dict[str, int] = {
	"FREE": 0,
	"PREMIUM": 1,
	"VIP": 2,
	"ADMIN": 3,
	"OWNER": 3,
}

def tier_rank(tier) -> int:
	return TIER_RANKS.get((tier or "").strip().upper(), 0)

def require_tier(min_tier):
	def wrapper(func):
		async def inner(update, context):
			if update.effective_user is None or update.message is None:
				return
			user_id = update.effective_user.id
			# Global kill-switch
			try:
				ks: KillSwitchState = state.get_killswitch_sync()
			except Exception:
				ks: KS = type("KS", (), {"enabled": False})()
			if getattr(ks, "enabled", False):
				await update.message.reply_text("🚨 Signals are temporarily paused.")
				return

			# Rate limit (20/min)
			try:
				limited: bool = state.rate_limited_sync(user_id, limit=20, window_seconds=60)
			except Exception:
				limited = False
			if limited:
				await update.message.reply_text("Rate limit exceeded. Please wait.")
				return
			tier: str = _effective_tier(user_id)
			if tier_rank(tier) < tier_rank(min_tier):
				try:
					from .command_access import check_command_access
					cmd_name = func.__name__.replace("_command", "").replace("async ", "").strip()
					_, reason = check_command_access(cmd_name, tier)
				except Exception:
					reason: str = f"🔒 You can't access this on {str(tier).upper()} tier.\nUse /upgrade to subscribe to unlock it."
				await update.message.reply_text(reason)
				return
			result = func(update, context)
			if inspect.isawaitable(result):
				return await result
			return result
		return inner
	return wrapper
# --- USER COMMAND: /support ---
async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	support_contact = "@theocrilox"
	await update.message.reply_text(f"For help or questions, contact support: {support_contact}")
# --- USER COMMAND: /status ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	
	tier = "free"
	expiry = None
	try:
		from signalrank_telegram.access import resolve_user_tier
		tier = str(resolve_user_tier(int(user_id))).lower()
	except Exception:
		tier = "free"
	
	# Get subscription expiry from Postgres — check premium_until first, then active Subscription
	try:
		from db.session import get_session
		from db.repository import get_or_create_user
		from db.models import Subscription
		from sqlalchemy import select, desc
		from datetime import datetime as _dt
		async with get_session() as session:
			user = await get_or_create_user(session, telegram_user_id=user_id)
			expiry = getattr(user, 'premium_until', None)
			if expiry is None:
				# Fall back to active subscription expiry
				now_dt = _dt.utcnow()
				res_sub = await session.execute(
					select(Subscription)
					.where(
						Subscription.user_id == user.id,
						Subscription.status == "active",
						Subscription.expires_at > now_dt,
					)
					.order_by(desc(Subscription.expires_at))
					.limit(1)
				)
				sub = res_sub.scalars().first()
				if sub is not None:
					expiry = sub.expires_at
	except Exception:
		pass
	
	# Get signals sent today
	signals_today = 0
	try:
		from core.redis_state import state
		from datetime import datetime
		date_str = datetime.utcnow().strftime('%Y-%m-%d')
		signals_today = int(state.get_sync(f"signals_sent:{user_id}:{date_str}") or 0)
	except Exception:
		pass
	
	limits = {"free": 2, "premium": 20, "vip": "∞", "owner": "∞", "admin": "∞"}
	limit = limits.get(tier, 2)
	
	tier_emoji = {"free": "🆓", "premium": "⭐", "vip": "👑", "owner": "🔧", "admin": "🔧"}.get(tier, "🆓")
	
	msg = f"{tier_emoji} Status: {tier.upper()}\n\n"
	if expiry:
		msg += f"📅 Expires: {expiry.strftime('%Y-%m-%d %H:%M UTC')}\n"
	msg += f"📊 Signals today: {signals_today}/{limit}\n"
	
	if tier == "free":
		msg += "\n/upgrade to unlock more signals"
	
	await update.message.reply_text(msg)

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web')))
try:
	from web.api import generate_api_key, set_user_api_key, get_user_api_key
except Exception:
	generate_api_key = lambda: "demo-key"
	set_user_api_key = lambda user_id, key: None
	get_user_api_key = lambda user_id: None

@require_tier("PREMIUM")
async def apikey_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	args = context.args or []
	if args and args[0].lower() == "regenerate":
		key: str = generate_api_key()
		set_user_api_key(user_id, key)
		await update.message.reply_text(f"🔑 Your new API key: {key}\nKeep it secret. Use it with the /signals API endpoint.")
		return
	key = get_user_api_key(user_id)
	if not key:
		key: str = generate_api_key()
		set_user_api_key(user_id, key)
	await update.message.reply_text(f"🔑 Your API key: {key}\nUse it with the /signals API endpoint. Send /apikey regenerate to reset.")
# Basic translation dictionary
TRANSLATIONS: dict[str, dict[str, str]] = {
	"en": {
		"help_title": "SignalRankAI Help",
		"dashboard": "Open your dashboard",
	},
	"es": {
		"help_title": "Ayuda de SignalRankAI",
		"dashboard": "Abrir tu panel",
	},
	"fr": {
		"help_title": "Aide SignalRankAI",
		"dashboard": "Ouvrir votre tableau de bord",
	},
}

def _t(user_id, key) -> str | None:
	lang = _get_user_language(user_id)
	return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)
from .user_prefs import user_prefs_store
# --------- LANGUAGE SELECTION COMMAND ---------
LANGUAGES: dict[str, str] = {
	"en": "English",
	"es": "Español",
	"fr": "Français",
}

def _get_user_language(user_id):
	return user_prefs_store.get_prefs(user_id).get("language", "en")

async def language_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	args = context.args or []
	if not args:
		current = _get_user_language(user_id)
		msg: str = "🌐 Select your language:\n" + "\n".join([f"/language {k} - {v}" for k, v in LANGUAGES.items()])
		msg += f"\n\nCurrent: {LANGUAGES.get(current, 'English')}"
		await update.message.reply_text(msg)
		return
	lang = args[0].lower()
	if lang not in LANGUAGES:
		await update.message.reply_text("Unsupported language. Available: " + ", ".join(LANGUAGES.keys()))
		return
	user_prefs_store.set_prefs(user_id, language=lang)
	await update.message.reply_text(f"Language set to {LANGUAGES[lang]}.")

# --------- CUSTOM SIGNAL FILTERS COMMAND ---------
@require_tier("PREMIUM")
async def filter_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	args = context.args or []
	if not args:
		prefs = user_prefs_store.get_prefs(user_id)
		filters = prefs.get("filters", {})
		if not filters:
			await update.message.reply_text("No custom filters set. Use /filter min_score 60 or /filter rr 2.0 or /filter regime TRENDING.")
		else:
			lines: list[str] = ["Your custom filters:"]
			for k, v in filters.items():
				lines.append(f"{k}: {v}")
			await update.message.reply_text("\n".join(lines))
		return
	key = args[0].lower()
	if key not in {"min_score", "rr", "regime"}:
		await update.message.reply_text("Supported filters: min_score, rr, regime. Example: /filter min_score 60")
		return
	value = args[1] if len(args) > 1 else None
	if not value:
		await update.message.reply_text("Usage: /filter <min_score|rr|regime> <value>")
		return
	filters = user_prefs_store.get_prefs(user_id).get("filters", {})
	filters[key] = value
	user_prefs_store.set_prefs(user_id, filters=filters)
	await update.message.reply_text(f"Filter set: {key} = {value}")

# --------- SCHEDULED REPORTS OPT-IN COMMAND ---------
@require_tier("PREMIUM")
async def reports_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	args = context.args or []
	if not args:
		prefs = user_prefs_store.get_prefs(user_id)
		val = prefs.get("reports_optin", False)
		msg: str = "You are currently " + ("subscribed to" if val else "not receiving") + " daily/weekly reports.\nUse /reports on or /reports off."
		await update.message.reply_text(msg)
		return
	opt = args[0].lower()
	if opt in {"on", "yes", "true"}:
		user_prefs_store.set_prefs(user_id, reports_optin=True)
		await update.message.reply_text("You will now receive daily/weekly performance summaries.")
	elif opt in {"off", "no", "false"}:
		user_prefs_store.set_prefs(user_id, reports_optin=False)
		await update.message.reply_text("You will no longer receive scheduled reports.")
	else:
		await update.message.reply_text("Usage: /reports on|off")
# --------- REFERRAL LEADERBOARD & REWARDS ---------
from db.session import get_session
from db.pg_features import get_or_create_user
from db.models import Outcome, ReferralReward, ReferralAttribution, Signal, Subscription, User
import asyncio

async def referral_leaderboard_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	if get_engine_for_event_loop() is None:
		await update.message.reply_text("Database unavailable.")
		return
	async with get_session() as session:
		# Top referrers by count
		from sqlalchemy import text
		res = await session.execute(
			text("""
			SELECT referrer_user_id, COUNT(*) as cnt
			FROM referral_attributions
			GROUP BY referrer_user_id
			ORDER BY cnt DESC
			LIMIT 10
			""")
		)
		rows = res.fetchall()
		if not rows:
			await update.message.reply_text("No referral data yet.")
			return
		# Get usernames if possible
		ids = [r[0] for r in rows]
		users = {}
		if ids:
			from sqlalchemy import text
			res2 = await session.execute(
				text("SELECT id, telegram_user_id, username FROM users WHERE id = ANY(:ids)"), {"ids": ids}
			)
			users = {r[0]: (r[1], r[2]) for r in res2.fetchall()}
		msg = "🏆 Referral Leaderboard:\n\n"
		for i, (uid, cnt) in enumerate(rows, 1):
			telegram_uid, username = users.get(uid, (None, None))
			if username:
				uname = username
			elif telegram_uid:
				uname = f"User ***{str(telegram_uid)[-3:]}"
			else:
				uname = f"User ***{str(uid)[-3:]}"
			msg += f"{i}. {uname}: {cnt} referrals\n"
		await update.message.reply_text(msg)

async def referral_rewards_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	if get_engine_for_event_loop() is None:
		await update.message.reply_text("Database unavailable.")
		return
	async with get_session() as session:
		user: User = await get_or_create_user(session, telegram_user_id=int(user_id))
		from sqlalchemy import text
		res = await session.execute(
			text("SELECT reward_type, COUNT(*) as cnt, SUM(reward_value) as total FROM referral_rewards WHERE referrer_user_id = :uid GROUP BY reward_type"),
			{"uid": user.id}
		)
		rows = res.fetchall()
		if not rows:
			msg = "No rewards earned yet. Refer friends to earn rewards!"
		else:
			msg = "🎁 Your Referral Rewards:\n"
			for rtype, cnt, total in rows:
				msg += f"{rtype}: {cnt} times, total value: {total}\n"
		
		# Show progress toward next reward
		from db.pg_features import get_referral_progress
		progress = await get_referral_progress(session, referrer_telegram_user_id=int(user_id))
		total = progress.get("total", 0)
		needed = progress.get("needed_for_next", 3)
		msg += f"\n\n📊 Progress: {total} total referrals\n"
		msg += f"🎯 {needed} more referrals for next reward (7 premium days)"
		await update.message.reply_text(msg)
from engine.signal_analytics import signal_analytics
# --------- ADMIN ANALYTICS COMMANDS ---------
from config import OWNER_IDS, ADMIN_IDS
def _is_admin(user_id) -> bool:
	"""Return True if user has admin or owner privileges.

	Checks (in order):
	  1. OWNER_IDS config set (from OWNER_IDS / OWNER_TELEGRAM_ID / OWNER_TELEGRAM_IDS env vars)
	  2. ADMIN_IDS config set (from ADMIN_IDS or ADMIN_ID env var, cast to int)
	  3. ADMIN_ID env var read directly (belt-and-suspenders for fresh reads)
	  4. DB tier == ADMIN or OWNER
	"""
	try:
		uid = int(user_id)
	except Exception:
		return False
	try:
		if uid in OWNER_IDS:
			return True
	except Exception:
		pass
	try:
		if uid in ADMIN_IDS:
			return True
	except Exception:
		pass
	# Belt-and-suspenders: read ADMIN_ID env var directly each call
	try:
		_aid = (os.getenv("ADMIN_ID") or "").strip()
		if _aid and uid == int(_aid):
			return True
	except Exception:
		pass
	try:
		tier = _effective_tier(uid).upper()
		return tier in ("ADMIN", "OWNER")
	except Exception:
		return False


# --------- ADMIN /assets COMMAND ---------
async def assets_command(update, context) -> None:
	"""Admin: manage the pinned asset universe.

	Usage:
	  /assets list            – show all managed assets
	  /assets add BTCUSDT     – pin an asset
	  /assets remove BTCUSDT  – unpin an asset
	"""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("⛔ Access Denied.")
		return

	from db.session import get_session
	from db.pg_features import (
		get_active_managed_assets,
		add_managed_asset,
		remove_managed_asset,
		list_all_managed_assets,
	)
	from data.fetcher import get_asset_type

	args = context.args or []
	subcmd = args[0].lower() if args else "list"

	if subcmd == "list":
		async with get_session() as session:
			rows = await list_all_managed_assets(session)
		if not rows:
			await update.message.reply_text("No managed assets yet.\nUse /assets add <SYMBOL> to pin one.")
			return
		lines: list[str] = []
		for r in rows:
			status = "✅" if r.is_active else "❌"
			lines.append(f"{status} `{r.symbol}` ({r.asset_type})")
		await update.message.reply_text(
			f"*Managed Assets ({len(rows)}):*\n" + "\n".join(lines),
			parse_mode="Markdown",
		)
		return

	if subcmd == "add":
		if len(args) < 2:
			await update.message.reply_text("Usage: /assets add <SYMBOL>")
			return
		symbol = args[1].upper().strip()
		atype = get_asset_type(symbol)
		async with get_session() as session:
			await add_managed_asset(
				session, symbol=symbol, asset_type=atype,
				added_by=update.effective_user.id,
			)
			await session.commit()
		await update.message.reply_text(f"✅ `{symbol}` pinned ({atype}).", parse_mode="Markdown")
		return

	if subcmd == "remove":
		if len(args) < 2:
			await update.message.reply_text("Usage: /assets remove <SYMBOL>")
			return
		symbol = args[1].upper().strip()
		async with get_session() as session:
			found = await remove_managed_asset(session, symbol=symbol)
			await session.commit()
		if found:
			await update.message.reply_text(f"❌ `{symbol}` unpinned.", parse_mode="Markdown")
		else:
			await update.message.reply_text(f"`{symbol}` was not in the managed list.", parse_mode="Markdown")
		return

	await update.message.reply_text(
		"Usage:\n/assets list\n/assets add <SYMBOL>\n/assets remove <SYMBOL>"
	)


async def admin_top_assets_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	if not _is_admin(user_id):
		await update.message.reply_text("Admin only.")
		return
	stats = signal_analytics.get_stats()
	delivery = stats.get('delivery_stats', {})
	asset_counts = {}
	for k, v in delivery.items():
		if k.startswith('delivered_'):
			asset = k[len('delivered_'):]
			asset_counts[asset] = asset_counts.get(asset, 0) + v
	top = sorted(asset_counts.items(), key=lambda x: x[1], reverse=True)[:10]
	msg: str = "\n".join([f"{a}: {c}" for a, c in top]) or "No data."
	await update.message.reply_text(f"Top Assets (delivered):\n{msg}")

async def admin_top_strategies_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	if not _is_admin(user_id):
		await update.message.reply_text("Admin only.")
		return
	from datetime import datetime, timedelta, timezone
	from sqlalchemy import select, func, desc
	from db.session import get_session, get_engine_for_event_loop
	from db.models import Signal

	engine = get_engine_for_event_loop()
	if engine is None:
		await update.message.reply_text("Database unavailable.")
		return

	cutoff = datetime.now(timezone.utc) - timedelta(days=30)
	async with get_session() as session:
		res = await session.execute(
			select(Signal.strategy_name, func.count(Signal.signal_id))
			.where(Signal.created_at >= cutoff)
			.group_by(Signal.strategy_name)
			.order_by(desc(func.count(Signal.signal_id)))
			.limit(10)
		)
		rows = res.fetchall()

	if not rows:
		await update.message.reply_text("No strategy data available (last 30d).")
		return

	lines = [f"{name}: {cnt}" for name, cnt in rows]
	await update.message.reply_text("Top Strategies (last 30d):\n" + "\n".join(lines))

async def admin_user_engagement_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	if not _is_admin(user_id):
			await update.message.reply_text("Admin only.")
			return
	stats = signal_analytics.get_stats()
	engagement = stats.get('user_engagement', {})
	top = sorted(engagement.items(), key=lambda x: x[1], reverse=True)[:10]
	msg: str = "\n".join([f"{u}: {c}" for u, c in top]) or "No data."
	await update.message.reply_text(f"Top Users (engagement):\n{msg}")
# --------- ADMIN /SELFHECK COMMAND ---------
@require_tier("ADMIN")
async def selfcheck_command(update, context) -> None:
	"""Admin/Owner: Show quick health summary of the system."""
	checks = []
	
	# DB check
	try:
		from db.session import get_engine_for_event_loop
		engine = get_engine_for_event_loop()
		checks.append("✅ Database: connected" if engine else "❌ Database: not connected")
	except Exception:
		checks.append("❌ Database: error")
	
	# Redis check
	try:
		from core.redis_state import state
		state.get_sync("health_check")
		checks.append("✅ Redis: connected")
	except Exception:
		checks.append("❌ Redis: not connected")
	
	# yfinance check
	try:
		import yfinance as yf
		t = yf.Ticker("AAPL")
		p = t.fast_info.get('lastPrice')
		checks.append(f"✅ yfinance: working (AAPL=${p:.2f})" if p else "⚠️ yfinance: no price")
	except Exception:
		checks.append("❌ yfinance: not available")
	
	# Bot token check
	try:
		from signalrank_telegram.bot import application
		bot = application.bot
		me = await bot.get_me()
		checks.append(f"✅ Bot: @{me.username}")
	except Exception:
		checks.append("❌ Bot: token invalid")
	
	# Last signal check
	try:
		from db.session import get_session
		from sqlalchemy import select, desc
		from db.models import Signal
		async with get_session() as session:
			res = await session.execute(select(Signal).order_by(desc(Signal.created_at)).limit(1))
			last = res.scalar_one_or_none()
			if last:
				checks.append(f"✅ Last signal: {last.asset} {last.timeframe} at {last.created_at}")
			else:
				checks.append("⚠️ Last signal: none found")
	except Exception:
		checks.append("⚠️ Last signal: check failed")
	
	if update.message is not None:
		await update.message.reply_text("🔍 System Health\n\n" + "\n".join(checks))
from .user_prefs import user_prefs_store
from telegram import Update
from telegram.ext import ContextTypes
# --------- NOTIFICATION CUSTOMIZATION COMMAND ---------
@require_tier("PREMIUM")
async def notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Let users customize which assets, timeframes, or strategies they want to receive signals for.
	Usage:
	  /notify assets BTCUSDT,ETHUSDT
	  /notify timeframes 1h,4h
	  /notify strategies momentum,trend
	  /notify clear
	  /notify (shows current prefs)
	"""
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	args: list[str] = context.args or []
	if not args:
		prefs = user_prefs_store.get_prefs(user_id)
		if not prefs:
			await update.message.reply_text("No custom notification preferences set. You will receive all signals allowed by your tier.")
		else:
			lines: list[str] = ["Your notification preferences:"]
			for k, v in prefs.items():
				lines.append(f"{k}: {', '.join(sorted(v))}")
			await update.message.reply_text("\n".join(lines))
		return
	cmd: str = args[0].lower()
	if cmd == "clear":
		user_prefs_store.clear_prefs(user_id)
		await update.message.reply_text("✅ Notification preferences cleared. You will receive all signals allowed by your tier.")
		return
	if len(args) < 2:
		await update.message.reply_text("Usage: /notify assets|timeframes|strategies <comma-separated-list> OR /notify clear")
		return
	values: list[str] = [x.strip().upper() for x in " ".join(args[1:]).split(",") if x.strip()]
	if cmd == "assets":
		user_prefs_store.set_prefs(user_id, assets=values)
		await update.message.reply_text(f"✅ Assets updated: {', '.join(values)}")
	elif cmd == "timeframes":
		user_prefs_store.set_prefs(user_id, timeframes=values)
		await update.message.reply_text(f"✅ Timeframes updated: {', '.join(values)}")
	elif cmd == "strategies":
		user_prefs_store.set_prefs(user_id, strategies=values)
		await update.message.reply_text(f"✅ Strategies updated: {', '.join(values)}")
	else:
		await update.message.reply_text("Usage: /notify assets|timeframes|strategies <comma-separated-list> OR /notify clear")
# --------- FEEDBACK COMMAND ---------
from .feedback import feedback_store
@require_tier("PREMIUM")
async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Allow non-free users to rate a signal or report an issue. Usage: /feedback <signal_ref> <rating|issue> [comment]"""
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	if tier.strip().upper() == "FREE":
		await update.message.reply_text("Feedback is only available for Premium and VIP users. Upgrade to unlock this feature.")
		return
	args: list[str] = context.args or []
	if len(args) < 2:
		await update.message.reply_text("Usage: /feedback <signal_ref> <rating|issue> [comment]")
		return
	signal_ref: str = str(args[0]).strip()
	rating_or_issue: str = str(args[1]).strip().lower()
	comment: str | None = " ".join(args[2:]).strip() if len(args) > 2 else None

	# Accept rating as 1-5 or issue as text
	rating = None
	issue = None
	if rating_or_issue.isdigit() and 1 <= int(rating_or_issue) <= 5:
		rating = int(rating_or_issue)
	else:
		issue: str = rating_or_issue

	# Optionally: resolve signal_id from short ref (first 8 chars)
	signal_id = None
	try:
		from db.session import get_session, get_engine_for_event_loop
		if get_engine_for_event_loop() is not None:
			from db.pg_features import get_signal_id_by_short_ref
			async with get_session() as session:
				signal_id = await get_signal_id_by_short_ref(session, signal_ref)
	except Exception:
		pass
	if not signal_id:
		signal_id: str = signal_ref  # fallback: use as-is

	feedback_store.add_feedback(user_id, signal_id, rating=rating, issue=issue, comment=comment)
	await update.message.reply_text("✅ Feedback received. Thank you!")

	# Optionally flush feedback every 10 submissions
	if len(feedback_store.get_feedback(signal_id)) % 10 == 0:
		feedback_store.flush()

# /pricing command
import os
import logging
import inspect
import socket
import random
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from core.redis_state import KillSwitchState, state
from .access import resolve_user_tier


_audit_logger: logging.Logger = logging.getLogger("audit")
logger: logging.Logger = logging.getLogger(__name__)

_BOOT_TS: str = datetime.now(timezone.utc).isoformat()


async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.message is None or update.effective_user is None:
		return
	# Owner-only (avoid exposing deployment fingerprints publicly)
	if _effective_tier(update.effective_user.id) != "OWNER":
		return
	# Non-sensitive fingerprint to confirm which build is running.
	mode: str = (getattr(config, "RUN_MODE", "engine") or "engine").strip().lower()
	lines: list[str] = [
		"SignalRankAI /version",
		f"boot_utc: {_BOOT_TS}",
		f"run_mode: {mode}",
		f"host: {socket.gethostname()}",
		f"railway_service: {config.RAILWAY_SERVICE_NAME}",
		f"railway_env: {config.RAILWAY_ENVIRONMENT}",
		f"railway_deployment: {config.RAILWAY_DEPLOYMENT_ID}",
		f"git_sha: {config.GIT_COMMIT_SHA}",
	]
	await update.message.reply_text("\n".join(lines))


def _effective_tier(user_id: int) -> str:
	try:
		t: str = resolve_user_tier(user_id)
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
	user_id: int = update.effective_user.id
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



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	from .command_access import get_help_message
	# get_help_message() returns HTML-formatted text
	msg: str = f"<b>{_t(user_id, 'help_title')}</b>\n\n" + get_help_message(tier)

	# Append tier-specific command hints
	tier_upper = tier.strip().upper()
	if tier_upper == "FREE":
		msg += (
			"\n\n💡 <b>Upgrade to unlock more:</b>\n"
			"  /tiers — Compare plans\n"
			"  /upgrade — Subscribe now\n"
			"  /referral — Earn free days"
		)
	elif tier_upper == "PREMIUM":
		msg += (
			"\n\n⚙️ <b>Your PREMIUM commands:</b>\n"
			"  /setlot — Set lot size for MT5 auto-exec\n"
			"  /connect_broker — Link your MT5 account\n"
			"  /mt5_status — Check linked account\n"
			"  /mystats — Personal P&amp;L stats\n"
			"  /referral — Earn +7 days per referral"
		)
	elif tier_upper in ("VIP", "OWNER", "ADMIN"):
		msg += (
			"\n\n👑 <b>Your VIP commands:</b>\n"
			"  /setrisk — Set risk % per trade\n"
			"  /setlot — Override lot size\n"
			"  /connect_broker — Link/update MT5\n"
			"  /mt5_status — Account details\n"
			"  /mystats — Personal P&amp;L stats\n"
			"  /referral — Earn +7 days per referral"
		)

	# Add dashboard link for eligible users
	if tier_upper in {"PREMIUM", "VIP", "ADMIN", "OWNER"}:
		base_url = os.getenv("DASHBOARD_URL")
		if base_url:
			sep = "&amp;" if "?" in base_url else "?"
			dashboard_url: str = f"{base_url}{sep}uid={user_id}"
			dashboard_text: str = _t(user_id, 'dashboard')
			msg += f"\n\n🌐 <a href=\"{dashboard_url}\">{dashboard_text}</a>"
	await update.message.reply_text(msg, disable_web_page_preview=True, parse_mode="HTML")

# --------- MYID COMMAND ---------
async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	msg: str = f"Your Telegram user ID: `{user_id}`\nYour current tier: *{tier}*"
	await update.message.reply_text(msg, parse_mode="Markdown")

# --------- DASHBOARD COMMAND ---------
@require_tier("PREMIUM")
async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	if tier.strip().upper() not in {"PREMIUM", "VIP", "ADMIN", "OWNER"}:
		await update.message.reply_text("The dashboard is only available for Premium, VIP, and above.")
		return
	base_url = os.getenv("DASHBOARD_URL")
	if not base_url:
		await update.message.reply_text("Dashboard is coming soon.")
		return
	sep = "&" if "?" in base_url else "?"
	dashboard_url: str = f"{base_url}{sep}uid={user_id}"
	await update.message.reply_text(f"🌐 [Open your dashboard]({dashboard_url})", disable_web_page_preview=True, parse_mode="Markdown")


async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show user's signals with tier-specific formatting.
	
	FREE: Show signals they received (delivered)
	PREMIUM/VIP: Show unresolved signals (ongoing trades)
	"""
	if await _public_guard(update):
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	
	# Import freshness validation at function level
	from engine.price_validator import enrich_signal_with_live_price

	# Owner and admin always get VIP format
	if tier.lower() in {"owner", "admin"}:
		tier = "VIP"

	# Prefer high-quality fresh signals if any exist (even if not delivered yet).
	try:
		engine = get_engine_for_event_loop()
		if engine is not None:
			from datetime import datetime, timedelta, timezone
			from sqlalchemy import select, desc
			from db.models import Signal as SignalModel
			async with get_session() as session:
				cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
				res = await session.execute(
					select(SignalModel)
					.where(SignalModel.created_at >= cutoff)
					.order_by(desc(SignalModel.created_at))
					.limit(50)
				)
				recent_rows = list(res.scalars().all())
				recent_signals = []
				for r in recent_rows:
					sig_dict = {
						"signal_id": r.signal_id,
						"asset": r.asset,
						"timeframe": r.timeframe,
						"direction": r.direction,
						"entry": r.entry,
						"stop_loss": r.stop_loss,
						"take_profit": r.take_profit,
						"rr_ratio": r.rr_estimate,
						"score": r.score,
						"confidence": getattr(r, "confidence", 0.5),
						"regime": getattr(r, "regime", "NEUTRAL"),
						"strength": getattr(r, "strength", 0.5),
						"ml_probability": getattr(r, "ml_probability", 0.5),
						"strategy_name": r.strategy_name,
						"strategy_group": r.strategy_group,
						"created_at": r.created_at,
					}
					
					# Enrich with live price and freshness info
					try:
						sig_dict = enrich_signal_with_live_price(sig_dict)
					except Exception:
						pass
					
					recent_signals.append(sig_dict)

				if recent_signals:
					from .formatter import format_signal
					msg_lines: list[str] = []
					shown = 0
					for s in recent_signals:
						formatted = format_signal(s, user_tier=tier)
						if not formatted:
							continue
						msg_lines.append(formatted)
						shown += 1
						if shown >= (3 if tier.lower() in {"free"} else 5):
							break
					if msg_lines:
						await update.message.reply_text("\n\n".join(msg_lines))
						return
	except Exception:
		pass

	signals_list: list[dict] = []
	
	# FREE tier: show delivered signals only - now sample 2 random signals with score >= 55
	if tier_rank(tier) < tier_rank("PREMIUM"):
		try:
			from db.session import get_session
			engine = get_engine_for_event_loop()
			if engine is not None:
				from db.pg_features import list_signals_sent_today
				async with get_session() as session:
					# Fetch ALL signals delivered to user today (no limit)
					rows: list[Signal] = await list_signals_sent_today(session, telegram_user_id=int(user_id))
					signals_list = []
					for r in rows:
						sig_dict = {
							"signal_id": r.signal_id,
							"asset": r.asset,
							"timeframe": r.timeframe,
							"direction": r.direction,
							"entry": r.entry,
							"stop_loss": r.stop_loss,
							"take_profit": r.take_profit,
							"rr_ratio": r.rr_estimate,
							"score": r.score,
							"created_at": getattr(r, "created_at", None),
						}
						
						# Enrich with live price and freshness info
						try:
							sig_dict = enrich_signal_with_live_price(sig_dict)
						except Exception:
							pass
						
						signals_list.append(sig_dict)
		except Exception as e:
			_audit_logger.error(f"Error fetching delivered signals for {user_id}: {e}")
			signals_list = []
		
		if not signals_list:
			if update.message is not None:
				await update.message.reply_text("✅ No signals delivered today.")
			return

		# Filter by score in 45–75 and sample any 2 at random
		eligible = []
		for s in signals_list:
			try:
				score_val = float(s.get('score') or 0)
			except Exception:
				score_val = 0.0
			if 45.0 <= score_val <= 75.0:
				eligible.append(s)

		if not eligible:
			if update.message is not None:
				await update.message.reply_text("⚠️ No signals above 55 score today. Upgrade for full access or check back later.")
			return
		picked = eligible if len(eligible) <= 2 else random.sample(eligible, 2)
		total_signals: int = len(eligible)
		lines: list[str] = [f"🆓 Today's Signals (showing {len(picked)} of {total_signals})", ""]
		for i, s in enumerate(picked, 1):
			entry = float(s.get('entry') or 0)
			sig_id = s.get('signal_id', 'N/A')
			sig_id_short = sig_id[:8]
			lines.append(
				f"{i}. {s.get('asset')} {s.get('timeframe')} {s.get('direction').upper()}\n"
				f"   Reference: `{sig_id_short}...` | Entry: {entry:.4f}\n"
				f"   /outcome {sig_id_short}"
			)
		lines += ["", "💡 Use /outcome <reference> to check if you hit TP/SL", "👆 Upgrade to PREMIUM for more signals and details."]
		if update.message is not None:
			await update.message.reply_text("\n".join(lines))
		return
	
	# PREMIUM/VIP: show unresolved signals (ongoing trades)
	unresolved_signals: list[dict] = []
	try:
		from db.session import get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
			from db.pg_features import list_unresolved_signals_for_user
			async with get_session() as session:
				rows: list[Signal] = await list_unresolved_signals_for_user(session, telegram_user_id=int(user_id))
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

	# Tier-based filtering
	tier_norm: str = str(tier or "").strip().lower()
	is_vip: bool = tier_norm in {"vip", "owner", "admin"}
	filtered_signals = []
	for s in unresolved_signals:
		try:
			score_val = float(s.get('score') or 0)
		except Exception:
			score_val = 0.0
		if is_vip:
			# VIP/Owner/Admin: show all signals with score >= 55
			if score_val >= 55.0:
				filtered_signals.append(s)
		else:
			# Premium: show signals in 55–75 band
			if 55.0 <= score_val <= 75.0:
				filtered_signals.append(s)

	if not filtered_signals:
		# Fallback: show any signals delivered today (even if already resolved/archived)
		delivered_today: list[dict] = []
		try:
			from db.session import get_session
			engine = get_engine_for_event_loop()
			if engine is not None:
				from db.pg_features import list_signals_sent_today
				async with get_session() as session:
					# type: AsyncSession
					rows: list[Signal] = await list_signals_sent_today(session, telegram_user_id=int(user_id))
					delivered_today = [
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
		except Exception:
			delivered_today = []

		if delivered_today:
			lines: list[str] = ["📬 Delivered today (latest signals):", ""]
			for i, s in enumerate(delivered_today[:10], 1):
				ref = str(s.get("signal_id") or "N/A")
				ref_short: str = ref[:8]
				try:
					score_val = float(s.get("score") or 0)
				except Exception:
					score_val = 0.0
				entry_val = 0.0
				try:
					entry_val = float(s.get("entry") or 0)
				except Exception:
					entry_val = 0.0
				lines.append(
					f"{i}. {s.get('asset')} {s.get('timeframe')} {str(s.get('direction') or '').upper()} | Score {score_val:.2f}\n"
					f"   Ref: {ref_short} | Entry: {entry_val:.4f}"
				)
			lines += ["", "Use /outcome <ref> to check if you hit TP/SL."]
			if update.message is not None:
				await update.message.reply_text("\n".join(lines))
			return

		if update.message is not None:
			await update.message.reply_text(
				"✅ No unresolved signals in your range. Premium shows score 55–75. VIP/Owner/Admin shows all signals."
			)
		return

	# PREMIUM/VIP: detailed formatting per tier with new ranges
	from .formatter import format_signal
	import json
	
	total_active: int = len(filtered_signals)
	if update.message is not None and total_active > 0:
		if is_vip:
			await update.message.reply_text(f"📊 Your Active Signals ({total_active} with score ≥ 55):\n\n")
		else:
			await update.message.reply_text(f"📊 Your Active Signals ({total_active} between 55–75 score):\n\n")
	
	for idx, s in enumerate(filtered_signals, 1):
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
					take_profit: float = float(tp_list[0]) if tp_list else 0.0
				elif isinstance(tp_raw, list):
					take_profit: float = float(tp_raw[0]) if tp_raw else 0.0
				else:
					take_profit = float(tp_raw or 0)
			except Exception:
				take_profit = 0.0
			
			regime = s.get('regime', 'NEUTRAL')
			ml_prob = float(s.get('ml_probability') or 0.5)

			merits = []
			demerits = []
			if confidence >= 0.7:
				merits.append("Strong confidence")
			elif confidence < 0.55:
				demerits.append("Low confidence")
			if rr >= 2.0:
				merits.append("Excellent R/R (≥2.0)")
			elif rr < 1.5:
				demerits.append("Weak R/R (<1.5)")
			if ml_prob >= 0.65:
				merits.append("ML model agrees")
			elif ml_prob < 0.4:
				demerits.append("ML model cautious")
			if regime and str(regime).upper() != "NEUTRAL":
				merits.append(f"Regime: {regime}")
			merits_text: str = ", ".join(merits) if merits else "Balanced setup"
			demerits_text: str = ", ".join(demerits) if demerits else "No major drawbacks"
			
			# Calculate entry/exit advice
			if s.get('direction', '').upper() == 'LONG':
				entry_advice: str = f"Buy on dip to {entry:.4f}"
				exit_advice: str = f"Take partial profit at {take_profit:.4f}, trail SL to {stop_loss:.4f}"
			else:
				entry_advice: str = f"Sell on rally to {entry:.4f}"
				exit_advice: str = f"Take partial profit at {take_profit:.4f}, trail SL to {stop_loss:.4f}"
			
			if is_vip:
				# Full advice for VIP
				msg: str = (
					f"🟢 VIP Signal: {s.get('asset')} ({s.get('timeframe')})\n"
					f"ID: `{sig_id}`\n\n"
					f"Setup: {s.get('direction').upper()} {s.get('strategy_name')}\n"
					f"Regime: {regime} | **Score**: {score:.1f}/100\n\n"
					f"Entry: {entry:.4f}\n"
					f"SL: {stop_loss:.4f}\n"
					f"TP: {take_profit:.4f}\n"
					f"R/R: {rr:.2f}:1\n\n"
					f"Confidence: {confidence*100:.0f}% | ML: {ml_prob*100:.0f}%\n\n"
					f"✅ Merits: {merits_text}\n"
					f"⚠️ Demerits: {demerits_text}\n\n"
					f"📌 Entry Strategy: {entry_advice}\n"
					f"📌 Exit Strategy: {exit_advice}\n"
					f"📌 Risk: {stop_loss:.4f} - {entry:.4f} = {abs(entry - stop_loss):.4f} pips\n\n"
					f"📍 /outcome {sig_id[:8]} for current position"
				)
			else:
				# Limited advice for PREMIUM
				msg: str = (
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


async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	arg: str = (context.args[0] if context.args else "").strip() if context.args else ""
	if not arg:
		await update.message.reply_text("Usage: /signal <reference> OR /signal all")
		return

	def _as_float(v) -> float | None:
		try:
			return float(v)
		except Exception:
			return None

	def _parse_tp(tp_raw) -> None | float:
		if tp_raw is None:
			return None
		if isinstance(tp_raw, (int, float)):
			return float(tp_raw)
		s: str = str(tp_raw).strip()
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
		s: str = (symbol or "").upper().strip()
		return s.endswith("USDT") or s.endswith("USDC") or s.endswith("BUSD")

	def _binance_symbol(asset: str) -> str:
		a: str = (asset or "").upper().strip()
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
		a: str = (asset or "").upper().strip()
		a: str = a.replace("/", "").replace("-", "")
		# Normalize USD suffix to USDT
		if a.endswith("USD") and not a.endswith("USDT"):
			a: str = a[:-3] + "USDT"
		return a

	def _current_price(asset: str) -> float | None:
		"""Fetch current price from live market data. Supports crypto, FX, and stocks."""
		try:
			from data.fetcher import get_candles, get_asset_type
			
			asset_type: str = get_asset_type(asset)
			if asset_type not in {"crypto", "fx", "stock"}:
				asset_type = "crypto"
			
			# Try short timeframes first; fall back if unavailable
			candles = []
			for tf in ("1m", "5m", "15m"):
				candles: list[dict] = get_candles(asset, tf)
				if candles:
					break
			
			if not candles:
				# Last-resort fallbacks per asset type
				# 1) Crypto: Try Bybit spot tickers, then Yahoo last close
				try:
					atype: str = asset_type
					if atype == "crypto":
						# Bybit spot ticker
						import requests
						sym: str = (asset or "").upper().replace("/", "").replace("-", "")
						if sym.endswith("USD") and not sym.endswith("USDT"):
							sym: str = sym[:-3] + "USDT"
						url = "https://api.bybit.com/v5/market/tickers"
						params: dict[str, str] = {"category": "spot", "symbol": sym}
						try:
							resp: Response = requests.get(url, params=params, timeout=8)
							data = resp.json() if resp.ok else {}
							result = (data.get("result") or {}).get("list") or []
							if isinstance(result, list) and result:
								last_price = result[0].get("lastPrice")
								if last_price is not None:
									return float(last_price)
						except Exception:
							pass

						# Yahoo Finance quick last close
						try:
							import yfinance as yf
							ysym: str = (asset or "").upper()
							if ysym.endswith("USDT"):
								base: str = ysym[:-4]
								ysym: str = f"{base}-USD"
							tkr = yf.Ticker(ysym)
							h = tkr.history(period="1d", interval="1m")
							if not h.empty:
								return float(h["Close"].iloc[-1])
						except Exception:
							pass

					# 2) FX/Stocks: Yahoo last close best-effort
					if atype in {"fx", "stock"}:
						try:
							import yfinance as yf
							ysym: str = (asset or "").upper().replace("_", "").replace("-", "")
							if atype == "fx" and "/" not in ysym and len(ysym) == 6:
								ysym: str = f"{ysym[:3]}{ysym[3:]}=X"
							tkr = yf.Ticker(ysym)
							h = tkr.history(period="1d", interval="1m")
							if not h.empty:
								return float(h["Close"].iloc[-1])
						except Exception:
							pass
				except Exception:
					pass
				return None
			
			latest = candles[-1]
			close_price = latest.get("close")
			
			if close_price is not None:
				return float(close_price)
			
			return None
		except Exception as e:
			logging.getLogger(__name__).warning(f"_current_price failed for {asset}: {e}")
			return None

	def _position_advice(*, direction: str, entry: float, sl: float, tp: float, price: float) -> tuple[str, dict]:
		"""Return (advice_text, metrics)."""
		direction = (direction or "").lower().strip()
		risk: float = abs(entry - sl)
		reward: float = abs(tp - entry)
		metrics: dict = {"risk": risk, "reward": reward}
		if risk <= 0 or reward <= 0:
			return ("Manage risk carefully. Consider waiting for clearer conditions.", metrics)

		if direction == "long":
			pl_pct: float = ((price - entry) / entry) * 100.0
			progress: float = (price - entry) / (tp - entry) if (tp - entry) != 0 else 0.0
			dist_to_sl: float = (price - sl)
		else:
			pl_pct: float = ((entry - price) / entry) * 100.0
			progress: float = (entry - price) / (entry - tp) if (entry - tp) != 0 else 0.0
			dist_to_sl: float = (sl - price)

		metrics.update({"pl_pct": pl_pct, "progress": progress})
		near_sl: bool = (dist_to_sl / risk) <= 0.2
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
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is None:
			raise RuntimeError("Postgres not configured")
		from db.pg_features import list_signals_sent_today, get_delivered_signal_by_ref
		from .formatter import format_signal, format_signal_free_limited

		if arg.lower() == "all":
			async with get_session() as session:
				rows: list[Signal] = await list_signals_sent_today(session, telegram_user_id=int(user_id))
				await session.commit()
			if not rows:
				await update.message.reply_text("No signals delivered to you today.")
				return
			lines: list[str] = ["📌 Today’s signals:", ""]
			for s in rows[:20]:
				ref = str(getattr(s, "signal_id", "") or "")
				lines.append(f"• {ref} — {s.asset} {s.timeframe} {s.direction}")
			await update.message.reply_text("\n".join(lines))
			return

		async with get_session() as session:
			sig: Signal | None = await get_delivered_signal_by_ref(session, telegram_user_id=int(user_id), ref=str(arg))
			oc = None
			if sig is not None:
				try:
					from db.pg_features import get_outcome_for_signal
					oc: Outcome | None = await get_outcome_for_signal(session, str(sig.signal_id))
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
			"ml_probability": getattr(sig, "ml_probability", None),
			"created_at": getattr(sig, "created_at", None),
		}
		
		# Enrich signal with live price and freshness info
		staleness_warning = None
		try:
			from engine.price_validator import (
				enrich_signal_with_live_price, 
				is_signal_fresh, 
				get_asset_type
			)
			from core.tier_constants import MAX_SIGNAL_AGE_SECONDS
			
			sig_dict = enrich_signal_with_live_price(sig_dict)
			
			# Check if signal is stale
			is_fresh, fresh_reason = is_signal_fresh(sig_dict)
			if not is_fresh:
				staleness_warning = f"⚠️ Warning: Signal is stale ({fresh_reason})"
			else:
				# Check age against threshold
				age_seconds = sig_dict.get('signal_age_seconds')
				if age_seconds:
					asset = sig_dict.get('asset', '')
					asset_type = get_asset_type(asset)
					max_age = MAX_SIGNAL_AGE_SECONDS.get(asset_type, 300)
					# Warning if over 50% of max age
					if age_seconds > (max_age * 0.5):
						age_minutes = int(age_seconds / 60)
						staleness_warning = f"⏰ Signal is {age_minutes} minutes old"
		except Exception as e:
			import logging
			logging.getLogger(__name__).debug(f"Failed to check signal freshness: {e}")
		
		# Enrich with entry_status and current price
		entry: float | None = _as_float(sig_dict.get("entry"))
		asset: str = str(sig_dict.get("asset") or "").upper()
		price = None
		entry_status = "UNKNOWN"
		
		if entry is not None and _is_crypto(asset):
			price: float | None = _current_price(asset)
			if price is not None and entry > 0:
				distance_pct: float = abs(price - entry) / entry * 100.0
				if distance_pct <= 5.0:
					entry_status = "AT_ENTRY"
				elif price < entry:
					entry_status = "PENDING_ENTRY"
				else:
					entry_status = "PENDING_ENTRY"
				sig_dict["entry_status"] = entry_status
				sig_dict["current_price"] = price
				sig_dict["distance_pct"] = distance_pct
		if oc is not None:
			status: str = str(getattr(oc, "status", "") or "").lower()
			r: os.Any | None = getattr(oc, "r_multiple", None)
			pct: os.Any | None = getattr(oc, "percent", None)
			label: str = "PROFIT ✅" if status.startswith("tp") else ("LOSS ❌" if status == "sl" else status.upper())
			
			# Show entry status with outcome
			entry_status = sig_dict.get("entry_status", "UNKNOWN")
			if entry_status == "AT_ENTRY":
				position_lines.append(f"✅ Entry Status: At entry zone")
			elif entry_status == "PENDING_ENTRY":
				position_lines.append(f"⏳ Entry Status: Was pending when signal sent")
			
			position_lines.append(f"📊 Outcome: {label} ({status})")
			if r is not None:
				position_lines.append(f"💰 R-Multiple: {float(r):.2f}R")
			if pct is not None:
				position_lines.append(f"📈 Move: {float(pct):.2f}%")
			advice_line: str = f"✅ This signal has a completed outcome. Use /outcome {str(arg)[:8]} for full details."
		else:
			# Show entry status for live signals
			entry_status = sig_dict.get("entry_status", "UNKNOWN")
			current_price = sig_dict.get("current_price")
			distance_pct = sig_dict.get("distance_pct")
			
			if current_price is not None and distance_pct is not None:
				if entry_status == "AT_ENTRY":
					position_lines.append(f"✅ Entry Status: At entry zone ({distance_pct:+.2f}%)")
				elif entry_status == "PENDING_ENTRY":
					position_lines.append(f"⏳ Entry Status: Awaiting entry ({distance_pct:+.2f}%)")
				else:
					position_lines.append(f"❓ Entry Status: Unknown")
				position_lines.append(f"Current price: {current_price:.6g}")
			
			# Live estimate (crypto only)
			if entry is not None and sl is not None and tp is not None:
				price: float | None = _current_price(str(sig_dict.get("asset") or ""))
				if price is not None:
					adv, metrics = _position_advice(
						direction=str(sig_dict.get("direction") or ""),
						entry=float(entry),
						sl=float(sl),
						tp=float(tp),
						price=float(price),
					)
					try:
						position_lines.append(f"P/L (est.): {float(metrics.get('pl_pct')):.2f}%")
					except Exception:
						pass
					try:
						position_lines.append(f"Progress to TP (est.): {max(0.0, min(1.0, float(metrics.get('progress')))) * 100.0:.0f}%")
					except Exception:
						pass
					advice_line: str = adv
				else:
					position_lines.append("Live position: unavailable right now.")
					advice_line = "Check later for a live update."

		if tier_rank(tier) < tier_rank("PREMIUM"):
			base: str = format_signal_free_limited(sig_dict)
			if staleness_warning:
				base = f"{staleness_warning}\n\n{base}"
			if position_lines or advice_line:
				base += "\n\n📍 Position (best-effort)\n" + "\n".join(position_lines)
				if advice_line:
					base += "\n\n🧠 Suggestion\n" + str(advice_line)
			await update.message.reply_text(base)
			return

		base: None | str = format_signal(sig_dict)
		if base is None:
			base = format_signal_free_limited(sig_dict)
		if staleness_warning:
			base = f"{staleness_warning}\n\n{base}"
		if position_lines or advice_line:
			base += "\n\n📍 Position (best-effort)\n" + "\n".join(position_lines)
			if advice_line:
				base += "\n\n🧠 Suggestion\n" + str(advice_line)
		await update.message.reply_text(base)
		return
	except Exception as e:
		import logging
		logging.getLogger(__name__).error(f"signal_command failed: {e}", exc_info=True)
		await update.message.reply_text(
			"No matching signal found for that reference. Use /signals to list recent references."
		)
		return


async def outcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	# Simplified, robust implementation to avoid indentation/syntax errors
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return

	user_id: int = update.effective_user.id
	arg: str = (context.args[0] if context.args else "").strip()
	if not arg:
		await update.message.reply_text("Usage: /outcome <reference>")
		return

	try:
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is None:
			raise RuntimeError("Postgres not configured")
		from db.pg_features import get_delivered_signal_by_ref, get_outcome_for_signal, get_or_create_user
		from db.models import Signal, User, Outcome
		from sqlalchemy import select
		import json
		import os

		async with get_session() as session:
			# Ensure user exists
			user: User = await get_or_create_user(session, telegram_user_id=int(user_id))

			# Look up delivered signal for this user
			sig: Signal | None = await get_delivered_signal_by_ref(session, telegram_user_id=int(user_id), ref=str(arg))

			if sig is None:
				# Try to find the signal globally by reference
				ref = arg
				query = select(Signal)
				if len(ref) >= 32:
					query = query.where(Signal.signal_id == ref)
				else:
					query = query.where(Signal.signal_id.like(f"{ref}%"))
				query = query.order_by(Signal.created_at.desc()).limit(1)
				res = await session.execute(query)
				undelivered_sig: Signal | None = res.scalars().first()
				if undelivered_sig is not None:
					await update.message.reply_text("⚠️ This is not your signal. You were not sent this trade.")
					return
				else:
					await update.message.reply_text("Signal not found.")
					return

			# Check outcome
			oc: Outcome | None = await get_outcome_for_signal(session, str(sig.signal_id))

		# Format and reply outside session where possible
		if oc is not None:
			status = str(getattr(oc, "status", "") or "").lower()
			r = getattr(oc, "r_multiple", None)
			pct = getattr(oc, "percent", None)
			label = "PROFIT ✅" if status.startswith("tp") else ("LOSS ❌" if status == "sl" else status.upper())
			lines = [
				"📣 Outcome",
				"",
				f"Reference: {sig.signal_id[:8]}",
				f"{sig.asset} {sig.timeframe} {sig.direction.upper()}",
				f"Entry: {sig.entry}",
				f"Result: {label} ({status})",
			]
			ml_prob = getattr(sig, "ml_probability", None)
			if ml_prob is not None:
				try:
					ml_pct = round(float(ml_prob) * 100, 1)
					lines.append(f"ML Score: {ml_pct}%")
				except Exception:
					pass
			if r is not None:
				try:
					lines.append(f"R-multiple: {float(r):.2f}R")
				except Exception:
					pass
			if pct is not None:
				try:
					lines.append(f"Move: {float(pct):.2f}%")
				except Exception:
					pass

			await update.message.reply_text("\n".join(lines))
			return

		# No outcome yet — show basic in-progress details
		lines = ["🔄 Signal In Progress", "", f"Reference: {sig.signal_id}"]
		lines.extend([
			f"Asset: {sig.asset}",
			f"Timeframe: {sig.timeframe}",
			f"Direction: {sig.direction.upper()}",
		])
		if getattr(sig, "entry", None) is not None:
			lines.append(f"Entry: {sig.entry}")
		if getattr(sig, "stop_loss", None) is not None:
			lines.append(f"Stop Loss: {sig.stop_loss}")
		try:
			tp_raw = getattr(sig, "take_profit", None)
			if isinstance(tp_raw, str):
				try:
					tp_data = json.loads(tp_raw)
					if isinstance(tp_data, list) and tp_data:
						for i, tp in enumerate(tp_data, 1):
							lines.append(f"Take Profit {i}: {tp}")
					else:
						lines.append(f"Take Profit: {tp_raw}")
				except Exception:
					lines.append(f"Take Profit: {tp_raw}")
			elif tp_raw is not None:
				lines.append(f"Take Profit: {tp_raw}")
		except Exception:
			pass

		await update.message.reply_text("\n".join(lines))
		return
	except Exception as e:
		import logging
		logging.getLogger(__name__).exception("outcome_command failed")
		await update.message.reply_text(
			"No outcome found for that reference yet. Use /signal <ref> for live details."
		)
		return
async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	code = None
	progress = None
	try:
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
			from db.pg_features import get_or_create_referral_code, get_referral_progress
			async with get_session() as session:
				code: str = await get_or_create_referral_code(session, referrer_telegram_user_id=int(user_id))
				progress = await get_referral_progress(session, referrer_telegram_user_id=int(user_id))
				await session.commit()
		else:
			raise RuntimeError("DATABASE_URL not configured. Postgres is required.")
	except Exception:
		progress = None
		try:
			import hashlib
			import base64
			digest = hashlib.sha1(str(user_id).encode("utf-8")).digest()
			code = base64.b32encode(digest).decode("utf-8").lower().strip("=")[:8]
		except Exception:
			code = str(user_id)

	bot_username = None
	try:
		me: User = await context.bot.get_me()
		bot_username: os.Any | None = getattr(me, "username", None)
	except Exception:
		bot_username: str | None = os.getenv("BOT_USERNAME")
	progress_line: str = ""
	if progress:
		need = int(progress.get("needed_for_next", 0) or 0)
		toward = int(progress.get("toward_next", 0) or 0)
		total = int(progress.get("total", 0) or 0)
		# If you're exactly on a multiple of 3, you already earned the previous reward;
		# the next reward needs 3 more invites.
		if toward == 0:
			progress_line: str = f"\n\nProgress: 0/3 (invite 3 more people to earn +7 days Premium). Total invites: {total}."
		else:
			progress_line: str = f"\n\nProgress: {toward}/3 (invite {need} more to earn +7 days Premium). Total invites: {total}."

	if bot_username and code:
		link: str = f"https://t.me/{bot_username}?start=ref_{code}"
		await update.message.reply_text(
			f"🎁 Invite link:\n{link}\n\n"
			"Reward: invite 3 new users → get +7 days Premium."
			f"{progress_line}"
		)
		return

	await update.message.reply_text(
		f"🎁 Your invite code: {code}\n\n"
		"Reward: invite 3 new users → get +7 days Premium.\n"
		"Invite link not available (bot username not resolved)."
		f"{progress_line}"
	)

async def pricing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if await _public_guard(update):
		return
	msg = (
		"💰 SignalRankAI Plans\n\n"
		"🆓 Free Plan\n"
		"• 2 signals per day\n"
		"• Entry price shown\n"
		"• SL/TP locked\n\n"
		"⭐ Premium\n"
		"• ₦8,000/week | ₦24,000/month | ₦56,000/quarter\n"
		"• Up to 20 signals per day\n"
		"• Full signals with Entry, SL, TP\n"
		"• Performance analytics & history\n"
		"• Custom filters & alerts\n\n"
		"👑 VIP\n"
		"• ₦16,000/week | ₦40,000/month\n"
		"• Unlimited signals\n"
		"• Everything in Premium\n"
		"• ML probability scores\n"
		"• Entry zones & partial TPs\n"
		"• Elite signals (score 85+)\n\n"
		"📱 Weekly Plan — ₦4,000/week (full access)\n\n"
		"Use /upgrade to subscribe."
	)
	if update.message is not None:
		await update.message.reply_text(msg)


@require_tier("PREMIUM")
async def analyze_command(update, context) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	args = context.args or []
	if not args:
		await update.message.reply_text("Usage: /analyze <ASSET> [TIMEFRAME]\nExample: /analyze BTCUSDT 1h")
		return

	asset = str(args[0]).upper().strip()
	tf = str(args[1]).strip() if len(args) > 1 else "1h"

	try:
		market_state = await get_market_state_async(asset, [tf], include_ml=True)
		tf_data = (market_state.get("timeframes") or {}).get(tf)
		if not tf_data:
			await update.message.reply_text("No market data available for that pair/timeframe.")
			return

		candles = tf_data.get("candles", [])
		indicators = tf_data.get("indicators", {})
		if len(candles) < 50:
			await update.message.reply_text("Not enough data to analyze this pair yet.")
			return

		gen = SignalGenerator()
		signals = gen.generate_signals(asset, tf, {"candles": candles, "indicators": indicators, "ml_probability": tf_data.get("ml_score")})
		if not signals:
			await update.message.reply_text("No high-confidence setup found right now.")
			return

		best = sorted(signals, key=lambda s: s.score, reverse=True)[0]

		# News sentiment + AI adjustments
		sentiment = get_news_sentiment(asset)
		alignment = 1 if (sentiment > 0 and best.direction == "long") or (sentiment < 0 and best.direction == "short") else -1 if sentiment != 0 else 0
		adj_scale = max(min(abs(sentiment), 3.0), 0.0) / 3.0
		score_adj = (adj_scale * 8.0) * (1 if alignment == 1 else -1 if alignment == -1 else 0)
		adjusted_score = max(min(best.score + score_adj, 99.0), 50.0)
		adjusted_conf = max(min(best.confidence + (adj_scale * 0.08 * alignment), 0.95), 0.25)

		# Volatility-aware AI recalibration using ATR + news alignment
		atr = indicators.get("atr")
		rsi = indicators.get("rsi")
		adx = indicators.get("adx")
		macd = indicators.get("macd", {}) or {}
		macd_hist = macd.get("hist") if isinstance(macd, dict) else None
		ema_fast = indicators.get("ema_fast")
		ema_slow = indicators.get("ema_slow")

		atr_mult = 1.3 if alignment == 1 else 1.8 if alignment == -1 else 1.5
		if not atr:
			atr = abs(best.entry - best.stop_loss) or (best.entry * 0.01)

		if best.direction == "long":
			ai_sl = round(best.entry - (atr * atr_mult), 6)
			ai_tps = [
				round(best.entry + (atr * 2.5), 6),
				round(best.entry + (atr * 4.0), 6),
				round(best.entry + (atr * 6.0), 6),
			]
		else:
			ai_sl = round(best.entry + (atr * atr_mult), 6)
			ai_tps = [
				round(best.entry - (atr * 2.5), 6),
				round(best.entry - (atr * 4.0), 6),
				round(best.entry - (atr * 6.0), 6),
			]

		headlines = fetch_news_headlines(asset)[:3]
		news_lines = []
		if headlines:
			for title, published_at, score in headlines:
				news_lines.append(f"• {title} ({score:+d})")

		sentiment_label = "Positive" if sentiment > 0 else "Negative" if sentiment < 0 else "Neutral"

		trend_label = "Bullish" if (ema_fast and ema_slow and ema_fast > ema_slow) else "Bearish" if (ema_fast and ema_slow and ema_fast < ema_slow) else "Neutral"

		msg_lines = [
			f"🧠 AI Market Analysis ({asset} {tf})",
			f"Direction: {best.direction.upper()}",
			f"Entry: {best.entry}",
			f"Stop Loss: {best.stop_loss} → AI {ai_sl}",
		]
		msg_lines.append("Take Profits (AI):")
		for i, tp_price in enumerate(ai_tps, 1):
			msg_lines.append(f"  TP{i}: {tp_price}")
		msg_lines += [
			f"Strategy: {best.strategy_name} ({best.strategy_group})",
			f"Score: {best.score:.1f} → AI-adjusted {adjusted_score:.1f}",
			f"Confidence: {best.confidence:.2f} → AI-adjusted {adjusted_conf:.2f}",
			f"News Sentiment: {sentiment_label} ({sentiment:.2f})",
			f"Trend: {trend_label} | RSI: {rsi:.1f}" if isinstance(rsi, (int, float)) else f"Trend: {trend_label}",
			f"ADX: {adx:.1f}" if isinstance(adx, (int, float)) else "ADX: n/a",
			f"MACD hist: {macd_hist:.3f}" if isinstance(macd_hist, (int, float)) else "MACD hist: n/a",
		]
		# Compact risk plan (position sizing + max risk %)
		sl_distance = abs(best.entry - ai_sl) if isinstance(ai_sl, (int, float)) else abs(best.entry - best.stop_loss)
		risk_pct = 1.0
		msg_lines += [
			"",
			"Risk Plan (compact):",
			f"• Max risk: {risk_pct:.1f}% of account",
			f"• Position size: (Account × {risk_pct/100:.2f}) ÷ {sl_distance:.6f}",
		]
		if news_lines:
			msg_lines.append("Top Headlines:")
			msg_lines += news_lines
		msg_lines.append("\n⚠️ Educational only. Not financial advice.")
		await update.message.reply_text("\n".join(msg_lines))
		return
	except Exception as e:
		await update.message.reply_text(f"Analysis failed: {e}")


async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id

	import os as _os
	from paystack.paystack import generate_paystack_link
	from telegram import InlineKeyboardMarkup, InlineKeyboardButton

	# ── VIP seat capacity check ───────────────────────────────────────────────
	vip_seats_total = int(_os.getenv("VIP_SEAT_LIMIT", "15"))
	vip_used = 0
	vip_full = False
	try:
		from db.session import get_engine_for_event_loop, get_session as _gs_upg
		if get_engine_for_event_loop() is not None:
			from db.repository import count_active_vip_users
			async with _gs_upg() as _s:
				vip_used = await count_active_vip_users(_s)
			vip_full = vip_used >= vip_seats_total
	except Exception:
		pass
	vip_seats_left = max(0, vip_seats_total - vip_used)

	# ── Build message ─────────────────────────────────────────────────────────
	if vip_full:
		vip_line = f"💎 *VIP Monthly* — ₦40,000 | 🔴 FULL ({vip_seats_total}/{vip_seats_total} seats)"
	else:
		vip_line = (
			f"💎 *VIP Monthly* — ₦40,000 | 🟢 {vip_seats_left} seat"
			+ ("s" if vip_seats_left != 1 else "") + " left"
		)

	msg = (
		"🚀 *SignalRankAI — Choose Your Plan*\n\n"
		+ vip_line + "\n"
		"⭐ *Premium* — ₦8,000/wk · ₦24,000/mo · ₦56,000/qtr\n"
		"📅 *Weekly Plan* — ₦4,000/wk\n\n"
		"_Tap a plan below to subscribe instantly via Paystack:_"
	)

	# ── Build keyboard ────────────────────────────────────────────────────────
	plans = [
		("💎 VIP Monthly — ₦40,000", 40000, "VIP", "MONTHLY", 30),
		("⭐ Premium Monthly — ₦24,000", 24000, "PREMIUM", "MONTHLY", 30),
		("⭐ Premium Quarterly — ₦56,000", 56000, "PREMIUM", "QUARTERLY", 90),
		("⭐ Premium Weekly — ₦8,000", 8000, "PREMIUM", "WEEKLY", 7),
		("📅 Weekly Plan — ₦4,000", 4000, "WEEKLY_PLAN", "WEEKLY", 7),
	]

	keyboard_rows = []
	for name, price, tier, duration, days in plans:
		if tier == "VIP" and vip_full:
			keyboard_rows.append([
				InlineKeyboardButton("💎 VIP — FULL  |  📋 Join Waitlist", callback_data="vip_waitlist_join")
			])
			continue
		try:
			link = generate_paystack_link(
				user_id=user_id,
				price=price,
				tier=tier,
				duration=duration,
				duration_days=days,
			)
			if link and link.startswith("http"):
				keyboard_rows.append([InlineKeyboardButton(name, url=link)])
		except Exception:
			pass

	keyboard_rows.append([InlineKeyboardButton("📞 Support: @theocrilox", url="https://t.me/theocrilox")])
	keyboard = InlineKeyboardMarkup(keyboard_rows)

	await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)


# ── Inline-button callbacks for /upgrade VIP waitlist ─────────────────────
async def vip_waitlist_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Handle 'Join Waitlist' button pressed from /upgrade when VIP is full."""
	query = update.callback_query
	await query.answer()
	user_id = update.effective_user.id if update.effective_user else None
	if not user_id:
		return
	try:
		from db.session import get_engine_for_event_loop, get_session as _gs_wl
		from db.models import VIPWaitlist, User
		from sqlalchemy import select as _sel
		engine = get_engine_for_event_loop()
		if engine is not None:
			async with _gs_wl() as session:
				u_res = await session.execute(_sel(User).where(User.telegram_user_id == int(user_id)))
				u = u_res.scalar_one_or_none()
				if u is not None:
					exists = (await session.execute(
						_sel(VIPWaitlist).where(VIPWaitlist.user_id == u.id)
					)).scalar_one_or_none()
					if exists is None:
						from datetime import datetime as _dt
						session.add(VIPWaitlist(user_id=u.id, joined_at=_dt.utcnow()))
						await session.commit()
						await query.edit_message_text(
							"✅ You've been added to the VIP waitlist!\n\n"
							"We'll DM you within 24 hours when a seat opens. "
							"You'll get a personal payment link to complete your upgrade.",
						)
						return
					else:
						await query.answer("You're already on the waitlist. We'll notify you when a seat opens! 🕐", show_alert=True)
						return
	except Exception:
		pass
	await query.answer("Could not add to waitlist. Please contact @theocrilox.", show_alert=True)


# ── Terms gate callbacks (/start disclaimer) ───────────────────────────────
async def agree_terms_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""User clicked [✅ I Agree] on the financial disclaimer."""
	query = update.callback_query
	await query.answer("Terms accepted ✅")
	user_id = update.effective_user.id if update.effective_user else None
	if not user_id:
		return
	try:
		from db.session import get_session as _gs_terms
		from db.models import User
		from sqlalchemy import update as _sa_upd
		async with _gs_terms() as session:
			await session.execute(
				_sa_upd(User)
				.where(User.telegram_user_id == int(user_id))
				.values(accepted_terms=True)
			)
			await session.commit()
	except Exception:
		pass
	welcome = (
		"✅ *Welcome to SignalRankAI!*\n\n"
		"You're all set. Here's what you get:\n"
		"• Risk-managed signals filtered for high-probability setups\n"
		"• Outcome tracking — no hype, no guarantees\n"
		"• Real-time market coverage: Crypto, Forex, Stocks, Commodities\n\n"
		"Use /pricing to see plans, or /upgrade to subscribe.\n"
		"Use /signals to see the latest setups."
	)
	try:
		await query.edit_message_text(welcome, parse_mode="Markdown")
	except Exception:
		try:
			if update.effective_chat:
				await context.bot.send_message(
					chat_id=update.effective_chat.id, text=welcome, parse_mode="Markdown"
				)
		except Exception:
			pass


async def decline_terms_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""User clicked [❌ Decline] on the financial disclaimer."""
	query = update.callback_query
	await query.answer()
	try:
		await query.edit_message_text(
			"No problem. You can return anytime by sending /start.\n\n"
			"Remember: SignalRankAI provides educational trade ideas only — "
			"never financial advice."
		)
	except Exception:
		pass


# ── Admin dashboard ────────────────────────────────────────────────────────
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""OWNER/ADMIN only — show real-time platform dashboard."""
	if update.effective_user is None or update.message is None:
		return
	tier = _effective_tier(update.effective_user.id)
	if tier_rank(tier) < tier_rank("ADMIN"):
		await update.message.reply_text("⛔ Access Denied.")
		return

	import os as _os_adm
	from datetime import datetime as _dt_adm

	try:
		from db.session import get_engine_for_event_loop, get_session as _gs_adm
		from sqlalchemy import select as _sel_adm, func as _func_adm
		from db.models import User as _User_adm, Signal as _Sig_adm, Subscription as _Sub_adm

		engine = get_engine_for_event_loop()
		if engine is None:
			await update.message.reply_text("Database not available.")
			return

		now = _dt_adm.utcnow()
		today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

		async with _gs_adm() as session:
			total_users = (await session.execute(
				_sel_adm(_func_adm.count(_User_adm.id))
			)).scalar() or 0

			from db.repository import count_active_vip_users as _cvip
			vip_active = await _cvip(session)

			premium_active = (await session.execute(
				_sel_adm(_func_adm.count(_Sub_adm.id)).where(
					_Sub_adm.tier == "premium",
					_Sub_adm.status == "active",
				)
			)).scalar() or 0

			signals_today = (await session.execute(
				_sel_adm(_func_adm.count(_Sig_adm.signal_id)).where(
					_Sig_adm.created_at >= today_start
				)
			)).scalar() or 0

			total_signals = (await session.execute(
				_sel_adm(_func_adm.count(_Sig_adm.signal_id))
			)).scalar() or 0

			# Free-tier users = total minus any active subscription
			free_users = total_users - premium_active - vip_active

		vip_limit = int(_os_adm.getenv("VIP_SEAT_LIMIT", "15"))
		msg = (
			"🛡️ *Admin Dashboard*\n\n"
			f"👥 Total Users: `{total_users:,}`\n"
			f"💎 VIP Active: `{vip_active}` / `{vip_limit}`\n"
			f"⭐ Premium Active: `{premium_active}`\n"
			f"🆓 Free Tier: `{max(0, free_users):,}`\n\n"
			f"📡 Signals Today: `{signals_today}`\n"
			f"📊 Total Signals (all-time): `{total_signals:,}`\n\n"
			f"🕐 UTC: `{now.strftime('%Y-%m-%d %H:%M')}`"
		)
		await update.message.reply_text(msg, parse_mode="Markdown")

	except Exception as e:
		logger.error(f"[admin] admin_command failed: {e}")
		await update.message.reply_text(f"Admin query failed: {e}")


# ── Admin broadcast ────────────────────────────────────────────────────────
async def admin_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""OWNER/ADMIN only — DM all registered users with a message.

	Usage: /admin_broadcast <message text>
	"""
	if update.effective_user is None or update.message is None:
		return
	tier = _effective_tier(update.effective_user.id)
	if tier_rank(tier) < tier_rank("ADMIN"):
		await update.message.reply_text("⛔ Access Denied.")
		return

	msg_text = " ".join(context.args or []).strip()
	if not msg_text:
		await update.message.reply_text(
			"Usage: /admin_broadcast <message>\n\n"
			"Example:\n/admin_broadcast New premium signals just dropped! 🔥"
		)
		return

	try:
		from db.session import get_engine_for_event_loop, get_session as _gs_bc
		from sqlalchemy import select as _sel_bc
		from db.models import User as _User_bc

		engine = get_engine_for_event_loop()
		if engine is None:
			await update.message.reply_text("Database not available.")
			return

		async with _gs_bc() as session:
			result = await session.execute(_sel_bc(_User_bc.telegram_user_id))
			user_ids = [row[0] for row in result.fetchall()]

		broadcast_text = f"📢 *SignalRankAI*\n\n{msg_text}"
		sent = 0
		failed = 0
		for uid in user_ids:
			try:
				await context.bot.send_message(
					chat_id=int(uid),
					text=broadcast_text,
					parse_mode="Markdown",
				)
				sent += 1
			except Exception:
				failed += 1

		await update.message.reply_text(
			f"✅ Broadcast complete.\n\nSent: {sent} | Failed: {failed}"
		)

	except Exception as e:
		logger.error(f"[admin] admin_broadcast_command failed: {e}")
		await update.message.reply_text(f"Broadcast failed: {e}")


# ── Terms blast (send disclaimer to all users without accepted_terms) ──────
async def blast_terms_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""OWNER/ADMIN — send the financial disclaimer gate to every user who hasn't
	accepted terms yet, PLUS the caller so they can verify the UI.
	Safe to run multiple times; idempotent per user."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("⛔ Access Denied.")
		return

	try:
		from db.session import get_engine_for_event_loop, get_session as _gs_bt
		from db.models import User as _User_bt
		from sqlalchemy import select as _sel_bt

		engine = get_engine_for_event_loop()
		if engine is None:
			await update.message.reply_text("⚠️ Database connection error. Please try again later.")
			return

		async with _gs_bt() as session:
			result = await session.execute(
				_sel_bt(_User_bt.telegram_user_id).where(_User_bt.accepted_terms == False)  # noqa: E712
			)
			pending_ids = [row[0] for row in result.fetchall()]

		# Always include the caller so they can verify the UI looks correct
		caller_id = int(update.effective_user.id)
		if caller_id not in pending_ids:
			pending_ids.insert(0, caller_id)

		await update.message.reply_text(
			f"📢 Sending terms gate to {len(pending_ids)} user(s)\u2026"
		)

		from telegram import InlineKeyboardMarkup as _IKM_bt, InlineKeyboardButton as _IKB_bt
		disclaimer = (
			"⚠️ *SignalRankAI — Financial Disclaimer*\n\n"
			"Please read and confirm to continue:\n\n"
			"• All signals are for *educational purposes only*\n"
			"• Nothing here constitutes financial advice or a trade recommendation\n"
			"• Trading involves significant risk — losses can exceed your deposit\n"
			"• Past performance does not guarantee future results\n"
			"• You are solely responsible for your trading decisions\n\n"
			"Tap *✅ I Agree* to acknowledge these terms and continue."
		)
		_kbd_bt = _IKM_bt([[
			_IKB_bt("✅ I Agree", callback_data="agree_terms"),
			_IKB_bt("❌ Decline", callback_data="decline_terms"),
		]])

		sent = 0
		failed = 0
		for uid in pending_ids:
			try:
				await context.bot.send_message(
					chat_id=int(uid),
					text=disclaimer,
					parse_mode="Markdown",
					reply_markup=_kbd_bt,
				)
				sent += 1
			except Exception:
				failed += 1

		await update.message.reply_text(
			f"✅ Terms blast complete.\n\nSent: {sent} | Failed: {failed}"
		)

	except Exception as e:
		logger.error(f"[blast_terms] failed: {e}")
		await update.message.reply_text(f"⚠️ Blast failed: {e}")

	try:
		from db.session import get_engine_for_event_loop, get_session as _gs_bt
		from db.models import User as _User_bt
		from sqlalchemy import select as _sel_bt

		engine = get_engine_for_event_loop()
		if engine is None:
			await update.message.reply_text("Database not available.")
			return

		async with _gs_bt() as session:
			result = await session.execute(
				_sel_bt(_User_bt.telegram_user_id).where(_User_bt.accepted_terms == False)  # noqa: E712
			)
			pending_ids = [row[0] for row in result.fetchall()]

		if not pending_ids:
			await update.message.reply_text("✅ All users have already accepted the terms.")
			return

		await update.message.reply_text(
			f"📢 Sending terms gate to {len(pending_ids)} user(s)…"
		)

		from telegram import InlineKeyboardMarkup as _IKM_bt, InlineKeyboardButton as _IKB_bt
		disclaimer = (
			"⚠️ *SignalRankAI — Financial Disclaimer*\n\n"
			"We've updated our terms. Please read and confirm to continue:\n\n"
			"• All signals are for *educational purposes only*\n"
			"• Nothing here constitutes financial advice or a trade recommendation\n"
			"• Trading involves significant risk — losses can exceed your deposit\n"
			"• Past performance does not guarantee future results\n"
			"• You are solely responsible for your trading decisions\n\n"
			"Tap *✅ I Agree* to acknowledge and continue using the bot."
		)
		_kbd_bt = _IKM_bt([[
			_IKB_bt("✅ I Agree", callback_data="agree_terms"),
			_IKB_bt("❌ Decline", callback_data="decline_terms"),
		]])

		sent = 0
		failed = 0
		for uid in pending_ids:
			try:
				await context.bot.send_message(
					chat_id=int(uid),
					text=disclaimer,
					parse_mode="Markdown",
					reply_markup=_kbd_bt,
				)
				sent += 1
			except Exception:
				failed += 1

		await update.message.reply_text(
			f"✅ Terms blast complete.\n\nSent: {sent} | Failed: {failed}"
		)

	except Exception as e:
		logger.error(f"[blast_terms] failed: {e}")
		await update.message.reply_text(f"Blast failed: {e}")


# /policy or /refunds command
async def policy_command(update, context) -> None:
	if await _public_guard(update):
		return
	msg = (
		"📄 Subscription & Refund Policy\n\n"
		"• Payments are non-refundable.\n"
		"• Auto-renew only applies if you explicitly agree and link your card.\n"
		"• If you do not link a card, your plan expires at the end of the purchased period.\n"
		"• If technical issues prevent delivery, subscription time may be extended.\n\n"
		"Subscriptions activate after successful verification.\n\n"
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
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
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
			most_active: str = ", ".join(list((stats or {}).get("top_assets") or [])[:2]) or "N/A"
			best_strategy: str = ", ".join(list((stats or {}).get("top_strategies") or [])[:1]) or "N/A"
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
	total_signals: int = len(trades)
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
	most_active: str = ', '.join([a for a, _ in Counter(assets).most_common(2)]) if assets else 'N/A'
	best_strategy = Counter(strategies).most_common(1)[0][0] if strategies else 'N/A'
	await update.message.reply_text(
		"\U0001F4CA SignalRankAI Weekly Recap\n\n"
		"Here’s a quick overview of your past week:\n\n"
		f"• Total signals sent: {total_signals}\n"
		f"• Markets most active: {most_active}\n"
		f"• Best-performing strategy: {best_strategy}"
	)

from core.performance import strategy_stats


# /start or welcome message

async def start_command(update, context):
	# ── Diagnostic entry log — visible in Railway logs ───────────────────────
	try:
		logger.info(
			"[/start] handler invoked user_id=%s username=%s chat_id=%s",
			getattr(getattr(update, 'effective_user', None), 'id', 'unknown'),
			getattr(getattr(update, 'effective_user', None), 'username', 'unknown'),
			getattr(getattr(update, 'effective_chat', None), 'id', 'unknown'),
		)
	except Exception:
		pass
	if update.effective_user is None or update.message is None:
		logger.warning("[/start] update missing effective_user or message — ignoring")
		return
	user_id = update.effective_user.id
	logger.info("[/start] processing user_id=%s — checking rate limit", user_id)
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
	upgrade_notice = None
	logger.info("[/start] user_id=%s — opening DB session", user_id)
	try:
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
			from db.models import User
			from sqlalchemy import select
			from db.repository import get_or_create_user
			from db.pg_features import record_bot_event
			from db.pg_features import ensure_alert_prefs
			from signalrank_telegram.access import resolve_user_tier
			async with get_session() as session:
				logger.info("[/start] user_id=%s — DB session open, querying user row", user_id)
				res: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(user_id)))
				existing: User | None = res.scalar_one_or_none()
				is_new: bool = existing is None
				user_row = await get_or_create_user(session, telegram_user_id=user_id, username=username)
				effective_tier = str(resolve_user_tier(int(user_id))).upper()
				if effective_tier in {"OWNER", "ADMIN"}:
					current = str(getattr(user_row, "tier", "") or "").lower()
					if current not in {"owner", "admin"}:
						try:
							user_row.tier = "owner" if effective_tier == "OWNER" else "admin"
							upgrade_notice = (
								"✅ Owner access granted via configuration. Use /help to see owner commands."
								if effective_tier == "OWNER"
								else "✅ Admin access granted. Use /help to see admin commands."
							)
						except Exception:
							pass
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
						code: str = code[4:]
					code: str | None = (code or "").strip() or None
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

				# Read accepted_terms before session closes (object becomes detached after commit)
				terms_accepted: bool = bool(getattr(user_row, "accepted_terms", False))

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
				"Database not connected. Please contact support if this persists."
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

	if upgrade_notice and update.message is not None:
		await update.message.reply_text(upgrade_notice)

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

	# ── Terms gate: new / unaccepted users must agree to disclaimer first ─────
	if not terms_accepted:
		from telegram import InlineKeyboardMarkup as _IKM, InlineKeyboardButton as _IKB
		disclaimer = (
			"⚠️ *Financial Disclaimer*\n\n"
			"Before you continue, please read and accept:\n\n"
			"• All signals are for *educational purposes only*\n"
			"• Nothing here constitutes financial advice or a trade recommendation\n"
			"• Trading involves significant risk — losses can exceed your deposit\n"
			"• Past performance does not guarantee future results\n"
			"• You are solely responsible for your trading decisions\n\n"
			"Tap *✅ I Agree* to acknowledge these terms and continue."
		)
		_kbd = _IKM([[
			_IKB("✅ I Agree", callback_data="agree_terms"),
			_IKB("❌ Decline", callback_data="decline_terms"),
		]])
		await update.message.reply_text(disclaimer, parse_mode="Markdown", reply_markup=_kbd)
		return  # Hold back welcome message until terms are accepted

	# Terms already accepted — send normal welcome
	await update.message.reply_text(msg)

# /about message
async def about_command(update, context) -> None:
	msg = (
		"\U0001F4CA About SignalRankAI\n\n"
		"SignalRankAI is a rule-based trading signal platform designed to deliver high-quality, risk-aware trade ideas.\n\n"
		"The system:\n"
		"• Uses multiple market strategies\n"
		"• Applies ML-assisted quality filters\n"
		"• Filters out weak or risky setups\n"
		"• Ranks signals by quality\n"
		"• Limits signal frequency to avoid noise\n\n"
		"Markets:\n"
		"• Crypto (BTC, ETH, SOL, and more)\n"
		"• Forex (EUR/USD, GBP/USD, USD/JPY, and more)\n"
		"• Stocks (AAPL, TSLA, MSFT, and more)\n"
		"• Commodities (Gold, Silver, Oil, Natural Gas)\n\n"
		"SignalRankAI does not execute trades and does not guarantee profits.\n"
		"All signals are for educational and informational purposes only.\n\n"
		"Trade responsibly.\n\n"
		"Support: @theocrilox"
	)
	if update.message is not None:
		await update.message.reply_text(msg)

# /faq message
async def faq_command(update, context) -> None:
	msg = (
		"\u2754 Frequently Asked Questions\n\n"
		"1) Does SignalRankAI place trades for me?\n"
		"No. SignalRankAI only provides trade signals. You decide if and how you trade.\n\n"
		"2) Are profits guaranteed?\n"
		"No. Trading always involves risk. No system can guarantee profits.\n\n"
		"3) How often are signals sent?\n"
		"Only when high-quality setups appear. Some days may have fewer or no signals.\n\n"
		"4) What markets are covered?\n"
		"Crypto (BTC, ETH, SOL), Forex (EUR/USD, GBP/USD, USD/JPY), Stocks (AAPL, TSLA, MSFT), and Commodities (Gold, Silver, Oil, Natural Gas).\n\n"
		"5) What’s the difference between Free, Premium, and VIP?\n"
		"Free: 2 signals/day with limited details.\n"
		"Premium: 20 signals/day with full Entry, SL, TP, and analytics.\n"
		"VIP: Unlimited signals with ML probability scores and elite signals.\n\n"
		"Yes. Subscriptions expire automatically. Auto-renew only applies if you opt in and link a card.\n\n"
		"7) Is this financial advice?\n"
		"No. Signals are for informational purposes only."
	)
	if update.message is not None:
		await update.message.reply_text(msg)

# /disclaimer message
async def disclaimer_command(update, context) -> None:
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


@require_tier("PREMIUM")
async def performance_command(update, context):
	if await _public_guard(update):
		return
	from datetime import datetime, timedelta
	user_id = update.effective_user.id
	tier: str = _effective_tier(user_id)

	# Prefer Postgres (deliveries + outcomes)
	try:
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
			from db.pg_features import get_user_performance_30d

			# Fetch performance stats
			stats = {}
			try:
				async with get_session() as session:
					stats = await get_user_performance_30d(session, int(user_id))
			except Exception as e:
				_audit_logger.error(f"/performance db fetch failed for user={user_id}: {e}")

			total = int((stats or {}).get("total") or 0)
			wins = int((stats or {}).get("wins") or 0)
			losses = int((stats or {}).get("losses") or 0)
			win_rate = float((stats or {}).get("win_rate") or 0.0)
			avg_r = (stats or {}).get("avg_r")
			net_r = (stats or {}).get("net_r")
			tracked = int((stats or {}).get("tracked_outcomes") or 0)
			profit_loss = float((stats or {}).get("profit_loss_pct") or 0.0)

			if total <= 0:
				# Fallback diagnostic: if deliveries exist but outcomes are missing, show a hint
				deliveries_30d = 0
				try:
					from sqlalchemy import select, func
					from db.models import SignalDelivery, User
					cutoff: datetime = datetime.utcnow() - timedelta(days=30)
					
					async with get_session() as session:
						res_u: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(user_id)))
						u: User | None = res_u.scalar_one_or_none()
						if u is None:
							deliveries_30d = 0
						else:
							res_d: Result[Tuple[int]] = await session.execute(
								select(func.count(SignalDelivery.id)).where(
									SignalDelivery.user_id == u.id,
									SignalDelivery.delivered_at >= cutoff,
								)
							)
							deliveries_30d = int(res_d.scalar() or 0)
				except Exception as e:
					_audit_logger.error(f"/performance delivery count failed for user={user_id}: {e}")
					deliveries_30d = 0

				if deliveries_30d > 0:
					msg: str = (
						"📊 Performance (pending outcomes)\n\n"
						f"Signals delivered (30d): {deliveries_30d}\n"
						"Outcomes not yet tracked for these signals. They will appear once TP/SL is marked."
					)
				else:
					msg = "No signals in the last 30 days."
				
				if update.message is not None:
					await update.message.reply_text(msg)
				return

			if tier_rank(tier) < tier_rank("PREMIUM"):
				bucket: str = "strong" if win_rate >= 0.6 else ("cautious" if win_rate <= 0.4 else "mixed")
				msg: str = (
					"📊 Performance (limited)\n\n"
					f"Recent trend: {bucket}.\n"
					"Upgrade to Premium for full stats and history."
				)
				if update.message is not None:
					await update.message.reply_text(msg)
				return

			avg_r_str: str = f"{float(avg_r):.2f}R" if avg_r is not None else "N/A"
			net_r_str: str = f"{float(net_r):.2f}R" if net_r is not None else "N/A"
			profit_str: str = f"+{profit_loss:.2f}%" if profit_loss >= 0 else f"{profit_loss:.2f}%"
			profit_emoji: str = "✅" if profit_loss >= 0 else "⚠️"
			
			msg: str = (
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
	except Exception as e:
		_audit_logger.error(f"/performance failed for user={user_id}: {e}")
		if update.message is not None:
			await update.message.reply_text("No performance data available right now. Use /signals for recent activity.")
		return


# -------- Premium commands --------
@require_tier("PREMIUM")
async def stats_command(update, context) -> None:
	user_id = update.effective_user.id
	# Postgres-first
	try:
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
			from db.pg_features import get_weekly_recap_stats, list_signals_sent_today
			from sqlalchemy import select as _sel_s, func as _func_s
			from db.models import Outcome as _Out, Signal as _Sig_s, SignalDelivery as _Deliv, User as _U_s
			async with get_session() as session:
				week = await get_weekly_recap_stats(session, int(user_id))
				today_rows: list = await list_signals_sent_today(session, int(user_id))
				# Fetch outcomes for signals delivered to this user (via SignalDelivery join)
				try:
					_u_res = await session.execute(
						_sel_s(_U_s).where(_U_s.telegram_user_id == int(user_id))
					)
					_u = _u_res.scalar_one_or_none()
					if _u is not None:
						_outcome_rows = (
							await session.execute(
								_sel_s(_Out)
								.join(_Deliv, _Deliv.signal_id == _Out.signal_id)
								.where(_Deliv.user_id == _u.id)
								.order_by(_Out.closed_at.desc())
								.limit(100)
							)
						).scalars().all()
					else:
						_outcome_rows = []
				except Exception:
					_outcome_rows = []
				await session.commit()
			# Compute stats from outcome rows
			_wins = sum(1 for o in _outcome_rows if str(o.status).startswith("tp"))
			_losses = sum(1 for o in _outcome_rows if o.status == "sl")
			_tracked = len(_outcome_rows)
			_win_rate = (_wins / _tracked * 100) if _tracked > 0 else None
			_r_values = [o.r_multiple for o in _outcome_rows if o.r_multiple is not None]
			_net_r = sum(_r_values) if _r_values else None
			_avg_r = (sum(_r_values) / len(_r_values)) if _r_values else None
			total_week = int((week or {}).get("total") or 0)
			today: int = len(today_rows or [])
			lines = [
				"📈 *My Stats*",
				"",
				f"📡 Signals today: `{today}`",
				f"📊 Signals this week: `{total_week}`",
			]
			if _tracked > 0:
				lines += [
					"",
					f"✅ Wins: `{_wins}` | ❌ Losses: `{_losses}` | Total: `{_tracked}`",
					f"🎯 Win Rate: `{_win_rate:.1f}%`" if _win_rate is not None else "",
					f"📐 Net R: `{_net_r:+.2f}R`" if _net_r is not None else "",
					f"📏 Avg R/trade: `{_avg_r:+.2f}R`" if _avg_r is not None else "",
				]
			else:
				lines.append("\n_No tracked outcomes yet. Outcomes appear when TP/SL levels are hit._")
			lines.append("\nUse /history to view recent signals.")
			msg: str = "\n".join(l for l in lines if l is not None)
			if update.message is not None:
				await update.message.reply_text(msg, parse_mode="Markdown")
			return
	except Exception:
		pass
	
	if update.message is not None:
		await update.message.reply_text("Stats unavailable right now.")


@require_tier("PREMIUM")
async def history_command(update, context):
	user_id = update.effective_user.id
	asset = None
	tf = None
	if context.args:
		asset: str = str(context.args[0]).upper()
		if len(context.args) > 1:
			tf = str(context.args[1])

	# Postgres-first
	try:
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
			from db.pg_features import list_recent_signals_delivered
			async with get_session() as session:
				rows: list[Signal] = await list_recent_signals_delivered(
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
			lines: list[str] = ["🧾 History (last 10):", ""]
			for s in rows:
				lines.append(
					f"• {s.asset} {s.timeframe} {s.direction} ref={s.signal_id} entry={s.entry} sl={s.stop_loss} tp={s.take_profit}"
				)
			if update.message is not None:
				await update.message.reply_text("\n".join(lines))
			return
	except Exception:
		pass
	
	if update.message is not None:
		await update.message.reply_text("No history available yet.")


@require_tier("PREMIUM")
async def risk_command(update, context) -> None:
	if update.message is None:
		return
	await update.message.reply_text(
		"🛡️ Risk (recommended)\n\n"
		"Suggested risk: ~1% per trade.\n"
		"Keep position sizes consistent and avoid overtrading."
	)


@require_tier("PREMIUM")
async def alerts_command(update, context) -> None:
	if await _public_guard(update):
		return
	user_id = update.effective_user.id

	async def _get_prefs() -> dict:
		try:
			from db.session import get_engine_for_event_loop, get_session
			engine = get_engine_for_event_loop()
			if engine is not None:
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
		quiet: str = "off" if qs is None or qe is None else f"{qs}:00–{qe}:00"
		status: str = "on" if prefs.get("tp_sl_enabled", True) else "off"
		if update.message is not None:
			await update.message.reply_text(f"🔔 Alerts\n\nTP/SL alerts: {status}\nQuiet hours: {quiet}\n\nUsage: /alerts on|off or /alerts quiet <start_hour> <end_hour>")
		return

	cmd: str = str(context.args[0]).lower()
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
async def elite_command(update, context) -> None:
	if update.message is None or update.effective_user is None:
		return
	try:
		from db.session import get_engine_for_event_loop, get_session
		from sqlalchemy import select, desc
		from datetime import datetime, timedelta, timezone
		from db.models import Signal
		engine = get_engine_for_event_loop()
		if engine is None:
			await update.message.reply_text("No elite signals available right now.")
			return
		cutoff = datetime.now(timezone.utc) - timedelta(days=7)
		async with get_session() as session:
			res = await session.execute(
				select(Signal)
				.where(Signal.created_at >= cutoff)
				.order_by(desc(Signal.score))
				.limit(25)
			)
			rows = list(res.scalars().all())
			await session.commit()
		elite = [r for r in rows if float(getattr(r, "score", 0) or 0) >= 85.0]
		if not elite:
			await update.message.reply_text("No elite signals available right now.")
			return
		from .formatter import format_signal
		count = 0
		for r in elite:
			sig = {
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
				"ml_probability": r.ml_probability,
			}
			formatted = format_signal(sig, user_tier="VIP")
			if not formatted:
				continue
			await update.message.reply_text(formatted)
			count += 1
			if count >= 5:
				break
		if count == 0:
			await update.message.reply_text("No elite signals available right now.")
	except Exception:
		await update.message.reply_text("No elite signals available right now.")


@require_tier("VIP")
async def early_command(update, context) -> None:
	if update.message is not None:
		await update.message.reply_text("⚡ Early access is automatic for VIP. You’ll receive signals first when available.")


@require_tier("VIP")
async def report_command(update, context) -> None:
	# Structured text report (monthly)
	if update.message is None:
		return
	try:
		from db.session import get_engine_for_event_loop, get_session
		from db.pg_features import get_user_performance_30d
		engine = get_engine_for_event_loop()
		if engine is None:
			await update.message.reply_text("No report data available right now.")
			return
		user_id = int(update.effective_user.id) if update.effective_user else 0
		async with get_session() as session:
			stats = await get_user_performance_30d(session, int(user_id))
			await session.commit()
		total = int(stats.get("total", 0) or 0)
		if total <= 0:
			await update.message.reply_text("No signals delivered in the last 30 days.")
			return
		wins = int(stats.get("wins", 0) or 0)
		losses = int(stats.get("losses", 0) or 0)
		win_rate = float(stats.get("win_rate", 0.0) or 0.0) * 100
		net_r = stats.get("net_r", 0) or 0
		profit = float(stats.get("profit_loss_pct", 0.0) or 0.0)
		msg = (
			"🗓️ VIP Report (last 30 days)\n\n"
			f"Signals: {total}\n"
			f"Wins/Losses: {wins}/{losses}\n"
			f"Win rate: {win_rate:.1f}%\n"
			f"Net R: {float(net_r):.2f}R\n"
			f"Est. P/L: {profit:+.2f}%\n"
			"\nUse /performance for full breakdown."
		)
		await update.message.reply_text(msg)
	except Exception:
		await update.message.reply_text("No report data available right now.")


# ============================================================
# NEW COMMANDS: Live Price, Portfolio, Market
# ============================================================

async def liveprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show real-time price for any asset."""
	if update.effective_user is None or update.message is None:
		return
	
	# Get asset from arguments
	if not context.args:
		await update.message.reply_text(
			"Usage: /liveprice <asset>\n\n"
			"Examples:\n"
			"/liveprice BTCUSDT\n"
			"/liveprice EUR/USD\n"
			"/liveprice AAPL"
		)
		return
	
	asset = context.args[0].strip().upper()
	
	try:
		from engine.price_validator import get_current_price
		
		# Fetch current price
		current_price = get_current_price(asset)
		
		if current_price is None:
			await update.message.reply_text(
				f"❌ Could not fetch current price for {asset}.\n\n"
				f"Please check the asset symbol and try again."
			)
			return
		
		# Format price based on asset type
		if 'USDT' in asset or 'USDC' in asset or 'BUSD' in asset:
			price_str = f"${current_price:,.4f}"
			asset_type = "Crypto"
		elif '/' in asset:
			price_str = f"{current_price:.5f}"
			asset_type = "Forex"
		else:
			price_str = f"${current_price:,.2f}"
			asset_type = "Stock"
		
		# Get timestamp
		from datetime import datetime
		timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
		
		message = (
			f"💰 **Live Price**\n\n"
			f"Asset: {asset}\n"
			f"Type: {asset_type}\n"
			f"Price: **{price_str}**\n\n"
			f"📅 {timestamp}\n\n"
			f"💡 Use /signal to view active signals"
		)
		
		await update.message.reply_text(message)
	
	except Exception as e:
		await update.message.reply_text(f"Error fetching price: {str(e)}")


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show all active signals with current P&L for the user."""
	if update.effective_user is None or update.message is None:
		return
	
	user_id = update.effective_user.id
	
	try:
		from db.session import get_session
		from db.models import Signal, SignalDelivery
		from sqlalchemy import select
		from datetime import datetime, timedelta
		from engine.price_validator import get_current_price
		from engine.signal_calculations import calculate_profit_loss_pct
		
		# Get active signals for this user
		async with get_session() as session:
			# Get signals delivered to this user in last 48 hours
			cutoff = datetime.utcnow() - timedelta(hours=48)
			stmt = (
				select(Signal)
				.join(SignalDelivery, Signal.signal_id == SignalDelivery.signal_id)
				.where(
					SignalDelivery.user_id == user_id,
					Signal.archived == False,
					Signal.created_at >= cutoff
				)
				.distinct()
			)
			result = await session.execute(stmt)
			signals = result.scalars().all()
		
		if not signals:
			await update.message.reply_text(
				"📊 **Portfolio**\n\n"
				"You have no active signals.\n\n"
				"Use /signals to view available signals."
			)
			return
		
		# Build portfolio message
		message = f"📊 **Your Active Signals** ({len(signals)})\n\n"
		
		total_pnl = 0.0
		valid_signals = 0
		
		for sig in signals:
			try:
				asset = sig.asset
				direction = sig.direction.upper()
				entry = sig.entry
				ref = sig.signal_id[:8]
				
				# Get current price
				current_price = get_current_price(asset)
				
				if current_price is None:
					continue
				
				# Calculate P&L
				pnl_pct = calculate_profit_loss_pct(entry, current_price, direction)
				total_pnl += pnl_pct
				valid_signals += 1
				
				# Format
				pnl_sign = "+" if pnl_pct >= 0 else ""
				pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
				
				message += (
					f"{pnl_emoji} **{asset}** {direction}\n"
					f"   Entry: {entry:.4f} | Now: {current_price:.4f}\n"
					f"   P&L: {pnl_sign}{pnl_pct:.2f}% | Ref: `{ref}`\n\n"
				)
			
			except Exception as e:
				continue
		
		# Add summary
		if valid_signals > 0:
			avg_pnl = total_pnl / valid_signals
			avg_sign = "+" if avg_pnl >= 0 else ""
			summary_emoji = "📈" if avg_pnl >= 0 else "📉"
			
			message += (
				f"━━━━━━━━━━━━━━━━\n"
				f"{summary_emoji} **Average P&L:** {avg_sign}{avg_pnl:.2f}%\n\n"
				f"💡 Use /signal <ref> for details"
			)
		
		await update.message.reply_text(message)
	
	except Exception as e:
		await update.message.reply_text(f"Error fetching portfolio: {str(e)}")


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show overall market conditions."""
	if update.effective_user is None or update.message is None:
		return
	
	try:
		from engine.price_validator import get_current_price
		from data.news import get_news_sentiment
		
		# Define major assets to track
		major_assets = [
			('BTCUSDT', 'Bitcoin'),
			('ETHUSDT', 'Ethereum'),
			('EUR/USD', 'Euro/USD'),
			('XAUUSD', 'Gold')
		]
		
		message = "🌐 **Market Overview**\n\n"
		
		# Get prices and sentiment for each
		for asset, name in major_assets:
			try:
				price = get_current_price(asset)
				
				if price is None:
					continue
				
				# Format price
				if 'USDT' in asset or 'USD' in asset:
					price_str = f"${price:,.2f}" if price > 100 else f"${price:,.4f}"
				else:
					price_str = f"{price:.5f}"
				
				# Get news sentiment (simplified - just show if available)
				try:
					sentiment = get_news_sentiment(asset, lookback_minutes=120)
					if sentiment > 0:
						sentiment_emoji = "📈🟢"
					elif sentiment < 0:
						sentiment_emoji = "📉🔴"
					else:
						sentiment_emoji = "➡️⚪"
				except:
					sentiment_emoji = "ℹ️"
				
				message += f"{sentiment_emoji} **{name}**: {price_str}\n"
			
			except Exception:
				continue
		
		# Add timestamp
		from datetime import datetime
		timestamp = datetime.utcnow().strftime("%H:%M UTC")
		
		message += f"\n📅 Updated: {timestamp}\n\n"
		message += "💡 Use /liveprice <asset> for specific prices\n"
		message += "📊 Use /signals to see available signals"
		
		await update.message.reply_text(message)
	
	except Exception as e:
		await update.message.reply_text(f"Error fetching market data: {str(e)}")


# --------- MT5 LINK COMMAND ---------
async def mt5_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Link a MetaTrader 5 account for one-click trade execution.

	Usage: /mt5_link <login> <password> <server>
	Example: /mt5_link 123456 MyP@ssw0rd MetaQuotes-Demo

	Credentials are encrypted with Fernet symmetric encryption before storage.
	"""
	if update.effective_user is None or update.message is None:
		return

	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)

	# Require at least PREMIUM tier to link MT5
	if tier_rank(tier) < tier_rank("PREMIUM"):
		await update.message.reply_text(
			"🔒 MT5 account linking requires a Premium or VIP subscription.\n"
			"Use /upgrade to unlock one-click MT5 execution."
		)
		return

	args = (context.args or [])
	if len(args) < 3:
		await update.message.reply_text(
			"⚙️ *Link your MT5 Account*\n\n"
			"Usage: `/mt5_link <login> <password> <server>`\n\n"
			"Example:\n`/mt5_link 123456 MyP@ssw0rd MetaQuotes-Demo`\n\n"
			"🔒 Your password is encrypted end-to-end with AES-256 (Fernet) before storage.\n"
			"Neither SignalRankAI staff nor Railway can read it in plaintext.",
			parse_mode="Markdown"
		)
		return

	mt5_login = args[0].strip()
	mt5_password = args[1].strip()
	mt5_server = " ".join(args[2:]).strip()  # server names can contain spaces

	# Delete the message immediately to prevent credential exposure in chat history
	try:
		await update.message.delete()
	except Exception:
		pass

	processing_msg = await update.effective_chat.send_message(
		"🔄 Linking your MT5 account… please wait."
	)

	try:
		from services.mt5_client import link_mt5_account
		result = await link_mt5_account(
			telegram_user_id=user_id,
			mt5_login=mt5_login,
			mt5_password=mt5_password,
			mt5_server=mt5_server,
		)
		if result.get("ok"):
			meta_id = result.get("metaapi_account_id") or ""
			reply = (
				"✅ *MT5 Account Linked Successfully!*\n\n"
				f"🏦 Server: `{mt5_server}`\n"
				f"🔐 Login: `{mt5_login}` *(credentials encrypted)*\n"
			)
			if meta_id:
				reply += f"☁️ MetaApi Account ID: `{meta_id}`\n"
			reply += (
				"\nYou can now use the ⚡ *Trade on MT5* button "
				"on any signal to execute instantly."
			)
		else:
			err = result.get("error", "Unknown error")
			reply = (
				f"❌ *MT5 Link Failed*\n\n"
				f"Error: `{err}`\n\n"
				"Please check your login, password and server name, then try again.\n"
				"Use /mt5_link <login> <password> <server>"
			)
	except Exception as exc:
		reply = (
			f"❌ *MT5 Link Error*\n\n`{type(exc).__name__}: {exc}`\n\n"
			"Please try again or contact support with /support"
		)

	try:
		await processing_msg.edit_text(reply, parse_mode="Markdown")
	except Exception:
		await update.effective_chat.send_message(reply, parse_mode="Markdown")


# --------- MT5 STATUS COMMAND ---------
async def mt5_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show the linked MT5 account details for the current user."""
	if update.effective_user is None or update.message is None:
		return

	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)

	if tier_rank(tier) < tier_rank("PREMIUM"):
		await update.message.reply_text(
			"🔒 MT5 features require Premium or VIP.\nUse /upgrade to subscribe."
		)
		return

	try:
		from services.mt5_client import get_user_mt5_account_id
		from db.session import get_session
		from db.models import MT5Credentials
		from sqlalchemy import select
		async with get_session() as session:
			row = (await session.execute(
				select(MT5Credentials).where(MT5Credentials.user_id == user_id)
			)).scalar_one_or_none()
		if row is None:
			await update.message.reply_text(
				"No MT5 account linked.\n\nUse /mt5_link <login> <password> <server> to connect."
			)
			return
		reply = (
			"⚙️ *Your Linked MT5 Account*\n\n"
			f"🏦 Server: `{row.server}`\n"
			f"🔐 Login: `{row.mt5_login}` *(password encrypted)*\n"
		)
		if row.metaapi_account_id:
			reply += f"☁️ MetaApi ID: `{row.metaapi_account_id}`\n"
		reply += "\nUse ⚡ buttons on signals to trade instantly."
		await update.message.reply_text(reply, parse_mode="Markdown")
	except Exception as exc:
		await update.message.reply_text(f"Error fetching MT5 status: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /setlot  — PREMIUM: set fixed lot size
# ─────────────────────────────────────────────────────────────────────────────

async def setlot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Set the fixed lot size used for PREMIUM automated executions.

	Usage: /setlot <0.001–1.0>
	"""
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)

	if tier_rank(tier) < tier_rank("PREMIUM"):
		await update.message.reply_text(
			"🔒 /setlot is available on <b>PREMIUM</b> and above.\n"
			"Use /upgrade to subscribe.",
			parse_mode="HTML",
		)
		return

	args = context.args or []
	if not args:
		await update.message.reply_text(
			"Usage: <code>/setlot 0.01</code>\n"
			"Valid range: 0.001 – 1.0 lots",
			parse_mode="HTML",
		)
		return

	try:
		lot = float(args[0])
	except ValueError:
		await update.message.reply_text("❌ Invalid lot size. Example: <code>/setlot 0.05</code>", parse_mode="HTML")
		return

	if not (0.001 <= lot <= 1.0):
		await update.message.reply_text("❌ Lot size must be between 0.001 and 1.0.", parse_mode="HTML")
		return

	lot = round(lot, 3)

	try:
		from db.session import get_session as _gs
		from db.models import User
		from sqlalchemy import select

		async with _gs() as session:
			row = (await session.execute(select(User).where(User.telegram_user_id == user_id))).scalar_one_or_none()
			if row:
				row.fixed_lot_size = lot
				await session.commit()
	except Exception as exc:
		await update.message.reply_text(f"❌ Could not save lot size: {exc}")
		return

	await update.message.reply_text(
		f"✅ Fixed lot size set to <b>{lot}</b>.\n"
		"All future PREMIUM executions will use this lot size.",
		parse_mode="HTML",
	)


# ─────────────────────────────────────────────────────────────────────────────
# /setrisk  — VIP: set risk percentage per trade
# ─────────────────────────────────────────────────────────────────────────────

async def setrisk_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Set the risk percentage per trade for VIP automated executions.

	Usage: /setrisk <0.1–5.0>
	"""
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)

	if tier_rank(tier) < tier_rank("VIP"):
		await update.message.reply_text(
			"🔒 /setrisk is available on <b>VIP</b> only.\n"
			"Risk-based lot sizing is an exclusive VIP feature. Use /upgrade.",
			parse_mode="HTML",
		)
		return

	args = context.args or []
	if not args:
		await update.message.reply_text(
			"Usage: <code>/setrisk 1.5</code>\n"
			"Valid range: 0.1% – 5.0% of account balance per trade.",
			parse_mode="HTML",
		)
		return

	try:
		pct = float(args[0])
	except ValueError:
		await update.message.reply_text("❌ Invalid value. Example: <code>/setrisk 1.5</code>", parse_mode="HTML")
		return

	if not (0.1 <= pct <= 5.0):
		await update.message.reply_text("❌ Risk must be between 0.1% and 5.0%.", parse_mode="HTML")
		return

	pct = round(pct, 2)

	try:
		from db.session import get_session as _gs
		from db.models import User
		from sqlalchemy import select

		async with _gs() as session:
			row = (await session.execute(select(User).where(User.telegram_user_id == user_id))).scalar_one_or_none()
			if row:
				row.max_risk_percentage = pct
				await session.commit()
	except Exception as exc:
		await update.message.reply_text(f"❌ Could not save risk setting: {exc}")
		return

	await update.message.reply_text(
		f"✅ Risk per trade set to <b>{pct}%</b>.\n"
		"Lot size will be calculated automatically based on your account balance and SL distance.",
		parse_mode="HTML",
	)


# ─────────────────────────────────────────────────────────────────────────────
# /tiers  — Subscription comparison table
# ─────────────────────────────────────────────────────────────────────────────

async def tiers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Display a tier comparison table and upgrade links."""
	if update.effective_user is None or update.message is None:
		return

	premium_price = int(os.getenv("PREMIUM_PRICE_NGN", "15000"))
	vip_price = int(os.getenv("VIP_PRICE_NGN", "30000"))
	vip_limit = int(os.getenv("VIP_SEAT_LIMIT", "15"))

	msg = (
		"<b>📊 SignalRankAI Subscription Tiers</b>\n\n"
		"<b>🆓 FREE</b>\n"
		"  • Delayed signals (top 3/day)\n"
		"  • Basic win-rate stats\n"
		"  • Community access\n"
		"  • No MT5 execution\n\n"
		f"<b>💎 PREMIUM — ₦{premium_price:,}/month</b>\n"
		"  • All signals in real time\n"
		"  • Up to <b>3 automated MT5 executions/day</b>\n"
		"  • Fixed lot size (set with /setlot)\n"
		"  • TP2 targeting only\n"
		"  • Personal win-rate dashboard\n\n"
		f"<b>👑 VIP — ₦{vip_price:,}/month</b> (only {vip_limit} seats)\n"
		"  • Everything in PREMIUM, plus:\n"
		"  • <b>Unlimited</b> automated executions\n"
		"  • Risk-based lot sizing (/setrisk)\n"
		"  • Multi-stage TPs: TP1 → SL to entry → TP2 → TP3\n"
		"  • FOMO broadcast priority\n"
		"  • Friday leaderboard inclusion\n"
		"  • Direct support line\n\n"
		"👉 Use /upgrade to subscribe"
	)
	await update.message.reply_text(msg, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# /mystats  — Personal performance stats
# ─────────────────────────────────────────────────────────────────────────────

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show the user's personal trading statistics."""
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)

	try:
		from db.session import get_session as _gs
		from db.models import MT5Execution, User
		from sqlalchemy import select, func

		async with _gs() as session:
			# User info
			user_row = (await session.execute(
				select(User).where(User.telegram_user_id == user_id)
			)).scalar_one_or_none()

			# Total executions
			total_exec = (await session.execute(
				select(func.count()).where(MT5Execution.user_id == user_id)
			)).scalar() or 0

			# Win / loss
			wins = (await session.execute(
				select(func.count()).where(
					MT5Execution.user_id == user_id,
					MT5Execution.status == "tp_hit",
				)
			)).scalar() or 0

			losses = (await session.execute(
				select(func.count()).where(
					MT5Execution.user_id == user_id,
					MT5Execution.status == "sl_hit",
				)
			)).scalar() or 0

			# Total realized PnL
			total_pnl = (await session.execute(
				select(func.sum(MT5Execution.realized_pnl)).where(
					MT5Execution.user_id == user_id,
					MT5Execution.realized_pnl.isnot(None),
				)
			)).scalar() or 0.0

		win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

		sub_expiry = ""
		if user_row:
			from datetime import timezone as _tz
			from datetime import datetime as _dt

			# Try premium_until / vip_until fields
			for field in ("vip_until", "premium_until"):
				expiry = getattr(user_row, field, None)
				if expiry:
					if hasattr(expiry, "tzinfo") and expiry.tzinfo is None:
						expiry = expiry.replace(tzinfo=_tz.utc)
					sub_expiry = f"\n📅 Subscription expires: <b>{expiry.strftime('%d %b %Y')}</b>"
					break

		daily_exec = 0
		if user_row:
			from engine.tiered_executor import reset_daily_counter_if_needed
			reset_daily_counter_if_needed(user_row)
			daily_exec = int(getattr(user_row, "daily_executions_today", 0) or 0)

		msg = (
			f"<b>📈 My Stats — {tier}</b>\n\n"
			f"🔢 Total executions: <b>{total_exec}</b>\n"
			f"✅ Wins: <b>{wins}</b>  ❌ Losses: <b>{losses}</b>\n"
			f"🎯 Win rate: <b>{win_rate:.1f}%</b>\n"
			f"💰 Total realized P&amp;L: <b>${total_pnl:+.2f}</b>\n"
		)
		if tier == "PREMIUM":
			from engine.tiered_executor import PREMIUM_DAILY_LIMIT
			remaining = max(0, PREMIUM_DAILY_LIMIT - daily_exec)
			msg += f"📋 Today's executions: <b>{daily_exec}/{PREMIUM_DAILY_LIMIT}</b> ({remaining} remaining)\n"
		msg += sub_expiry
		await update.message.reply_text(msg, parse_mode="HTML")

	except Exception as exc:
		await update.message.reply_text(f"⚠️ Could not load stats: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /referral  — Generate referral deep-link
# ─────────────────────────────────────────────────────────────────────────────

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Generate a personal referral link and show referral stats."""
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id

	bot_username = ""
	try:
		bot_username = (await context.bot.get_me()).username or ""
	except Exception:
		bot_username = os.getenv("BOT_USERNAME", "SignalRankBot")

	referral_url = f"https://t.me/{bot_username}?start=ref_{user_id}"
	bonus_days = int(os.getenv("REFERRAL_BONUS_DAYS", "7"))

	# Count how many users were referred by this user
	referred_count = 0
	bonus_earned_days = 0
	try:
		from db.session import get_session as _gs
		from db.models import User
		from sqlalchemy import select, func

		async with _gs() as session:
			referred_count = (await session.execute(
				select(func.count()).where(User.referred_by == user_id)
			)).scalar() or 0
			# Bonus is earned when referred user pays — count paying referrals
			# (users who are PREMIUM or VIP and were referred by this user)
			paying = (await session.execute(
				select(func.count()).where(
					User.referred_by == user_id,
					User.tier.in_(["PREMIUM", "VIP"]),
				)
			)).scalar() or 0
			bonus_earned_days = paying * bonus_days
	except Exception:
		pass

	msg = (
		f"🔗 <b>Your Referral Link</b>\n\n"
		f"<code>{referral_url}</code>\n\n"
		f"📊 Referrals: <b>{referred_count}</b>\n"
		f"🎁 Bonus earned: <b>+{bonus_earned_days} days</b> subscription\n\n"
		f"💡 Earn <b>+{bonus_days} free days</b> every time someone you refer upgrades to PREMIUM or VIP.\n"
		f"Share your link and grow your streak!"
	)
	await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)


# ─────────────────────────────────────────────────────────────────────────────
# /connect_broker  — FSM-guided MT5 account setup
# ─────────────────────────────────────────────────────────────────────────────

# Conversation states
_CB_ASK_LOGIN = 0
_CB_ASK_PASSWORD = 1
_CB_ASK_SERVER = 2
_CB_CONFIRM = 3


async def connect_broker_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
	"""Entry point for the /connect_broker conversation."""
	if update.effective_user is None or update.message is None:
		return -1
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)

	if tier_rank(tier) < tier_rank("PREMIUM"):
		await update.message.reply_text(
			"🔒 MT5 broker connection requires <b>PREMIUM</b> or above.\nUse /upgrade.",
			parse_mode="HTML",
		)
		return -1  # ConversationHandler.END

	await update.message.reply_text(
		"🔗 <b>Connect Your MT5 Broker</b>\n\n"
		"I'll walk you through linking your MetaTrader 5 account.\n\n"
		"<b>Step 1/3</b> — Enter your <b>MT5 login number</b> (numeric account ID):\n\n"
		"Type /cancel at any time to abort.",
		parse_mode="HTML",
	)
	return _CB_ASK_LOGIN


async def connect_broker_got_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
	if update.message is None or update.message.text is None:
		return _CB_ASK_LOGIN
	login_text = update.message.text.strip()
	if not login_text.isdigit():
		await update.message.reply_text("❌ Login must be a numeric account ID. Try again:")
		return _CB_ASK_LOGIN
	context.user_data["mt5_login"] = login_text
	await update.message.reply_text(
		"<b>Step 2/3</b> — Enter your <b>MT5 password</b>:\n\n"
		"⚠️ Your password will be <b>encrypted</b> before storage. "
		"We never store it in plain text.",
		parse_mode="HTML",
	)
	return _CB_ASK_PASSWORD


async def connect_broker_got_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
	if update.message is None or update.message.text is None:
		return _CB_ASK_PASSWORD
	context.user_data["mt5_password"] = update.message.text.strip()
	# Delete the password message for security
	try:
		await update.message.delete()
	except Exception:
		pass
	await update.message.reply_text(
		"✅ Password received and will be encrypted.\n\n"
		"<b>Step 3/3</b> — Enter your <b>MT5 server name</b> (e.g. <code>ICMarkets-Demo</code>):",
		parse_mode="HTML",
	)
	return _CB_ASK_SERVER


async def connect_broker_got_server(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
	if update.message is None or update.message.text is None:
		return _CB_ASK_SERVER
	server = update.message.text.strip()
	if not server:
		await update.message.reply_text("❌ Server name cannot be empty. Try again:")
		return _CB_ASK_SERVER
	context.user_data["mt5_server"] = server
	login = context.user_data.get("mt5_login", "")
	await update.message.reply_text(
		f"<b>Confirm your MT5 details:</b>\n\n"
		f"🔢 Login: <code>{login}</code>\n"
		f"🏦 Server: <code>{server}</code>\n"
		f"🔐 Password: <code>{'*' * 8}</code> (hidden)\n\n"
		"Reply <b>YES</b> to confirm or <b>NO</b> to cancel.",
		parse_mode="HTML",
	)
	return _CB_CONFIRM


async def connect_broker_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
	if update.message is None or update.effective_user is None:
		return -1
	text = (update.message.text or "").strip().upper()
	if text != "YES":
		await update.message.reply_text("❌ Setup cancelled. Use /connect_broker to start again.")
		context.user_data.clear()
		return -1  # END

	user_id: int = update.effective_user.id
	login: str = context.user_data.get("mt5_login", "")
	password: str = context.user_data.get("mt5_password", "")
	server: str = context.user_data.get("mt5_server", "")
	context.user_data.clear()

	await update.message.reply_text("⏳ Linking your account via MetaApi… (this may take 30–60 s)")

	try:
		from services.mt5_client import link_mt5_account
		result = await link_mt5_account(
			telegram_user_id=user_id,
			mt5_login=login,
			mt5_password=password,
			server=server,
		)
		account_id = result.get("metaapi_account_id") or result.get("id") or "unknown"
		await update.message.reply_text(
			f"✅ <b>MT5 account linked!</b>\n\n"
			f"☁️ MetaApi ID: <code>{account_id}</code>\n\n"
			"You can now use ⚡ buttons on signals to execute trades instantly.\n"
			"Use /setlot to configure your lot size.",
			parse_mode="HTML",
		)
	except Exception as exc:
		await update.message.reply_text(
			f"❌ <b>Failed to link account:</b> {exc}\n\n"
			"Check your login/password/server and try /connect_broker again.",
			parse_mode="HTML",
		)
	return -1  # END


async def connect_broker_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
	if update.message:
		await update.message.reply_text("❌ Broker setup cancelled.")
	if context.user_data:
		context.user_data.clear()
	return -1  # END


def build_connect_broker_conversation():
	"""Build and return the ConversationHandler for /connect_broker.

	Register this in bot.py with ``application.add_handler()``.
	"""
	from telegram.ext import ConversationHandler, MessageHandler, filters, CommandHandler as _CH

	return ConversationHandler(
		entry_points=[_CH("connect_broker", connect_broker_start)],
		states={
			_CB_ASK_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_broker_got_login)],
			_CB_ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_broker_got_password)],
			_CB_ASK_SERVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_broker_got_server)],
			_CB_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, connect_broker_confirm)],
		},
		fallbacks=[_CH("cancel", connect_broker_cancel)],
		conversation_timeout=300,
	)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Step 1 of /cancel — show policy warning + InlineKeyboard confirmation.

	Displays the NO REFUND policy, subscription expiry date, and two buttons:
	  ❌ Yes, Cancel Auto-Renew  →  cancel_confirm_callback (actual gateway disable)
	  🔙 Nevermind               →  cancel_nevermind_callback (no-op, dismiss)
	Safe to call on FREE tier (shows informational message and exits).
	"""
	user_id = update.effective_user.id if update.effective_user else None
	if not user_id:
		return

	try:
		from db.session import get_session
		from db.models import User
		from db.repository import get_active_subscription
		from sqlalchemy import select
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton

		async with get_session() as session:
			row = await session.execute(
				select(User).where(User.telegram_user_id == int(user_id))
			)
			user = row.scalars().first()

			if not user:
				await update.message.reply_text("\u26a0\ufe0f No account found. Use /start to register.")
				return

			current_tier = getattr(user, "tier", "free").lower()
			if current_tier == "free":
				await update.message.reply_text(
					"\u2139\ufe0f You don't have an active paid subscription to cancel."
				)
				return

			# Retrieve subscription expiry for the policy message
			expiry_str = "the end of your current billing period"
			try:
				sub = await get_active_subscription(
					session, telegram_user_id=int(user_id), tier=current_tier
				)
				if sub and sub.expires_at:
					expiry_str = f"*{sub.expires_at.strftime('%B %d, %Y')}*"
			except Exception:
				pass

		vip_note = (
			"\n\n\u26a0\ufe0f *Note to VIPs: Once your period ends, your seat is permanently "
			"given to the next trader on the waitlist.*"
			if current_tier == "vip"
			else ""
		)
		msg = (
			"\u26a0\ufe0f *Subscription Cancellation* \u26a0\ufe0f\n\n"
			"\U0001f4dc *Our Policy:* We operate a *STRICT NO REFUND* policy. "
			"If you cancel, you will *NOT* be billed again, but you will retain "
			"your current tier access until your billing cycle ends on "
			f"{expiry_str}."
			+ vip_note
			+ "\n\nAre you sure you want to cancel auto-renewal?"
		)
		keyboard = InlineKeyboardMarkup([[
			InlineKeyboardButton("\u274c Yes, Cancel Auto-Renew", callback_data="cancel_confirm"),
			InlineKeyboardButton("\U0001f519 Nevermind", callback_data="cancel_nevermind"),
		]])
		await update.message.reply_text(msg, reply_markup=keyboard, parse_mode="Markdown")

	except Exception as e:
		logger.error(f"[cancel] cancel_command failed for user {user_id}: {e}")
		await update.message.reply_text(
			"\u274c Could not process cancellation. Please contact /support."
		)


async def _cancel_and_disable_paystack(user_id: int) -> dict:
	"""Shared helper: call Paystack /subscription/disable and set auto_renew=False in DB.

	Returns:
	  {"success": bool, "gateway_cancelled": bool, "tier": str}
	Used by cancel_confirm_callback to perform the actual cancellation work.
	"""
	try:
		from db.session import get_session
		from db.models import User
		from sqlalchemy import select, update as sa_update

		async with get_session() as session:
			row = await session.execute(
				select(User).where(User.telegram_user_id == int(user_id))
			)
			user = row.scalars().first()

			if not user:
				return {"success": False, "gateway_cancelled": False, "tier": "free"}

			current_tier = getattr(user, "tier", "free").lower()
			sub_code = getattr(user, "paystack_subscription_code", None)

			# Disable Paystack recurring billing (2-step: fetch email_token → POST disable)
			gateway_cancelled = False
			if sub_code:
				try:
					import httpx as _httpx, os as _os
					secret = _os.getenv("PAYSTACK_SECRET_KEY", "").strip()
					if secret:
						headers = {
							"Authorization": f"Bearer {secret}",
							"Content-Type": "application/json",
						}
						async with _httpx.AsyncClient(timeout=15) as client:
							# Step 1: fetch subscription to get email_token
							r1 = await client.get(
								f"https://api.paystack.co/subscription/{sub_code}",
								headers=headers,
							)
							email_token = ""
							if r1.status_code < 400:
								email_token = (r1.json().get("data") or {}).get("email_token", "")
							# Step 2: disable with code + email_token
							r2 = await client.post(
								"https://api.paystack.co/subscription/disable",
								json={"code": sub_code, "token": email_token},
								headers=headers,
							)
							gateway_cancelled = r2.status_code < 400
				except Exception as _ge:
					# Non-fatal — DB cancellation still proceeds
					logger.warning(f"[cancel] Paystack gateway cancel failed: {_ge}")

			# Mark auto_renew=False; access expires naturally at period end (no downgrade)
			await session.execute(
				sa_update(User).where(User.id == user.id).values(auto_renew=False)
			)
			await session.commit()
			return {"success": True, "gateway_cancelled": gateway_cancelled, "tier": current_tier}

	except Exception as e:
		logger.error(f"[cancel] _cancel_and_disable_paystack failed for user {user_id}: {e}")
		return {"success": False, "gateway_cancelled": False, "tier": "free"}


async def cancel_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Step 2 of /cancel (confirmed) — execute Paystack disable + set auto_renew=False.

	Triggered by the '❌ Yes, Cancel Auto-Renew' InlineKeyboard button.
	Edits the original confirmation message with the result summary.
	"""
	query = update.callback_query
	await query.answer("Processing cancellation...")
	user_id = update.effective_user.id if update.effective_user else None
	if not user_id:
		return

	try:
		result = await _cancel_and_disable_paystack(user_id)

		if not result["success"]:
			await query.edit_message_text(
				"\u274c Cancellation failed. Please contact /support.",
				parse_mode="Markdown",
			)
			return

		tier = result["tier"].upper()
		gateway_note = (
			"\u2705 Paystack auto-billing stopped at the gateway."
			if result["gateway_cancelled"]
			else "\u26a0\ufe0f Please also cancel via your Paystack dashboard if billed directly."
		)
		await query.edit_message_text(
			f"\u2705 *Cancellation Confirmed*\n\n"
			f"Your {tier} auto-renewal is now *OFF*. "
			f"You keep full access until your billing cycle ends.\n\n"
			f"{gateway_note}\n\n"
			f"You can re-subscribe anytime with /upgrade. \U0001f64f",
			parse_mode="Markdown",
		)

	except Exception as e:
		logger.error(f"[cancel] cancel_confirm_callback failed for user {user_id}: {e}")
		try:
			await query.edit_message_text(
				"\u274c Cancellation failed. Please contact /support."
			)
		except Exception:
			pass


async def cancel_nevermind_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Step 2 of /cancel (aborted) — user clicked Nevermind; no DB changes.

	Triggered by the '🔙 Nevermind' InlineKeyboard button.
	Edits the original message to confirm no action was taken.
	"""
	query = update.callback_query
	await query.answer("Good choice! \U0001f4aa")
	try:
		await query.edit_message_text(
			"\U0001f519 *Cancellation Aborted*\n\n"
			"Your subscription remains fully active. Keep catching those pips! \U0001f680",
			parse_mode="Markdown",
		)
	except Exception as e:
		logger.warning(f"[cancel] cancel_nevermind_callback edit failed: {e}")