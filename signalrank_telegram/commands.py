from telegram import Update
from telegram.ext import ContextTypes
from db.session import get_session, get_engine_for_event_loop
from db.repository import get_active_subscription
from engine.market_state import get_market_state_async
from engine.strategies.signal_generator import SignalGenerator
from data.news import get_news_sentiment, fetch_news_headlines
# --- USER COMMAND: /status ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	if get_engine_for_event_loop() is None:
		await update.message.reply_text("Database not configured.")
		return
	try:
		async with get_session() as session:
			sub = await get_active_subscription(session, telegram_user_id=update.effective_user.id)
			await session.commit()
		if sub is None:
			await update.message.reply_text("You are on the FREE tier. Upgrade for more features!")
			return
		tier = getattr(sub, "tier", "free").upper()
		expires = getattr(sub, "expires_at", None)
		status = getattr(sub, "status", "inactive").capitalize()
		msg = f"\n<b>Subscription Status</b>\nTier: <b>{tier}</b>\nStatus: <b>{status}</b>"
		if expires:
			msg += f"\nExpires: <b>{expires.strftime('%Y-%m-%d %H:%M')}</b>"
		await update.message.reply_text(msg, parse_mode="HTML")
	except Exception as e:
		await update.message.reply_text(f"Unable to fetch status: {e}")

# --- USER COMMAND: /support ---
async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	support_contact = "@theocrilox"
	await update.message.reply_text(f"For help or questions, contact support: {support_contact}")
# Import actual owner/admin command handlers
from signalrank_telegram.owner_commands import owner_users, owner_revenue, correct_signal
# --------- DEV/ADMIN PLACEHOLDER COMMANDS ---------
async def unlock(update, context):
	if update.message is not None:
		await update.message.reply_text("🔓 Unlock command received. (No action implemented.)")

async def dev_pause(update, context):
	if update.message is not None:
		await update.message.reply_text("⏸️ Dev pause command received. (No action implemented.)")

async def dev_resume(update, context):
	if update.message is not None:
		await update.message.reply_text("▶️ Dev resume command received. (No action implemented.)")

async def dev_force_signal(update, context):
	if update.message is not None:
		await update.message.reply_text("⚡ Dev force signal command received. (No action implemented.)")

async def dev_invalidate(update, context):
	if update.message is not None:
		await update.message.reply_text("❌ Dev invalidate command received. (No action implemented.)")
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

# --------- SCHEDULED REPORTS OPT-IN COMMAND ---------
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
# --------- CUSTOM SIGNAL FILTERS COMMAND ---------
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

from sqlalchemy.ext.asyncio.session import AsyncSession

from sqlalchemy.ext.asyncio.session import AsyncSession
from typing import Tuple

from sqlalchemy import Select
from typing import Tuple

from sqlalchemy import Select
from typing import Tuple

from sqlalchemy import Select
from typing import Tuple

from sqlalchemy import Select
from typing import Tuple

from sqlalchemy import Result

from sqlalchemy.ext.asyncio.session import AsyncSession

from telegram._user import User

from sqlalchemy.ext.asyncio.session import AsyncSession

from sqlalchemy.ext.asyncio.session import AsyncSession

from sqlalchemy.ext.asyncio.session import AsyncSession

from sqlalchemy.ext.asyncio.session import AsyncSession
from typing import Tuple

from sqlalchemy import Result

from sqlalchemy.ext.asyncio.session import AsyncSession

from sqlalchemy.ext.asyncio.session import AsyncSession
from typing import Tuple

from sqlalchemy import Result
from typing import Tuple

from sqlalchemy import Result

from sqlalchemy.ext.asyncio.session import AsyncSession

from sqlalchemy.ext.asyncio.session import AsyncSession

from sqlalchemy.ext.asyncio.session import AsyncSession

from sqlalchemy.ext.asyncio.session import AsyncSession
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web')))
try:
	from web.api import generate_api_key, set_user_api_key, get_user_api_key
except Exception:
	generate_api_key = lambda: "demo-key"
	set_user_api_key = lambda user_id, key: None
	get_user_api_key = lambda user_id: None

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
# --------- REFERRAL LEADERBOARD & REWARDS ---------
from db.session import get_session
from db.pg_features import get_or_create_user
from db.models import Outcome, Outcome, ReferralReward, ReferralAttribution, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Signal, Subscription, Signal, Signal, Signal, User
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
			FROM referrals
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
				text("SELECT id, username FROM users WHERE id = ANY(:ids)"), {"ids": ids}
			)
			users = {r[0]: r[1] for r in res2.fetchall()}
		msg = "🏆 Referral Leaderboard:\n\n"
		for i, (uid, cnt) in enumerate(rows, 1):
			uname = users.get(uid) or f"User {uid}"
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
			await update.message.reply_text("No rewards earned yet. Refer friends to earn rewards!")
			return
		msg = "🎁 Your Referral Rewards:\n"
		for rtype, cnt, total in rows:
			msg += f"{rtype}: {cnt} times, total value: {total}\n"
		await update.message.reply_text(msg)
from engine.signal_analytics import signal_analytics
# --------- ADMIN ANALYTICS COMMANDS ---------
from config import OWNER_IDS
def _is_admin(user_id) -> bool:
	return int(user_id) in OWNER_IDS

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
	# Placeholder: If strategies are tracked, add here. For now, show fill_rates as proxy.
	stats = signal_analytics.get_stats()
	fill_rates = stats.get('fill_rates', {})
	top = sorted(fill_rates.items(), key=lambda x: x[1], reverse=True)[:10]
	msg: str = "\n".join([f"{a}: {c:.2f}" for a, c in top]) or "No data."
	await update.message.reply_text(f"Top Strategies (by fill rate):\n{msg}")

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
	import platform, psutil, shutil
	import datetime
	import os
	# ENGINE import removed; use get_engine_for_event_loop() if needed
	lines: list[str] = ["🩺 System Self-Check"]
	lines.append(f"Time: {datetime.datetime.now(datetime.timezone.utc).isoformat()} UTC")
	lines.append(f"Host: {platform.node()} | OS: {platform.system()} {platform.release()}")
	lines.append(f"Python: {platform.python_version()}")
	lines.append(f"RAM: {psutil.virtual_memory().percent}% used")
	lines.append(f"Disk: {shutil.disk_usage('/').percent}% used")
	# DB status
	try:
		if get_engine_for_event_loop() is not None:
			lines.append("DB: ✅ Connected")
		else:
			lines.append("DB: ❌ Not connected")
	except Exception:
		lines.append("DB: ❓ Unknown")
		# ML drift
		try:
			import json
			from pathlib import Path
			drift_path: Path = Path(__file__).parent.parent / "ml" / "ml_drift.json"
			if drift_path.exists():
				with open(drift_path, "r") as f:
					drift = json.load(f)
				acc = drift.get("accuracy")
				auc = drift.get("auc")
				lines.append(f"ML: acc={acc:.3f} auc={auc:.3f}")
			else:
				lines.append("ML: No drift data")
		except Exception:
			lines.append("ML: Drift check error")
		# Uptime
		try:
			import time
			uptime: float = time.time() - psutil.boot_time()
			lines.append(f"Uptime: {uptime/3600:.1f}h")
		except Exception:
			pass
		await update.message.reply_text("\n".join(lines))
	# ML drift
	try:
		import json
		from pathlib import Path
		drift_path: Path = Path(__file__).parent.parent / "ml" / "ml_drift.json"
		if drift_path.exists():
			with open(drift_path, "r") as f:
				drift = json.load(f)
			acc = drift.get("accuracy")
			auc = drift.get("auc")
			lines.append(f"ML: acc={acc:.3f} auc={auc:.3f}")
		else:
			lines.append("ML: No drift data")
	except Exception:
		lines.append("ML: Drift check error")
	# Uptime
	try:
		import time
		uptime: float = time.time() - psutil.boot_time()
		lines.append(f"Uptime: {uptime/3600:.1f}h")
	except Exception:
		pass
	await update.message.reply_text("\n".join(lines))
from .user_prefs import user_prefs_store
from telegram import Update
from telegram.ext import ContextTypes
# --------- NOTIFICATION CUSTOMIZATION COMMAND ---------
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

from core.redis_state import KillSwitchState, KillSwitchState, state
from .access import resolve_user_tier


_audit_logger: logging.Logger = logging.getLogger("audit")

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
	lang = _get_user_language(user_id)
	msg: str = f"*{_t(user_id, 'help_title')}*\n\n" + get_help_message(tier)
	# Add dashboard link for eligible users
	if tier.strip().upper() in {"PREMIUM", "VIP", "ADMIN", "OWNER"}:
		dashboard_url: str = f"https://yourdomain.com/userdash/login?uid={user_id}"
		# Escape brackets and parentheses in dashboard link for Markdown V2
		safe_dashboard_url: str = dashboard_url.replace('(', '\\(').replace(')', '\\)').replace('[', '\\[').replace(']', '\\]')
		safe_dashboard_text: str = _t(user_id, 'dashboard').replace('[', '\\[').replace(']', '\\]')
		msg += f"\n\n🌐 [{safe_dashboard_text}]({safe_dashboard_url})"
	await update.message.reply_text(msg, disable_web_page_preview=True, parse_mode="MarkdownV2")

# --------- MYID COMMAND ---------
async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	msg: str = f"Your Telegram user ID: `{user_id}`\nYour current tier: *{tier}*"
	await update.message.reply_text(msg, parse_mode="Markdown")

# --------- DASHBOARD COMMAND ---------
async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	if tier.strip().upper() not in {"PREMIUM", "VIP", "ADMIN", "OWNER"}:
		await update.message.reply_text("The dashboard is only available for Premium, VIP, and above.")
		return
	dashboard_url: str = f"https://yourdomain.com/userdash/login?uid={user_id}"
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

	# Owner and admin always get VIP format
	if tier.lower() in {"owner", "admin"}:
		tier = "VIP"

	signals_list: list[dict] = []
	
	# FREE tier: show delivered signals only - now sample 2 random signals with score >= 55
	if tier_rank(tier) < tier_rank("PREMIUM"):
		try:
			from db.session import get_session
			if ENGINE is not None:
				from db.pg_features import list_signals_sent_today
				async with get_session() as session:
					# Fetch ALL signals delivered to user today (no limit)
					rows: list[Signal] = await list_signals_sent_today(session, telegram_user_id=int(user_id))
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
		if ENGINE is not None:
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
			if ENGINE is not None:
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
		}
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
			if position_lines or advice_line:
				base += "\n\n📍 Position (best-effort)\n" + "\n".join(position_lines)
				if advice_line:
					base += "\n\n🧠 Suggestion\n" + str(advice_line)
			await update.message.reply_text(base)
			return

		base: None | str = format_signal(sig_dict)
		if position_lines or advice_line:
			base += "\n\n📍 Position (best-effort)\n" + "\n".join(position_lines)
			if advice_line:
				base += "\n\n🧠 Suggestion\n" + str(advice_line)
		await update.message.reply_text(base)
		return
	except Exception as e:
		import logging
		logging.getLogger(__name__).error(f"signal_command failed: {e}", exc_info=True)
		await update.message.reply_text("Signal lookup is temporarily unavailable.")
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
		await update.message.reply_text("Outcome lookup is temporarily unavailable.")
		return
		# If outcome not yet determined, show current signal details based on tier
		# Determine what to show based on tier
	try:
			vip_cut = float(getattr(config, "VIP_SCORE_THRESHOLD", 72))
	except Exception:
			vip_cut = 72.0
		
		# Owner always gets VIP format
	if user_tier in {"owner", "admin"}:
			user_tier = "vip"
		
	show_levels: bool = user_tier in {"vip", "premium"}
	show_strategy: bool = user_tier in {"vip"}
	show_strength: bool = user_tier in {"vip"}
		
	lines: list[str] = ["🔄 Signal In Progress", ""]
		
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
			
			# ML Score
			ml_prob: os.Any | None = getattr(sig, "ml_probability", None)
			if ml_prob is not None:
				ml_pct: float = round(float(ml_prob) * 100, 1)
				ml_emoji: str = "✅" if float(ml_prob) >= 0.75 else ("⚠️" if float(ml_prob) >= 0.5 else "❌")
				lines.append(f"{ml_emoji} ML Score: {ml_pct}%")
		
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
		
	def _binance_symbol_rest(asset: str) -> str:
			a: str = (asset or "").upper().strip()
			a: str = a.replace("/", "").replace("-", "")
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
			
				candles = []
				for tf in ("1m", "5m", "15m"):
					candles = get_candles(asset, tf)
					if candles:
						break
			
				if not candles:
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
			if near_sl:
				return ("⚠️ Price is close to SL zone. Consider reducing exposure or exiting early to avoid a full SL hit.", metrics)
			return ("⏳ Still developing. Consider waiting; avoid moving SL further away.", metrics)
		
		# Calculate current position
	entry: float | None = _as_float(sig.entry)
	sl: float | None = _as_float(sig.stop_loss)
	tp: None | float = _parse_tp(sig.take_profit)
		
	if entry is not None and sl is not None and tp is not None:
			price: float | None = _current_price(str(sig.asset))
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
		code = None
		progress = None

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

	if code:
		await update.message.reply_text(
			f"🎁 Your invite code: {code}\n\n"
			"Reward: invite 3 new users → get +7 days Premium.\n"
			"Invite link is unavailable (bot username not resolved)."
			f"{progress_line}"
		)
	else:
		await update.message.reply_text("Invite system is temporarily unavailable.")

async def pricing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if await _public_guard(update):
		return
	# VIP seat info from Postgres (best-effort)
	try:
		from db.session import ENGINE, get_session
		from db.repository import count_active_vip_users
		if ENGINE is not None:
			async with get_session() as session:
				used: int = await count_active_vip_users(session, exclude_telegram_user_ids=set())
				await session.commit()
			limit = int(getattr(config, "VIP_SEAT_LIMIT", 15))
			remaining: int = max(0, limit - used)
		else:
			used, remaining, limit = 0, 15, 15
	except Exception:
		used, remaining, limit = 0, 15, 15
	vip_line: str = f"VIP seats remaining: {remaining}/{limit}"
	msg: str = (
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
	"""Generates Paystack payment links for subscriptions with tier confirmation."""
	user_id: int = update.effective_user.id
	from paystack.paystack import generate_paystack_link
	from signalrank_telegram.payment_handler import format_tier_upgrade_confirmation
	
	# Plan codes (optional; used later when wiring Paystack plans properly)
	premium_monthly_code: str | None = os.getenv("PAYSTACK_PLAN_CODE_PREMIUM_MONTHLY")
	premium_quarterly_code: str | None = os.getenv("PAYSTACK_PLAN_CODE_PREMIUM_QUARTERLY")
	premium_semiannual_code: str | None = os.getenv("PAYSTACK_PLAN_CODE_PREMIUM_SEMIANNUAL")
	vip_monthly_code: str | None = os.getenv("PAYSTACK_PLAN_CODE_VIP_MONTHLY")

	links = []
	
	# PREMIUM options
	premium_plans: list[tuple[str, int, int, str | None]] = [
		("Premium (₦4,000 / 7 days)", 4000, 7, getattr(config, "PAYSTACK_PLAN_CODE_PREMIUM_WEEKLY", None)),
		("Premium (₦12,000 / 30 days)", 12000, 30, premium_monthly_code),
		("Premium (₦28,000 / 90 days)", 28000, 90, premium_quarterly_code),
	]
	
	premium_formatted: str = await format_tier_upgrade_confirmation("PREMIUM", 4000, 7, user_id)
	premium_msg: str = premium_formatted + "\n\n📌 PREMIUM Plans:\n"
	
	for label, amount, days, plan_code in premium_plans:
		link = generate_paystack_link(user_id, amount, tier="premium", duration_days=days, plan_code=plan_code)
		premium_msg += f"• {label}: {link}\n"
	
	if update.message is not None:
		await update.message.reply_text(premium_msg)
	
	# VIP link only if seats available (or user is owner/bypassed/already VIP)
	try:
		from db.session import ENGINE, get_session
		from db.repository import count_active_vip_users, get_active_subscription
		from config import OWNER_IDS
		if ENGINE is not None:
			async with get_session() as session:
				used: int = await count_active_vip_users(session, exclude_telegram_user_ids=set())
				limit = int(os.getenv("VIP_SEAT_LIMIT", "15") or "15")
				remaining: int = max(0, limit - used)
				sub: Subscription | None = await get_active_subscription(session, telegram_user_id=user_id, tier="vip")
				already_vip: bool = sub is not None
				await session.commit()
		else:
			remaining, limit, already_vip = 15, 15, False
		try:
			bypassed = bool(await state.has_temp_owner(user_id))
		except Exception:
			bypassed = False
		is_owner: bool = user_id in OWNER_IDS
		can_offer_vip: bool = (remaining > 0) or already_vip or bypassed or is_owner
	except Exception:
		can_offer_vip = True
		remaining = None
		limit = None

	if can_offer_vip:
		vip_formatted: str = await format_tier_upgrade_confirmation("VIP", 20000, 30, user_id)
		vip_msg: str = vip_formatted + "\n\n"
		
		vip_link = generate_paystack_link(user_id, 20000, tier="vip", duration_days=30, plan_code=vip_monthly_code)
		vip_msg += f"🔗 {vip_link}\n"
		
		if remaining is not None:
			vip_msg += f"\n⚠️ {remaining}/{limit} VIP seats remaining"
		
		if update.message is not None:
			await update.message.reply_text(vip_msg)
	else:
		if update.message is not None:
			await update.message.reply_text(
				"🏆 VIP TIER (SOLD OUT)\n\n"
				"VIP seats are currently full.\n"
				"Check /pricing later or upgrade to Premium to get started!"
			)
# --- Extra Signal Purchase Logic ---
from telegram import Update



# /policy or /refunds command
async def policy_command(update, context) -> None:
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


TIER_RANKS: dict[str, int] = {
	"FREE": 0,
	"PREMIUM": 1,
	"VIP": 2,
	"OWNER": 3
}

def tier_rank(tier) -> int:
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
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
			from db.models import User
			from sqlalchemy import select
			from db.repository import get_or_create_user
			from db.pg_features import record_bot_event
			from db.pg_features import ensure_alert_prefs
			async with get_session() as session:
				res: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(user_id)))
				existing: User | None = res.scalar_one_or_none()
				is_new: bool = existing is None
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
async def about_command(update, context) -> None:
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
			await update.message.reply_text("Performance is temporarily unavailable. Please try again shortly.")
		return
	total: int = len(trades_30d)
	if total == 0:
		if update.message is not None:
			await update.message.reply_text("No signals in the last 30 days.")
		return
	win_count: int = sum(1 for t in trades_30d if (len(t) > 15 and str(t[15]).upper() == 'TP'))
	win_rate: float | int = win_count / total if total > 0 else 0
	if tier_rank(tier) < tier_rank("PREMIUM"):
		bucket = "mixed"
		if win_rate >= 0.6:
			bucket = "strong"
		elif win_rate <= 0.4:
			bucket = "cautious"
		msg: str = (
			"📊 Performance (limited)\n\n"
			f"Recent snapshot: {bucket}.\n"
			"Upgrade to Premium for full stats and history."
		)
		if update.message is not None:
			await update.message.reply_text(msg)
		return
	msg: str = f"Last 30 days:\n✔ Signals: {total}\n✔ Snapshot win-rate: {round(win_rate*100,1)}%"
	if update.message is not None:
		await update.message.reply_text(msg)


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
			async with get_session() as session:
				week = await get_weekly_recap_stats(session, int(user_id))
				today_rows: list[Signal] = await list_signals_sent_today(session, int(user_id))
				await session.commit()
			total_week = int((week or {}).get("total") or 0)
			today: int = len(today_rows or [])
			msg: str = (
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
	msg: str = (
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
	lines: list[str] = ["🧾 History (last 10):", ""]
	for t in filtered:
		try:
			lines.append(f"• {t[1]} {t[2]} {t[3]} entry={t[4]} sl={t[5]} tp={t[6]}")
		except Exception:
			continue
	if update.message is not None:
		await update.message.reply_text("\n".join(lines))


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
async def early_command(update, context) -> None:
	if update.message is not None:
		await update.message.reply_text("⚡ Early access is automatic for VIP. You’ll receive signals first when available.")


@require_tier("VIP")
async def report_command(update, context) -> None:
	# Structured text report (monthly)
	if update.message is None:
		return
	await update.message.reply_text(
		"🗓️ VIP Monthly Report\n\n"
		"Monthly reports are delivered automatically.\n"
		"This command will show the latest report when available."
	)
