from utils.timeutils import now_utc_naive
import os
import asyncio

from telegram import Update
from telegram.ext import ContextTypes
from db.session import collect_database_health, get_session, get_engine_for_event_loop
from config import config
from db.repository import get_active_subscription
from engine.market_state import get_market_state_async
from engine.strategies.signal_generator import SignalGenerator
from data.news import get_news_sentiment, fetch_news_headlines
import inspect
from urllib.parse import urlparse
from core.redis_state import KillSwitchState, state
from core.command_limits import (
	REQUIRE_TIER_RATE_LIMIT,
	PUBLIC_COMMAND_RATE_LIMIT,
	START_COMMAND_RATE_LIMIT,
	FREE_MIN_SCORE,
	FREE_SIGNAL_DAILY_LIMIT,
)
from .admin_commands import admin_dashboard, admin_top_assets_command
from .user_commands import start_command, status_command, account_command
from .signal_commands import signals_command, proof_command
from .account_commands import performance_command, history_command, apikey_command
from .mt5_commands import mt5_link_command, mt5_status_command
from .utils import tier_rank, _effective_tier, _public_guard
from core.tier_policy import evaluate_command_access, tier_rank as canonical_tier_rank
from core.signal_identity import signal_id_line

TIER_RANKS: dict[str, int] = {
	tier: canonical_tier_rank(tier)
	for tier in ("FREE", "PREMIUM", "VIP", "ADMIN", "OWNER")
}
FREE_PROOF_FEED_LIMIT = 5


def _railway_env_hint(feature: str, missing: list[str]) -> str:
	missing_list = ", ".join(missing)
	return (
		f"⚠️ {feature} is not configured on this deployment.\n\n"
		f"Missing env vars: {missing_list}\n\n"
		"Railway setup:\n"
		"1) Open your Railway service\n"
		"2) Go to Variables\n"
		f"3) Add {missing_list}\n"
		"4) Redeploy the service"
	)

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
				ks = type("KillSwitchFallback", (), {"enabled": False})()
			if getattr(ks, "enabled", False):
				await update.message.reply_text("🚨 Signals are temporarily paused.")
				return

			# Rate limit (20/min)
			try:
				limited: bool = state.rate_limited_sync(
					user_id,
					limit=int(REQUIRE_TIER_RATE_LIMIT["limit"]),
					window_seconds=int(REQUIRE_TIER_RATE_LIMIT["window_seconds"]),
				)
			except Exception:
				limited = False
			if limited:
				await update.message.reply_text("Rate limit exceeded. Please wait.")
				return
			tier: str = _effective_tier(user_id)
			if tier_rank(tier) < tier_rank(min_tier):
				cmd_name = func.__name__.replace("_command", "").replace("async ", "").strip()
				try:
					from .command_access import check_command_access
					cmd_name = func.__name__.replace("_command", "").replace("async ", "").strip()
					_, reason = check_command_access(cmd_name, tier)
				except Exception:
					reason: str = f"🔒 You can't access this on {str(tier).upper()} tier.\nUse /upgrade to subscribe to unlock it."
				decision = evaluate_command_access(cmd_name, tier)
				reason = decision.reason
				try:
					from services.upgrade_intents import schedule_upgrade_intent
					schedule_upgrade_intent(
						int(user_id), decision, action=cmd_name, source="telegram_command"
					)
				except Exception:
					pass
				await update.message.reply_text(reason)
				return
			result = func(update, context)
			if inspect.isawaitable(result):
				return await result
			return result
		return inner
	return wrapper


def _chart_symbol_for_broker(signal: dict | None = None) -> tuple[str, str]:
	"""Return (broker_prefix, symbol) for TradingView based on broker hints."""
	import os as _os
	asset = str((signal or {}).get("asset") or "").upper().strip()
	broker = str((signal or {}).get("broker") or (signal or {}).get("exchange") or "").upper().strip()
	default_broker = str(_os.getenv("TRADINGVIEW_BROKER", "BINANCE")).upper().strip()
	fx_prefix = str(_os.getenv("TRADINGVIEW_FX_PREFIX", "OANDA")).upper().strip() or "OANDA"
	indices_prefix = str(_os.getenv("TRADINGVIEW_INDEX_PREFIX", "TVC")).upper().strip() or "TVC"
	stock_default = str(_os.getenv("TRADINGVIEW_STOCK_PREFIX", "NASDAQ")).upper().strip() or "NASDAQ"

	# Normalize commodity aliases for TradingView symbols
	commodity_map = {
		"WTI": "USOIL",
		"BRENT": "UKOIL",
	}
	index_symbols = {"DXY", "US30", "US500", "US100", "SPX", "NDX", "DJI", "VIX"}
	stock_nasdaq = {"AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "INTC", "NFLX", "ADBE", "CRM", "ORCL", "CSCO"}
	stock_nyse = {"JPM", "BAC", "WFC", "GS", "MS", "C", "V", "MA", "JNJ", "UNH", "PFE", "ABBV", "TMO", "MRK", "ABT", "XOM", "CVX"}

	# Explicit broker map for crypto or user-provided exchange hints
	broker_map = {
		"BINANCE": "BINANCE",
		"BYBIT": "BYBIT",
		"COINBASE": "COINBASE",
		"KRAKEN": "KRAKEN",
		"BITSTAMP": "BITSTAMP",
		"OANDA": "OANDA",
		"FXCM": "FXCM",
		"FOREXCOM": "FOREXCOM",
		"TVC": "TVC",
		"NASDAQ": "NASDAQ",
		"NYSE": "NYSE",
	}

	# Crypto (BINANCE default)
	if asset.endswith("USDT") or asset.endswith("USDC"):
		broker_prefix = broker_map.get(broker, broker_map.get(default_broker, "BINANCE"))
		return broker_prefix, asset

	# FX (OANDA or FX_IDC)
	if len(asset) == 6 and asset.isalpha():
		broker_prefix = broker_map.get(broker, broker_map.get(fx_prefix, "OANDA"))
		return broker_prefix, asset

	# Commodities (XAU/XAG/OIL)
	if asset in {"XAUUSD", "XAGUSD"}:
		return "OANDA", asset
	if asset in {"WTI", "BRENT", "USOIL", "UKOIL"}:
		return "TVC", commodity_map.get(asset, asset)

	# Indices
	if asset in index_symbols:
		return indices_prefix, asset

	# Stocks (default NASDAQ/NYSE)
	if asset.isalpha() and 1 <= len(asset) <= 5:
		if asset in stock_nyse:
			return "NYSE", asset
		if asset in stock_nasdaq:
			return "NASDAQ", asset
		return stock_default, asset

	# Fallback
	return broker_map.get(default_broker, "BINANCE"), asset


def _build_dynamic_menu(user_id: int, tier: str):
	"""Build tier-aware inline menu for /start and /account."""
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		rows = []
		rows.append([
			InlineKeyboardButton("📊 Signals", callback_data="nav_signals"),
			InlineKeyboardButton("🏆 Performance", callback_data="nav_performance"),
		])
		if tier_rank(tier) < tier_rank("PREMIUM"):
			rows.append([InlineKeyboardButton("✅ Proof Feed", callback_data="nav_proof")])
			rows.append([InlineKeyboardButton("💳 Upgrade to VIP/Premium", callback_data="nav_upgrade")])
			rows.append([InlineKeyboardButton("🔒 MT5 Auto‑Trading (VIP)", callback_data="locked_mt5")])
		else:
			rows.append([
				InlineKeyboardButton("🔗 Link MT5", callback_data="mt5_link_guide"),
				InlineKeyboardButton("⚙️ MT5 Settings", callback_data="mt5_settings"),
				InlineKeyboardButton("📊 Advanced Portfolio", callback_data="advanced_portfolio"),
			])
		rows.append([
			InlineKeyboardButton("⚙️ Account", callback_data="nav_account"),
			InlineKeyboardButton("🎧 Support", callback_data="nav_support"),
		])
		rows.append([InlineKeyboardButton("Settings", callback_data="nav_settings")])
		# Admin shortcut
		try:
			if int(user_id) in ADMIN_IDS:
				rows.append([InlineKeyboardButton("🛡️ Admin Dashboard", callback_data="admin_dashboard")])
		except Exception:
			pass
		return InlineKeyboardMarkup(rows)
	except Exception:
		return None


_TELEGRAM_CALLBACK_DATA_MAX_BYTES = 64


def _compact_signal_callback_id(signal_id: object) -> str:
	raw = str(signal_id or "").strip()
	return raw[:36] if raw else ""


def _signal_callback_data(prefix: str, signal_id: object, suffix: str = "") -> str:
	payload = _compact_signal_callback_id(signal_id)
	data = f"{prefix}{payload}{suffix}"
	while payload and len(data.encode("utf-8")) > _TELEGRAM_CALLBACK_DATA_MAX_BYTES:
		payload = payload[:-1]
		data = f"{prefix}{payload}{suffix}"
	return data


def _build_signal_action_keyboard(signal: dict | None = None):
	"""Build inline buttons for /signals output (chart + trade)."""
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		broker_prefix, asset = _chart_symbol_for_broker(signal)
		_chart_symbol = asset.replace("/", "").replace(" ", "")
		chart_url = "https://www.tradingview.com/chart/"
		if _chart_symbol:
			chart_url = f"https://www.tradingview.com/chart/?symbol={broker_prefix}:{_chart_symbol}"
		signal_id = _compact_signal_callback_id((signal or {}).get("signal_id"))
		trade_cb = _signal_callback_data("mt5_trade_", signal_id) if signal_id else None
		rows = [[
			InlineKeyboardButton("📈 View Chart", url=chart_url),
		]]
		if signal_id:
			rows[0].append(InlineKeyboardButton("⚡ Trade Now", callback_data=trade_cb))
			rows.append([
				InlineKeyboardButton("🔥 Taking It", callback_data=_signal_callback_data("signal_reaction_", signal_id, "|taking_it")),
				InlineKeyboardButton("👀 Watching", callback_data=_signal_callback_data("signal_reaction_", signal_id, "|watching")),
			])
			rows.append([
				InlineKeyboardButton("📈 Monitor", callback_data=_signal_callback_data("monitor_signal_", signal_id)),
				InlineKeyboardButton("🔍 Check Outcome", callback_data=_signal_callback_data("check_outcome_", signal_id)),
			])
		keyboard = InlineKeyboardMarkup(rows)
		return keyboard
	except Exception:
		return None


async def _get_live_vip_seat_state() -> tuple[int, int, bool]:
	vip_used = 0
	try:
		from db.session import collect_database_health, get_engine_for_event_loop, get_session
		if get_engine_for_event_loop() is not None:
			from db.repository import count_active_vip_users
			async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
				vip_used = await count_active_vip_users(session, exclude_telegram_user_ids=set())
	except Exception:
		pass
	vip_limit = int(os.getenv("VIP_SEAT_LIMIT", "0") or 0)
	if vip_limit <= 0:
		return vip_used, -1, False
	vip_seats_left = max(0, vip_limit - int(vip_used))
	return vip_used, vip_seats_left, vip_seats_left <= 0


def _vip_plan_line(*, MarkdownV2: bool, seats_left: int, sold_out: bool) -> str:
	vip_price = int(os.getenv("VIP_MONTHLY_PRICE_NGN", os.getenv("VIP_PRICE_NGN", "40000")))
	price = f"₦{vip_price:,}"
	if sold_out:
		return f"💎 VIP Monthly — {price} \\| 🔴 VIP Sold Out" if MarkdownV2 else f"💎 VIP Monthly — {price} | 🔴 VIP Sold Out"
	if seats_left < 0:
		return f"💎 VIP Monthly — {price} \\| 🟢 Open enrollment" if MarkdownV2 else f"💎 VIP Monthly — {price} | 🟢 Open enrollment"
	if MarkdownV2:
		return f"💎 VIP Monthly — {price} \\| 🟢 {seats_left} seats left"
	return f"💎 VIP Monthly — {price} | 🟢 {seats_left} seats left"


def is_valid_paystack_checkout_url(url: str | None) -> bool:
	if not url:
		return False
	parsed = urlparse(str(url))
	return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


async def _build_plan_keyboard(user_id: int, *, include_navigation: bool) -> object | None:
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		from paystack.paystack import generate_paystack_link

		def _checkout_button(label: str, *, price: int, tier: str, duration: str, duration_days: int) -> InlineKeyboardButton:
			link = generate_paystack_link(
				user_id=user_id,
				price=price,
				tier=tier,
				duration=duration,
				duration_days=duration_days,
			)
			if is_valid_paystack_checkout_url(link):
				return InlineKeyboardButton(label, url=link)
			return InlineKeyboardButton(label, callback_data="payment_unavailable")

		_, vip_seats_left, vip_sold_out = await _get_live_vip_seat_state()
		rows = []
		if vip_sold_out:
			rows.append([InlineKeyboardButton("💎 VIP Sold Out", callback_data="vip_sold_out")])
			rows.append([InlineKeyboardButton("📋 Join VIP Waitlist", callback_data="vip_waitlist_join")])
		else:
			vip_price = int(os.getenv("VIP_MONTHLY_PRICE_NGN", os.getenv("VIP_PRICE_NGN", "40000")))
			seat_label = "Open enrollment" if vip_seats_left < 0 else f"{vip_seats_left} left"
			rows.append([
				_checkout_button(
					f"💎 VIP Monthly — ₦{vip_price:,} ({seat_label})",
					price=vip_price,
					tier="VIP",
					duration="MONTHLY",
					duration_days=30,
				),
			])
		prem_month_price = int(os.getenv("PREMIUM_MONTHLY_PRICE_NGN", "24000"))
		prem_qtr_price = int(os.getenv("PREMIUM_QUARTERLY_PRICE_NGN", "56000"))
		prem_year_price = int(os.getenv("PREMIUM_YEARLY_PRICE_NGN", "192000"))
		rows.append([
			_checkout_button(
				f"⭐ Premium Monthly — ₦{prem_month_price:,}",
				price=prem_month_price,
				tier="PREMIUM",
				duration="MONTHLY",
				duration_days=30,
			),
		])
		rows.append([
			_checkout_button(
				f"⭐ Premium Quarterly — ₦{prem_qtr_price:,}",
				price=prem_qtr_price,
				tier="PREMIUM",
				duration="QUARTERLY",
				duration_days=90,
			),
		])
		rows.append([
			_checkout_button(
				f"🔥 Premium Yearly (Best Value) — ₦{prem_year_price:,}",
				price=prem_year_price,
				tier="PREMIUM",
				duration="YEARLY",
				duration_days=365,
			),
		])
		rows.append([InlineKeyboardButton("📞 Support: @theocrilox", url="https://t.me/theocrilox")])
		if include_navigation:
			rows.append([
				InlineKeyboardButton("📈 Signals", callback_data="nav_signals"),
				InlineKeyboardButton("👤 Account", callback_data="nav_account"),
			])
		return InlineKeyboardMarkup(rows)
	except Exception:
		return None


async def _compose_pricing_message(user_id: int) -> tuple[str, object | None]:
	from core.tier_policy import get_entitlements

	_, vip_seats_left, vip_sold_out = await _get_live_vip_seat_state()
	vip_line = _vip_plan_line(MarkdownV2=False, seats_left=vip_seats_left, sold_out=vip_sold_out)
	prem_month_price = int(os.getenv("PREMIUM_MONTHLY_PRICE_NGN", "24000"))
	prem_qtr_price = int(os.getenv("PREMIUM_QUARTERLY_PRICE_NGN", "56000"))
	prem_year_price = int(os.getenv("PREMIUM_YEARLY_PRICE_NGN", "192000"))
	free_limit = get_entitlements("FREE").daily_signal_limit
	premium_limit = get_entitlements("PREMIUM").daily_signal_limit
	vip_limit = get_entitlements("VIP").daily_signal_limit
	msg = (
		"🚀 SignalRankAI — Plans Built Around Trader Value\n\n"
		"🆓 Free — proof feed + limited educational signals\n"
		f"• Up to {free_limit}/day, delayed/limited detail, upgrade prompts\n\n"
		f"⭐ Premium — ₦{prem_month_price:,}/mo · ₦{prem_qtr_price:,}/qtr · ₦{prem_year_price:,}/yr\n"
		f"• Up to {premium_limit}/day, real-time Entry/SL/TP, /signals, /outcome, performance stats, multi-asset coverage\n\n"
		f"{vip_line}\n"
		f"• Up to {vip_limit}/day, stricter high-conviction stream, priority delivery, TP3 runner, webhook/API, MT5-ready controls, advanced profile filters\n\n"
		"Why upgrade? Paid tiers get cleaner timing, deeper signal context, more markets, tracked outcomes, and priority delivery.\n\n"
		"⚠️ Educational only. Trading involves risk. No guaranteed returns."
	)
	keyboard = await _build_plan_keyboard(int(user_id), include_navigation=False)
	return msg, keyboard


async def _compose_upgrade_message(user_id: int) -> tuple[str, object | None]:
	_, vip_seats_left, vip_sold_out = await _get_live_vip_seat_state()
	vip_line = _vip_plan_line(MarkdownV2=False, seats_left=vip_seats_left, sold_out=vip_sold_out)
	prem_month_price = int(os.getenv("PREMIUM_MONTHLY_PRICE_NGN", "24000"))
	prem_qtr_price = int(os.getenv("PREMIUM_QUARTERLY_PRICE_NGN", "56000"))
	prem_year_price = int(os.getenv("PREMIUM_YEARLY_PRICE_NGN", "192000"))
	msg = (
		"🚀 <b>Upgrade SignalRankAI</b>\n\n"
		"The free tier proves the system. Paid tiers are for traders who want cleaner timing, more context, and better workflow.\n\n"
		f"⭐ <b>Premium</b> — ₦{prem_month_price:,}/mo · ₦{prem_qtr_price:,}/qtr · ₦{prem_year_price:,}/yr\n"
		"• More daily real-time signals\n"
		"• Full Entry / Stop Loss / TP levels\n"
		"• /signals, /outcome, /performance, portfolio-style recap\n"
		"• Multi-asset feed: crypto, FX, stocks, commodities\n\n"
		f"{vip_line}\n"
		"• Priority delivery when the engine finds a setup\n"
		"• Stricter quality stream and TP3 runner\n"
		"• Webhook/API and MT5-ready controls\n"
		"• Advanced profile filters: scalp, day, swing, position\n\n"
		"Best practice: start Premium, upgrade to VIP when you need faster workflow and automation-grade alerts.\n\n"
		"⚠️ <i>No guaranteed profits. Educational only. Trade responsibly.</i>\n\n"
		"Tap a plan below to open checkout, or use Support if a payment link is unavailable."
	)
	keyboard = await _build_plan_keyboard(int(user_id), include_navigation=True)
	return msg, keyboard


def _build_main_menu_keyboard(user_id: int):
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		rows = [
			[
				InlineKeyboardButton("📊 Signals", callback_data="nav_signals"),
				InlineKeyboardButton("🏆 Performance", callback_data="nav_performance"),
			],
			[
				InlineKeyboardButton("⚙️ Account", callback_data="nav_account"),
				InlineKeyboardButton("💳 Upgrade", callback_data="nav_upgrade"),
			],
			[
				InlineKeyboardButton("🎧 Support", callback_data="nav_support"),
			],
		]
		try:
			if int(user_id) in ADMIN_IDS:
				rows.append([InlineKeyboardButton("🛡️ Admin Dashboard", callback_data="admin_dashboard")])
		except Exception:
			pass
		return InlineKeyboardMarkup(rows)
	except Exception:
		return None


async def _compose_main_menu_message(user_id: int) -> tuple[str, object | None]:
	msg = (
		"👋 Welcome to SignalRankAI.\n"
		"Pick a category below to continue."
	)
	return msg, _build_main_menu_keyboard(int(user_id))


def _build_section_back_keyboard(*, include_upgrade: bool = True):
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		rows = [
			[
				InlineKeyboardButton("⚙️ Account", callback_data="nav_account"),
				InlineKeyboardButton("🎧 Support", callback_data="nav_support"),
			],
		]
		if include_upgrade:
			rows.insert(0, [
				InlineKeyboardButton("💳 Upgrade", callback_data="nav_upgrade"),
				InlineKeyboardButton("🏠 Back to Main Menu", callback_data="nav_home"),
			])
		else:
			rows.insert(0, [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="nav_home")])
		return InlineKeyboardMarkup(rows)
	except Exception:
		return None


async def _compose_signals_menu_message(user_id: int) -> tuple[str, object | None]:
	tier = _effective_tier(int(user_id))
	msg = (
		"📊 Signals Menu\n\n"
		"• Use /signals to view the latest active trade setups\n"
		"• Track live opportunities across crypto, forex, stocks, and commodities\n"
		"• Premium and VIP users receive deeper signal detail and broader coverage\n\n"
		f"Your current tier: {tier}\n"
		"Tip: send /signals anytime to pull the latest signal feed."
	)
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		keyboard = InlineKeyboardMarkup([
			[
				InlineKeyboardButton("🏆 Performance", callback_data="nav_performance"),
				InlineKeyboardButton("💳 Upgrade", callback_data="nav_upgrade"),
			],
			[
				InlineKeyboardButton("⚙️ Account", callback_data="nav_account"),
				InlineKeyboardButton("🎧 Support", callback_data="nav_support"),
			],
			[
				InlineKeyboardButton("🏠 Back to Main Menu", callback_data="nav_home"),
			],
		])
	except Exception:
		keyboard = None
	return msg, keyboard


async def _compose_performance_menu_message(user_id: int) -> tuple[str, object | None]:
	tier = _effective_tier(int(user_id))
	if tier_rank(tier) < tier_rank("PREMIUM"):
		msg = (
			"🏆 Performance Menu\n\n"
			"Detailed performance analytics are available on Premium and VIP plans.\n"
			"Upgrade to unlock 30-day stats, tracked outcomes, and win-rate reporting.\n\n"
			"You can still use /upgrade to unlock analytics instantly."
		)
	else:
		msg = (
			"🏆 Performance Menu\n\n"
			"• Use /performance for your 30-day delivery and outcome summary\n"
			"• Review tracked wins, losses, win rate, and net R performance\n"
			"• Pair this with /portfolio and /dashboard for a broader view\n\n"
			f"Your current tier: {tier}"
		)
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		keyboard = InlineKeyboardMarkup([
			[
				InlineKeyboardButton("📊 Signals", callback_data="nav_signals"),
				InlineKeyboardButton("⚙️ Account", callback_data="nav_account"),
			],
			[
				InlineKeyboardButton("💳 Upgrade", callback_data="nav_upgrade"),
				InlineKeyboardButton("🎧 Support", callback_data="nav_support"),
			],
			[
				InlineKeyboardButton("🏠 Back to Main Menu", callback_data="nav_home"),
			],
		])
	except Exception:
		keyboard = None
	return msg, keyboard


async def _compose_support_menu_message(user_id: int) -> tuple[str, object | None]:
	_ = user_id
	msg = (
		"🎧 Support Menu\n\n"
		"Need help with billing, subscriptions, bot access, or trade delivery?\n\n"
		"Support contact: @theocrilox\n"
		"Helpful commands:\n"
		"• /faq\n"
		"• /policy\n"
		"• /refunds"
	)
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		keyboard = InlineKeyboardMarkup([
			[
				InlineKeyboardButton("💬 Contact Support", url="https://t.me/theocrilox"),
			],
			[
				InlineKeyboardButton("⚙️ Account", callback_data="nav_account"),
				InlineKeyboardButton("💳 Upgrade", callback_data="nav_upgrade"),
			],
			[
				InlineKeyboardButton("🏠 Back to Main Menu", callback_data="nav_home"),
			],
		])
	except Exception:
		keyboard = None
	return msg, keyboard


async def button_click_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Handle inline button callbacks from /help and /signals."""
	query = update.callback_query
	if query is None:
		return
	try:
		logger.info("[button_click] data=%s user_id=%s", query.data, getattr(update.effective_user, "id", None))
		print(f"[button_click] data={query.data} user_id={getattr(update.effective_user, 'id', None)}", flush=True)
	except Exception:
		pass
	try:
		await query.answer()
	except Exception:
		pass
	data = str(query.data or "")
	if data == "nav_settings":
		from types import SimpleNamespace
		proxy_update = SimpleNamespace(effective_user=update.effective_user, message=query.message)
		await settings_command(proxy_update, context)
		return
	if data == "nav_timezone" or data.startswith("timezone_"):
		if await handle_timezone_callback(update, context):
			return
	if data.startswith("trade_now_"):
		try:
			signal_id = str(data.replace("trade_now_", "", 1) or "").strip()[:36]
			if signal_id:
				from telegram import InlineKeyboardMarkup, InlineKeyboardButton
				new_kbd = InlineKeyboardMarkup([
					[InlineKeyboardButton("⚡ Trade Now", callback_data=_signal_callback_data("mt5_trade_", signal_id))],
					[
						InlineKeyboardButton("📈 Monitor", callback_data=_signal_callback_data("monitor_signal_", signal_id)),
						InlineKeyboardButton("🔍 Check Outcome", callback_data=_signal_callback_data("check_outcome_", signal_id)),
					],
				])
				await query.edit_message_reply_markup(reply_markup=new_kbd)
				await query.answer("Buttons updated. Tap ⚡ Trade Now again.", show_alert=False)
				return
		except Exception:
			pass
		try:
			await query.answer("This button is outdated. Send /signals to refresh.", show_alert=True)
		except Exception:
			pass
		return
	# Help navigation
	if data == "nav_home":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_main_menu_message(int(uid))
			await query.edit_message_text(text=msg, reply_markup=keyboard)
			return
		except Exception as _e:
			logger.exception("[button_click] nav_home failed: %s", _e)
			try:
				await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)
			except Exception:
				pass
			return
	if data == "nav_signals":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_signals_menu_message(int(uid))
			await query.edit_message_text(text=msg, reply_markup=keyboard)
			return
		except Exception as _e:
			logger.exception("[button_click] nav_signals failed: %s", _e)
			try:
				await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)
			except Exception:
				pass
			return
	if data == "nav_proof":
		try:
			if update.effective_user is None:
				return
			from types import SimpleNamespace
			proxy_update = SimpleNamespace(
				effective_user=update.effective_user,
				message=query.message,
			)
			await proof_command(proxy_update, context)
			return
		except Exception as _e:
			logger.exception("[button_click] nav_proof failed: %s", _e)
			try:
				await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)
			except Exception:
				pass
			return
	if data == "nav_account":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_status_message(int(uid))
			await _edit_message_or_reply(query, msg, keyboard)
			return
		except Exception as _e:
			logger.exception("[button_click] nav_account failed: %s", _e)
			try:
				await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)
			except Exception:
				pass
			return
	if data == "nav_performance":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_performance_menu_message(int(uid))
			await query.edit_message_text(text=msg, reply_markup=keyboard)
			return
		except Exception as _e:
			logger.exception("[button_click] nav_performance failed: %s", _e)
			try:
				await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)
			except Exception:
				pass
			return
	if data == "nav_execution":
		try:
			await execution_command(update, context)
			return
		except Exception as _e:
			logger.exception("[button_click] nav_execution failed: %s", _e)
			try:
				await query.answer("Something went wrong. Please try again.", show_alert=True)
			except Exception:
				pass
			return
	if data == "nav_upgrade":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_upgrade_message(int(uid))
			await _edit_message_or_reply(query, msg, keyboard)
			return
		except Exception as _e:
			logger.exception("[button_click] nav_upgrade failed: %s", _e)
			try:
				await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)
			except Exception:
				pass
			return
	if data == "nav_support":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_support_menu_message(int(uid))
			await query.edit_message_text(text=msg, reply_markup=keyboard)
			return
		except Exception as _e:
			logger.exception("[button_click] nav_support failed: %s", _e)
			try:
				await query.answer("⚠️ Something went wrong. Please try again.", show_alert=True)
			except Exception:
				pass
			return
	if data == "payment_unavailable":
		try:
			await query.answer(
				"Checkout is temporarily unavailable in this environment. Use Support if you need a payment link.",
				show_alert=True,
			)
		except Exception:
			pass
		return
	if data == "vip_sold_out":
		try:
			await query.answer("VIP is currently sold out. Join the waitlist to be notified.", show_alert=True)
		except Exception:
			pass
		return
	# Admin dashboard shortcut
	if data == "admin_dashboard":
		return await admin_dashboard(update, context)
	# Locked feature upsell
	if data.startswith("locked_"):
		try:
			await query.answer(
				"⭐ This feature requires Premium or VIP. Type /upgrade to unlock!",
				show_alert=True,
			)
		except Exception:
			pass
		return
	# Protect VIP callbacks
	if data in {"mt5_settings", "advanced_portfolio"}:
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			tier = _effective_tier(int(uid))
			if tier_rank(tier) < tier_rank("PREMIUM"):
				await query.answer(
					"⭐ This feature requires Premium or VIP. Type /upgrade to unlock!",
					show_alert=True,
				)
				return
			from telegram import InlineKeyboardMarkup, InlineKeyboardButton
			if data == "mt5_settings":
				msg = (
					"⚙️ MT5 Settings\n\n"
					"Use these commands:\n"
					"• /mt5_status — connection status\n"
					"• /setlot — fixed lot size\n"
					"• /setrisk — max risk %\n"
					"• /mt5_link — link your MT5 account"
				)
			else:
				msg = (
					"📊 Advanced Portfolio\n\n"
					"Use these commands:\n"
					"• /portfolio — active signals P&L\n"
					"• /risk — risk guidance\n"
					"• /alerts — TP/SL alerts\n"
					"• /performance — stats summary"
				)
			keyboard = InlineKeyboardMarkup([
				[InlineKeyboardButton("⬅️ Back", callback_data="nav_account")]
			])
			await _edit_message_or_reply(query, msg, keyboard)
			return
		except Exception:
			return
	if data == "mt5_link_guide":
		try:
			await query.message.reply_text(
				"To connect your MT5 account for auto-trading, use one of these:\n\n"
				"1) Guided setup: /connect_broker\n"
				"2) Direct command: /mt5_link <Account Number> <Password> <Server Name>\n\n"
				"Example: /mt5_link 12345678 MyPass123 Exness-MT5-Real"
			)
			return
		except Exception:
			return
	# Admin callbacks
	if data.startswith("admin_"):
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None or int(uid) not in ADMIN_IDS:
				await query.answer("⛔ Access Denied", show_alert=True)
				return
			if data == "admin_broadcast":
				await query.message.reply_text("📢 Broadcast mode: use /admin_broadcast <message>.")
				return
			if data == "admin_user_stats":
				await query.message.reply_text("👥 User stats: use /admin or /admin_user_engagement.")
				return
			if data == "admin_revenue":
				await query.message.reply_text("💸 Revenue analytics: use /owner_revenue.")
				return
			if data == "admin_force_signal":
				try:
					from signalrank_telegram.owner_commands import dev_force_signal, _is_admin_or_owner
					
					uid = update.effective_user.id if update.effective_user else None
					if uid is None or not await _is_admin_or_owner(uid):
						await query.answer("⛔ Access Denied.", show_alert=True)
						return
					
					# Call the signal generation function directly
					context.args = []
					await dev_force_signal(update, context)
				except Exception:
					await query.answer("Failed to generate signal. Try /force_signal instead.", show_alert=True)
				return
			if data == "admin_toggle_engine":
				await query.message.reply_text("🛑 Engine: use /dev_pause or /dev_resume.")
				return
			if data == "admin_force_market_scan":
				await query.message.reply_text("🧠 Market scan: use /force_market_scan.")
				return
		except Exception:
			return
	# Trade button
	if data.startswith("trade_now"):
		try:
			from telegram import InlineKeyboardMarkup, InlineKeyboardButton
			raw = str(data or "")
			signal_id = ""
			if raw.startswith("trade_now_"):
				signal_id = raw.replace("trade_now_", "", 1)[:36]
			if signal_id:
				await query.message.reply_text(
					"⚡ Updated action button:",
					reply_markup=InlineKeyboardMarkup([
						[InlineKeyboardButton("⚡ Take Trade", callback_data=_signal_callback_data("mt5_trade_", signal_id))]
					]),
				)
				return
			await query.message.reply_text("⚡ Please open /signals and use the latest Trade button.")
			return
		except Exception:
			return


async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Admin dashboard with secure button menu (ADMIN_IDS only)."""
	if update.effective_user is None:
		return
	if int(update.effective_user.id) not in ADMIN_IDS:
		return
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		keyboard = InlineKeyboardMarkup([
			[
				InlineKeyboardButton("📢 Broadcast to All", callback_data="admin_broadcast"),
				InlineKeyboardButton("👥 User Stats", callback_data="admin_user_stats"),
			],
			[
				InlineKeyboardButton("💸 Revenue Analytics", callback_data="admin_revenue"),
				InlineKeyboardButton("⚡ Force Signal", callback_data="admin_force_signal"),
			],
			[
				InlineKeyboardButton("🛑 Pause/Resume Engine", callback_data="admin_toggle_engine"),
				InlineKeyboardButton("🧠 Force Market Scan", callback_data="admin_force_market_scan"),
			],
		])
	except Exception:
		keyboard = None
	if update.message is None and getattr(update, "callback_query", None) is not None:
		try:
			update.message = update.callback_query.message
		except Exception:
			pass
	if update.message is None:
		return
	await update.message.reply_text("🛡️ Admin Dashboard", reply_markup=keyboard)


@require_tier("ADMIN")
async def force_market_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	if int(update.effective_user.id) not in ADMIN_IDS:
		return

	try:
		from ml.inference import MLFilter
		from ml.features import extract_features
	except Exception:
		await update.message.reply_text("⚠️ ML module not available. Scan skipped.")
		return

	ml_filter = MLFilter()
	if not getattr(ml_filter, "active", False):
		await update.message.reply_text("⚠️ ML model not loaded — train first.")
		return

	threshold_raw = str(os.getenv("ML_PROB_THRESHOLD") or "").strip()
	threshold = float(threshold_raw) if threshold_raw else None
	await update.message.reply_text("Market scan started. I will post the result when the scan completes.")

	try:
		from db.session import get_session
		from db.models import Signal, AdminEvent
		from sqlalchemy import select
		from datetime import datetime, timedelta
		cutoff = now_utc_naive() - timedelta(hours=4)
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			rows = await session.execute(
				select(Signal)
				.where(
					Signal.created_at >= cutoff,
					Signal.ml_probability.is_(None),
					Signal.expired.is_(False),
				)
				.limit(50)
			)
			signals = rows.scalars().all()

		approved = rejected = errors = 0
		for sig_row in signals:
			try:
				sig_dict = {col.name: getattr(sig_row, col.name) for col in sig_row.__table__.columns}
				features = extract_features(sig_dict, {})
				ok, _prob = ml_filter.ml_filter(features, threshold=threshold)
				if ok:
					approved += 1
				else:
					rejected += 1
			except Exception:
				errors += 1

		try:
			async with get_session() as event_session:
				event_session.add(
					AdminEvent(
						event_type="force_market_scan",
						actor_telegram_user_id=int(update.effective_user.id),
						details={
							"total": len(signals),
							"approved": approved,
							"rejected": rejected,
							"errors": errors,
							"threshold": threshold,
						},
					)
				)
				await event_session.commit()
		except Exception as event_exc:
			logger.debug("[force_market_scan] admin event write failed: %s", event_exc)

	except Exception:
		await update.message.reply_text("⚠️ Scan failed. Check logs for details.")
		return

	threshold_label = f"{threshold:.2f}" if threshold is not None else "auto"
	await update.message.reply_text(
		f"🤖 Market scan complete. Signals={len(signals)} | "
		f"approved={approved} | rejected={rejected} | errors={errors} | "
		f"threshold={threshold_label}"
	)
# --- USER COMMAND: /support ---
async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	support_contact = "@theocrilox"
	await update.message.reply_text(f"For help or questions, contact support: {support_contact}")
# --- USER COMMAND: /status ---
async def _compose_status_message(user_id: int) -> tuple[str, object | None]:
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
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			user = await get_or_create_user(session, telegram_user_id=user_id)
			expiry = getattr(user, 'premium_until', None)
			if expiry is None:
				# Fall back to active subscription expiry
				now_dt = now_utc_naive()
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
		date_str = now_utc_naive().strftime('%Y-%m-%d')
		signals_today = int(state.get_sync(f"signals_sent:{user_id}:{date_str}") or 0)
	except Exception:
		pass

	limits = {"free": 3, "premium": 20, "vip": "∞", "owner": "∞", "admin": "∞"}
	limit = limits.get(tier, 3)

	tier_emoji = {"free": "🆓", "premium": "⭐", "vip": "👑", "owner": "🔧", "admin": "🔧"}.get(tier, "🆓")

	msg = f"{tier_emoji} Status: {tier.upper()}\n\n"
	if expiry:
		msg += f"📅 Expires: {expiry.strftime('%Y-%m-%d %H:%M UTC')}\n"
	msg += f"📊 Signals today: {signals_today}/{limit}\n"

	if tier == "free":
		msg += "\n/upgrade to unlock more signals"

	keyboard = _build_dynamic_menu(user_id=int(user_id), tier=tier)
	return msg, keyboard


async def _edit_message_or_reply(query, msg: str, keyboard=None) -> None:
	try:
		await query.edit_message_text(msg, reply_markup=keyboard)
		return
	except Exception:
		pass
	try:
		if query and query.message is not None:
			await query.message.reply_text(msg, reply_markup=keyboard)
	except Exception:
		pass


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None:
		return
	if update.message is None and getattr(update, "callback_query", None) is not None:
		try:
			update.message = update.callback_query.message
		except Exception:
			pass
	if update.message is None:
		return
	user_id = update.effective_user.id
	msg, keyboard = await _compose_status_message(int(user_id))
	await update.message.reply_text(msg, reply_markup=keyboard)


async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Alias for /status with dynamic tier menu."""
	return await status_command(update, context)

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web')))
try:
	from web.api import generate_api_key
except Exception:
	generate_api_key = lambda: "demo-key"


async def _rotate_api_token_for_user(user_id: int, ttl_days: int = 30) -> str:
	from datetime import datetime, timedelta
	from db.session import get_session
	from db.repository import create_api_token
	token = generate_api_key()
	expires = now_utc_naive() + timedelta(days=max(1, min(int(ttl_days), 365)))
	async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
		await create_api_token(
			session,
			telegram_user_id=int(user_id),
			raw_token=str(token),
			scope="signals:read",
			expires_at=expires,
		)
		await session.commit()
	return str(token)


async def _get_existing_api_token_meta(user_id: int):
	from db.session import get_session
	from db.repository import get_latest_active_api_token_meta
	async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
		meta = await get_latest_active_api_token_meta(session, telegram_user_id=int(user_id))
		await session.commit()
	return meta

@require_tier("PREMIUM")
async def apikey_command(update, context) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	args = context.args or []
	if args and args[0].lower() == "regenerate":
		key = await _rotate_api_token_for_user(int(user_id), ttl_days=30)
		await update.message.reply_text(f"🔑 Your new API key: {key}\nKeep it secret. Use it with the /signals API endpoint.")
		return
	meta = await _get_existing_api_token_meta(int(user_id))
	if meta is None:
		key = await _rotate_api_token_for_user(int(user_id), ttl_days=30)
		await update.message.reply_text(f"🔑 Your API key: {key}\nUse it with the /signals API endpoint. Send /apikey regenerate to rotate.")
		return
	prefix = str(meta.get("token_prefix") or "")
	exp = str(meta.get("expires_at") or "unknown")
	await update.message.reply_text(
		f"🔑 Active API key exists.\n"
		f"Prefix: <code>{prefix}</code>\n"
		f"Expires: <code>{exp}</code>\n\n"
		f"Use /apikey regenerate to rotate and receive a new full key.",
		parse_mode="HTML",
	)
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
async def db_health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Admin-only database pool and Postgres activity diagnostics."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	try:
		from db.session import collect_database_health

		health = await collect_database_health()
		pool = dict(health.get("pool") or {})
		pg = dict(health.get("postgres") or {})
		activity = dict(pg.get("activity_by_state") or {})
		session_metrics = dict(pool.get("session_metrics") or {})
		schema_status = {}
		try:
			from sqlalchemy import text
			async with get_session(priority="interactive", label="signalrank_telegram_commands") as schema_session:
				revision = (await schema_session.execute(
					text("SELECT version_num FROM alembic_version LIMIT 1")
				)).scalar_one_or_none()
				tables = (await schema_session.execute(text("""
					SELECT
					  to_regclass('public.signal_lifecycles') IS NOT NULL,
					  to_regclass('public.signal_tracking_events') IS NOT NULL,
					  to_regclass('public.signal_event_notifications') IS NOT NULL
				"""))).one()
				schema_status = {
					"revision": revision,
					"signal_lifecycles": bool(tables[0]),
					"signal_tracking_events": bool(tables[1]),
					"signal_event_notifications": bool(tables[2]),
				}
		except Exception as schema_error:
			schema_status = {"error": type(schema_error).__name__}
		lines = [
			"Database Health",
			"",
			f"Configured: {bool(pool.get('configured'))}",
			f"Engine ready: {bool(pool.get('engine_ready'))}",
			f"Railway runtime: {bool(pool.get('railway_runtime'))}",
			f"Engines: {int(pool.get('engine_count') or 0)}",
			f"Pool: size={pool.get('size', pool.get('effective_pool_size'))} checked_out={pool.get('checkedout', 'n/a')} overflow={pool.get('overflow', 'n/a')}",
			f"Effective cap: pool={pool.get('effective_pool_size')} overflow={pool.get('effective_max_overflow')}",
			f"Session gate: limit={pool.get('session_limit')} active={session_metrics.get('active', 0)} waiting={session_metrics.get('waiting', 0)} errors={session_metrics.get('errors', 0)}",
			f"Interactive: active={session_metrics.get('interactive_active', 0)} waiting={session_metrics.get('interactive_waiting', 0)}",
			f"Background gate: limit={pool.get('background_session_limit')} active={session_metrics.get('background_active', 0)} waiting={session_metrics.get('background_waiting', 0)} dropped={session_metrics.get('background_dropped', 0)}",
			f"Sessions: opened={session_metrics.get('opened', 0)} closed={session_metrics.get('closed', 0)} noncritical_dropped={session_metrics.get('noncritical_dropped', 0)}",
			f"Alembic head: {schema_status.get('revision', 'unavailable')}",
			f"Lifecycle tables: state={schema_status.get('signal_lifecycles', False)} events={schema_status.get('signal_tracking_events', False)} notifications={schema_status.get('signal_event_notifications', False)}",
		]
		if pg.get("max_connections"):
			lines.append(f"Postgres max_connections: {pg.get('max_connections')}")
		if activity:
			lines.append("Activity:")
			for state_name, count in sorted(activity.items()):
				lines.append(f"- {state_name}: {count}")
		if pg.get("error"):
			lines.append(f"Postgres activity error: {pg.get('error')}")
		await update.message.reply_text("\n".join(lines))
	except Exception as exc:
		await update.message.reply_text(f"Database health unavailable. Reference logged: {type(exc).__name__}")


async def delivery_debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Owner/admin proof trail for a signal delivery and Telegram acknowledgement."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	args = [str(x or "").strip() for x in (context.args or []) if str(x or "").strip()]
	if not args:
		await update.message.reply_text("Usage: /delivery_debug <signal_ref> [telegram_user_id]")
		return
	ref = args[0]
	user_filter = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

	try:
		from sqlalchemy import select
		from db.models import (
			Outcome,
			Signal,
			SignalDelivery,
			SignalEventNotification,
			SignalTrackingEvent,
			User,
		)
		from db.session import get_session
		from db.signal_reference import resolve_signal_reference

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			resolved = await resolve_signal_reference(session, ref)
			signal_uuid = str(resolved.signal.signal_id)
			query = (
				select(SignalDelivery, User, Signal, Outcome)
				.join(User, User.id == SignalDelivery.user_id)
				.join(Signal, Signal.signal_id == SignalDelivery.signal_id)
				.outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
				.where(Signal.signal_id == signal_uuid)
				.order_by(SignalDelivery.id.desc())
				.limit(20)
			)
			if user_filter is not None:
				query = query.where(User.telegram_user_id == int(user_filter))
			rows = (await session.execute(query)).all()
			event_query = (
				select(SignalEventNotification, SignalTrackingEvent)
				.join(
					SignalTrackingEvent,
					SignalTrackingEvent.id == SignalEventNotification.event_id,
				)
				.where(SignalEventNotification.signal_id == signal_uuid)
				.order_by(SignalTrackingEvent.event_time.desc(), SignalEventNotification.id.desc())
				.limit(50)
			)
			if user_filter is not None:
				event_query = event_query.where(
					SignalEventNotification.telegram_user_id == int(user_filter)
				)
			event_rows = (await session.execute(event_query)).all()
			await session.commit()

		if not rows:
			await update.message.reply_text("No delivery rows match that signal reference and user.")
			return

		latest_event_by_user = {}
		for notification, event in event_rows:
			latest_event_by_user.setdefault(int(notification.telegram_user_id), (notification, event))

		for delivery, user, signal, outcome in rows:
			proof_ok = bool(delivery.telegram_chat_id is not None and delivery.telegram_message_id is not None)
			from signalrank_telegram.timezones import effective_user_timezone, format_user_datetime
			display_tz = getattr(delivery, "display_timezone", None) or effective_user_timezone(
				getattr(user, "timezone", None), user.telegram_user_id
			)
			generated_display = getattr(delivery, "display_generated_at", None) or format_user_datetime(
				signal.created_at, display_tz, user.telegram_user_id
			)
			delivered_display = getattr(delivery, "display_delivered_at", None) or format_user_datetime(
				delivery.delivered_at, display_tz, user.telegram_user_id
			)
			latest_event = latest_event_by_user.get(int(user.telegram_user_id))
			if latest_event:
				notification, event = latest_event
				event_proof = (
					f"\nLifecycle: {event.event_type} at {event.event_time}\n"
					f"Lifecycle notification: state={notification.delivery_state} "
					f"sent_ok={bool(notification.sent_ok)} message={notification.sent_message_id or 'none'}\n"
					f"Lifecycle error: {notification.error or 'none'}"
				)
			else:
				event_proof = "\nLifecycle: no persisted event notification yet"
			message = (
				"Delivery proof\n"
				f"{signal_id_line(signal)}\n"
				f"Market: {signal.asset} {signal.timeframe} {str(signal.direction).upper()}\n"
				f"User: {user.telegram_user_id}\n"
				f"State: {delivery.delivery_state} | sent_ok={bool(delivery.sent_ok)} | proof={proof_ok}\n"
				f"Telegram: chat={delivery.telegram_chat_id or 'none'} message={delivery.telegram_message_id or 'none'}\n"
				f"Attempts: {int(delivery.attempt_count or 0)}\n"
				f"Dispatch: {delivery.dispatch_started_at or 'none'}\n"
				f"Confirmed: {delivery.delivery_confirmed_at or 'none'}\n"
				f"Generated ({display_tz}): {generated_display}\n"
				f"Delivered ({display_tz}): {delivered_display}\n"
				f"Age at delivery: {getattr(delivery, 'signal_age_at_delivery_seconds', None) or 'n/a'}s\n"
				f"Error: {delivery.last_error or 'none'}\n"
				f"Outcome: {getattr(outcome, 'status', None) or 'pending'}"
				f"{event_proof}"
			)
			await update.message.reply_text(message[:3900])
	except Exception as exc:
		logger.exception("[delivery_debug] failed: %s", exc)
		await update.message.reply_text(f"Delivery debug failed: {type(exc).__name__}")


async def _load_signal_debug_payload(ref: str) -> dict | None:
	from db.session import get_session
	from db.signal_reference import SignalReferenceError, resolve_signal_reference

	async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
		try:
			row = (await resolve_signal_reference(session, ref)).signal
		except SignalReferenceError:
			return None
		await session.commit()
	return {column.key: getattr(row, column.key, None) for column in row.__table__.columns}

async def signal_debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Owner/admin inspection of the DB fields needed for signal rendering."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	args = [str(value or "").strip() for value in (context.args or []) if str(value or "").strip()]
	if not args:
		await update.message.reply_text("Usage: /signal_debug <signal_ref>")
		return
	try:
		payload = await _load_signal_debug_payload(args[0])
		if payload is None:
			await update.message.reply_text("No signal matches that reference.")
			return
		from signalrank_telegram.formatter import signal_format_diagnostics
		diagnostics = signal_format_diagnostics(payload)
		fields = diagnostics["fields"]
		lines = [
			"Signal Debug",
			signal_id_line(payload),
			f"Missing required: {', '.join(diagnostics['missing_required']) or 'none'}",
			f"Fallback renderable: {bool(diagnostics['can_render_fallback'])}",
		]
		for key in ("asset", "direction", "timeframe", "entry", "stop_loss", "tp1", "score", "status", "lifecycle_state", "reason", "ai_reason"):
			lines.append(f"{key}: {fields.get(key) if fields.get(key) not in (None, '') else 'MISSING'}")
		await update.message.reply_text("\n".join(lines)[:3900])
	except Exception as exc:
		logger.exception("[signal_debug] failed: %s", exc)
		await update.message.reply_text(f"Signal debug failed: {type(exc).__name__}")


async def format_debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Owner/admin formatter verdict and safe preview for a stored signal."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	args = [str(value or "").strip() for value in (context.args or []) if str(value or "").strip()]
	if not args:
		await update.message.reply_text("Usage: /format_debug <signal_ref>")
		return
	try:
		payload = await _load_signal_debug_payload(args[0])
		if payload is None:
			await update.message.reply_text("No signal matches that reference.")
			return
		from signalrank_telegram.formatter import format_signal, signal_format_diagnostics
		diagnostics = signal_format_diagnostics(payload)
		rendered = format_signal(payload, user_tier="owner", display_tier="vip")
		verdict = "renderable" if rendered and str(rendered).strip() else "formatter_failed"
		preview = str(rendered or "").replace("<", "[").replace(">", "]")[:2500]
		message = (
			"Format Debug\n"
			f"{signal_id_line(payload)}\n"
			f"Verdict: {verdict}\n"
			f"Missing required: {', '.join(diagnostics['missing_required']) or 'none'}\n"
			f"Fallback renderable: {bool(diagnostics['can_render_fallback'])}\n\n"
			f"Preview:\n{preview or 'none'}"
		)
		await update.message.reply_text(message[:3900])
	except Exception as exc:
		logger.exception("[format_debug] failed: %s", exc)
		await update.message.reply_text(f"Format debug failed: {type(exc).__name__}")


async def engine_debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Admin-only latest engine cycle diagnostics from the Redis/runtime state heartbeat."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	try:
		import json as _json
		from core.redis_state import state

		raw = state.get_sync("engine:last_cycle")
		if not raw:
			await update.message.reply_text(
				"Engine Debug\n\nNo latest cycle heartbeat found yet. Wait for one engine cycle, then retry /engine_debug."
			)
			return
		if isinstance(raw, (bytes, bytearray)):
			raw = raw.decode("utf-8", errors="replace")
		cycle = _json.loads(raw) if isinstance(raw, str) else dict(raw or {})
		pipeline = dict(cycle.get("pipeline_stats") or {})

		def _fmt_ms(value):
			try:
				return f"{int(float(value))}ms"
			except Exception:
				return "n/a"

		lines = [
			"Engine Debug",
			"",
			f"Status: {cycle.get('status', 'unknown')}",
			f"Cycle: {cycle.get('cycle', 'n/a')}  Round: {cycle.get('round', 'n/a')}",
			f"Started: {cycle.get('started_at', 'n/a')}",
			f"Completed: {cycle.get('completed_at', cycle.get('updated_at', 'n/a'))}",
			f"Duration: {_fmt_ms(cycle.get('duration_ms'))}",
			f"Assets attempted: {cycle.get('assets_attempted', pipeline.get('assets_attempted', 0))}",
			f"Market data assets: {cycle.get('market_data_assets', pipeline.get('market_data_assets', 0))}",
			f"Market fetch: {_fmt_ms(cycle.get('market_fetch_ms', pipeline.get('market_fetch_ms')))}",
			f"Market fetch error: {cycle.get('market_fetch_error') or pipeline.get('market_fetch_error') or 'none'}",
			f"Max score: {cycle.get('max_score', 'n/a')}",
			f"Score absent reason: {cycle.get('max_score_absent_reason') or 'none'}",
			"",
			"Pipeline:",
		]
		for key in (
			"strategy_signals",
			"normalized",
			"consensus",
			"selected",
			"unique",
			"strict_candidates",
			"risk_passed",
			"final_signals",
			"stored",
			"no_candles",
			"no_strategy_signals",
			"validation_failed",
			"risk_failed",
			"advanced_filter_failed",
			"quality_rejected",
			"score_rejected",
			"skipped_portfolio_exposure",
		):
			if key in pipeline:
				lines.append(f"- {key}: {pipeline.get(key)}")
		delivery_reasons = pipeline.get("delivery_skip_reasons") or {}
		if delivery_reasons:
			lines.extend(["", "Delivery skips:"])
			for reason, count in sorted(
				delivery_reasons.items(), key=lambda item: int(item[1] or 0), reverse=True
			)[:12]:
				lines.append(f"- {reason}: {count}")
		class_counts = cycle.get("class_counts") or {}
		if class_counts:
			lines.extend(["", f"Class counts: {class_counts}"])
		await update.message.reply_text("\n".join(lines))
	except Exception as exc:
		await update.message.reply_text(f"Engine debug unavailable. Reference logged: {type(exc).__name__}")

def _load_last_engine_cycle() -> dict:
    """Return the latest engine heartbeat without exposing Redis details."""
    import json as _json

    raw = state.get_sync("engine:last_cycle")
    if not raw:
        return {}
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
            return dict(parsed or {}) if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _infer_no_signal_reason(cycle: dict) -> str:
    pipeline = dict(cycle.get("pipeline_stats") or {})
    market_data_assets = int(cycle.get("market_data_assets", pipeline.get("market_data_assets", 0)) or 0)
    strategies = int(pipeline.get("strategy_signals", 0) or 0)
    final_signals = int(pipeline.get("final_signals", 0) or 0)
    stored = int(pipeline.get("stored", 0) or 0)
    if cycle.get("market_fetch_error") or pipeline.get("market_fetch_error"):
        return "market_data_error"
    if market_data_assets <= 0:
        return str(cycle.get("max_score_absent_reason") or "no_usable_market_data")
    if strategies <= 0:
        return "no_strategy_setup"
    if int(pipeline.get("score_rejected", 0) or 0) > 0 and final_signals <= 0:
        return "score_threshold"
    if int(pipeline.get("risk_failed", 0) or 0) > 0 and final_signals <= 0:
        return "risk_gate"
    if int(pipeline.get("quality_rejected", 0) or 0) > 0 and final_signals <= 0:
        return "quality_gate"
    if final_signals > 0 and stored <= 0:
        return "storage_or_deduplication"
    if stored > 0:
        reasons = dict(pipeline.get("delivery_skip_reasons") or {})
        if reasons:
            return max(reasons, key=lambda key: int(reasons.get(key) or 0))
        return "delivery_or_user_eligibility"
    return str(cycle.get("max_score_absent_reason") or "no_candidate")


async def why_no_signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain the most recent no-signal cycle using recorded pipeline evidence."""
    if update.effective_user is None or update.message is None:
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    cycle = _load_last_engine_cycle()
    if not cycle:
        await update.message.reply_text(
            "Why No Signal\n\nNo completed engine heartbeat is available yet. "
            "Start the engine and wait for one cycle."
        )
        return
    pipeline = dict(cycle.get("pipeline_stats") or {})
    primary = _infer_no_signal_reason(cycle)
    delivery_reasons = dict(pipeline.get("delivery_skip_reasons") or {})
    lines = [
        "Why No Signal",
        "",
        f"Cycle: {cycle.get('cycle', 'n/a')}",
        f"Completed: {cycle.get('completed_at', cycle.get('updated_at', 'n/a'))}",
        f"Assets considered: {cycle.get('assets_attempted', pipeline.get('assets_attempted', 0))}",
        f"Usable market data: {cycle.get('market_data_assets', pipeline.get('market_data_assets', 0))}",
        f"Strategy candidates: {pipeline.get('strategy_signals', 0)}",
        f"Score rejected: {pipeline.get('score_rejected', 0)}",
        f"Risk rejected: {pipeline.get('risk_failed', 0)}",
        f"Quality rejected: {pipeline.get('quality_rejected', 0)}",
        f"Final signals: {pipeline.get('final_signals', 0)}",
        f"Stored: {pipeline.get('stored', 0)}",
        "",
        f"Primary reason: {primary}",
        f"Market fetch error: {cycle.get('market_fetch_error') or pipeline.get('market_fetch_error') or 'none'}",
        f"Effective asset concurrency: {os.getenv('MARKET_FETCH_ASSET_CONCURRENCY', '2')}",
    ]
    if delivery_reasons:
        lines.extend(["", "Top delivery blocks:"])
        for reason, count in sorted(delivery_reasons.items(), key=lambda item: int(item[1] or 0), reverse=True)[:8]:
            lines.append(f"- {reason}: {count}")
    await update.message.reply_text("\n".join(lines)[:3900])


async def ohlc_health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show effective OHLC concurrency, provider state and recent engine results."""
    if update.effective_user is None or update.message is None:
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    try:
        from data.fetcher import get_provider_concurrency_snapshot, get_provider_health_snapshot

        concurrency = get_provider_concurrency_snapshot()
        health = get_provider_health_snapshot()
    except Exception as exc:
        concurrency = {}
        health = {"error": type(exc).__name__}
    cycle = _load_last_engine_cycle()
    pipeline = dict(cycle.get("pipeline_stats") or {})
    lines = [
        "OHLC Health",
        "",
        f"Asset concurrency: {os.getenv('MARKET_FETCH_ASSET_CONCURRENCY', '2')}",
        f"Provider attempt limit: {os.getenv('OHLC_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME', '2')}",
        f"Provider timeout: {os.getenv('OHLC_PROVIDER_REQUEST_TIMEOUT_SECONDS', '7')}s",
        f"Last usable assets: {cycle.get('market_data_assets', pipeline.get('market_data_assets', 0))}",
        f"Last no-candle count: {pipeline.get('no_candles', 0)}",
        f"Last fetch error: {cycle.get('market_fetch_error') or pipeline.get('market_fetch_error') or 'none'}",
        "",
        "Provider concurrency:",
    ]
    if concurrency:
        for provider, values in sorted(concurrency.items()):
            if isinstance(values, dict):
                lines.append(
                    f"- {provider}: inflight={values.get('inflight', 0)} limit={values.get('limit', 'n/a')}"
                )
    else:
        lines.append("- no requests observed in this process")
    if isinstance(health, dict) and health:
        lines.extend(["", "Provider health:"])
        for provider, values in sorted(health.items())[:12]:
            if isinstance(values, dict):
                lines.append(
                    f"- {provider}: success={values.get('success_count', 0)} failures={values.get('failure_count', 0)}"
                )
    await update.message.reply_text("\n".join(lines)[:3900])


async def asset_capability_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inspect canonical classification, session and release capability for an asset."""
    if update.effective_user is None or update.message is None:
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    symbol = str((context.args or [""])[0]).upper().strip()
    if not symbol:
        await update.message.reply_text("Usage: /asset_capability BTCUSDT")
        return
    from core.asset_registry import resolve_asset_spec
    from data.market_hours import get_market_session_status

    spec = resolve_asset_spec(symbol)
    try:
        session_status = get_market_session_status(spec.symbol)
        status = getattr(session_status, "reason", None) or ("open" if session_status.is_open else "closed")
    except Exception as exc:
        status = f"error:{type(exc).__name__}"
    lines = [
        "Asset Capability",
        "",
        f"Requested: {symbol}",
        f"Canonical: {spec.symbol}",
        f"Class: {spec.asset_class}",
        f"Subtype: {spec.subtype}",
        f"Timezone: {spec.timezone}",
        f"Calendar: {spec.calendar}",
        f"24/7: {spec.continuous}",
        f"Actionable: {spec.actionable}",
        f"Analysis only: {spec.analysis_only}",
        f"Session status: {status}",
    ]
    if spec.asset_class == "unknown":
        lines.append("Capability state: DISABLED_BAD_CLASSIFICATION")
    elif spec.analysis_only:
        lines.append("Capability state: ANALYSIS_ONLY")
    else:
        lines.append("Capability state: registry_valid_provider_audit_required")
    await update.message.reply_text("\n".join(lines))


async def asset_class_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List canonical assets for one class without launching provider requests."""
    if update.effective_user is None or update.message is None:
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    requested = str((context.args or [""])[0]).lower().strip()
    if not requested:
        await update.message.reply_text("Usage: /asset_class_test crypto|forex|stock|index|commodity|macro")
        return
    aliases = {"fx": "forex", "indices": "index", "stocks": "stock", "commodities": "commodity"}
    requested = aliases.get(requested, requested)
    from core.asset_registry import list_asset_specs

    specs = [spec for spec in list_asset_specs() if spec.asset_class == requested]
    if not specs:
        await update.message.reply_text(f"No canonical assets are registered for class {requested}.")
        return
    actionable = [spec.symbol for spec in specs if spec.actionable]
    analysis_only = [spec.symbol for spec in specs if spec.analysis_only]
    await update.message.reply_text(
        "Asset Class Test\n\n"
        f"Class: {requested}\n"
        f"Registered: {len(specs)}\n"
        f"Actionable: {', '.join(actionable) or 'none'}\n"
        f"Analysis only: {', '.join(analysis_only) or 'none'}"
    )


async def all_asset_test_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Summarise the canonical registry and explain how to run the full audit."""
    if update.effective_user is None or update.message is None:
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    from collections import Counter
    from core.asset_registry import list_asset_specs

    specs = list_asset_specs()
    counts = Counter(spec.asset_class for spec in specs)
    lines = [
        "All Asset Test Status",
        "",
        f"Registered canonical assets: {len(specs)}",
        f"Actionable: {sum(1 for spec in specs if spec.actionable)}",
        f"Analysis only: {sum(1 for spec in specs if spec.analysis_only)}",
        "",
        "Classes:",
    ]
    lines.extend(f"- {name}: {count}" for name, count in sorted(counts.items()))
    lines.extend([
        "",
        "Full network audit: python scripts/asset_capability_audit.py --all",
        "This command reports registry state only and does not fabricate provider success.",
    ])
    await update.message.reply_text("\n".join(lines))


async def delivery_eligibility_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explain whether the current user is eligible to receive future signals."""
    if update.effective_user is None or update.message is None:
        return
    user_id = int(update.effective_user.id)
    try:
        from sqlalchemy import select
        from db.models import SignalDelivery, Subscription, User
        from services.user_intelligence import get_user_trading_preferences

        async with get_session(
            priority="interactive",
            label="telegram_delivery_eligibility",
            timeout_seconds=3.0,
        ) as session:
            user = (
                await session.execute(select(User).where(User.telegram_user_id == user_id).limit(1))
            ).scalar_one_or_none()
            if user is None:
                await update.message.reply_text(
                    "Delivery Eligibility\n\nRegistered: no\nUse /start to create your account."
                )
                return
            subscription = (
                await session.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .order_by(Subscription.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            latest_delivery = (
                await session.execute(
                    select(SignalDelivery)
                    .where(SignalDelivery.user_id == user.id)
                    .order_by(SignalDelivery.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            prefs = await get_user_trading_preferences(session, user_id)
        subscription_status = str(getattr(subscription, "status", "none") or "none")
        active_subscription = subscription_status.lower() == "active" or str(user.tier).lower() in {"admin", "owner"}
        lines = [
            "Delivery Eligibility",
            "",
            "Registered: yes",
            f"Tier: {str(user.tier or 'free').upper()}",
            f"Subscription active: {'yes' if active_subscription else 'no'}",
            f"Terms accepted: {'yes' if bool(user.accepted_terms) else 'no'}",
            f"Trade profile: {prefs.trade_profile}",
            f"Risk profile: {prefs.risk_profile}",
            f"Asset classes: {', '.join(prefs.asset_classes)}",
            f"Sessions: {', '.join(prefs.sessions)}",
            f"Notifications: {prefs.notification_style}",
            f"Execution mode: {prefs.execution_mode}",
            f"Latest delivery state: {getattr(latest_delivery, 'delivery_state', 'none')}",
            f"Latest delivery sent: {'yes' if bool(getattr(latest_delivery, 'sent_ok', False)) else 'no'}",
        ]
        if not user.accepted_terms:
            lines.extend(["", "Primary block: terms_not_accepted"])
        elif not active_subscription and str(user.tier).lower() not in {"free"}:
            lines.extend(["", "Primary block: inactive_subscription"])
        else:
            lines.extend(["", "Account gate: eligible; each signal still passes profile, cooldown and risk checks."])
        await update.message.reply_text("\n".join(lines)[:3900])
    except Exception as exc:
        logger.exception("[delivery_eligibility] failed: %s", exc)
        await update.message.reply_text(
            f"Delivery eligibility is temporarily unavailable ({type(exc).__name__})."
        )


async def owner_test_delivery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a safe owner-only Telegram infrastructure test with no trade mutation."""
    if update.effective_user is None or update.message is None:
        return
    user_id = int(update.effective_user.id)
    if user_id not in set(OWNER_IDS or set()):
        await update.message.reply_text("Owner only.")
        return
    asset = str((context.args or ["BTCUSDT"])[0]).upper().strip() or "BTCUSDT"
    from core.asset_registry import resolve_asset_spec

    spec = resolve_asset_spec(asset)
    if spec.asset_class == "unknown":
        await update.message.reply_text("Unknown asset. The test was blocked before Telegram delivery.")
        return
    logger.info("[test_delivery_reserved] user=%s asset=%s", user_id, spec.symbol)
    message = (
        "TEST — NOT A TRADING SIGNAL\n\n"
        f"Asset: {spec.symbol}\n"
        "Purpose: Telegram infrastructure and acknowledgement test only.\n"
        "No trade, signal, subscription, performance or broker record is created."
    )
    try:
        sent = await context.bot.send_message(chat_id=user_id, text=message)
        message_id = int(getattr(sent, "message_id", 0) or 0)
        logger.info(
            "[telegram_send_ok] kind=infrastructure_test user=%s asset=%s message_id=%s",
            user_id,
            spec.symbol,
            message_id,
        )
        try:
            import json as _json
            state.set_sync(
                f"delivery_test:{user_id}:{message_id}",
                _json.dumps({
                    "kind": "infrastructure_test",
                    "asset": spec.symbol,
                    "telegram_user_id": user_id,
                    "telegram_message_id": message_id,
                    "sent_ok": True,
                    "affects_performance": False,
                }),
                ex=86400,
            )
            logger.info("[delivery_proof_write] kind=infrastructure_test message_id=%s", message_id)
        except Exception as store_exc:
            logger.warning("[test_delivery_receipt_store_failed] error=%s", type(store_exc).__name__)
        logger.info("[test_delivery_completed] user=%s asset=%s", user_id, spec.symbol)
    except Exception as exc:
        logger.exception("[test_delivery_failed] user=%s asset=%s", user_id, spec.symbol)
        await update.message.reply_text(f"Infrastructure test failed: {type(exc).__name__}")


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Set or show the user's personalized AI trading profile."""
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	from services.trade_profiles import normalize_trade_profile
	from services.user_intelligence import (
		UserTradingPreferences,
		format_preferences,
		get_user_trading_preferences,
		normalize_risk_profile,
		set_user_trading_preferences,
	)

	user_id = int(update.effective_user.id)
	args = [str(x).strip().lower() for x in (context.args or []) if str(x).strip()]
	if args and args[0] == "timezone":
		await _send_timezone_panel(update.message, user_id)
		return

	is_read = not args
	response_text = ""
	response_markup = None
	timezone_user = None
	try:
		# Keep the DB foreground lane limited to DB work. Telegram network I/O and
		# timezone prompting happen only after this session has been released.
		async with get_session(
			priority="interactive",
			label="profile.read" if is_read else "profile.write",
			timeout_seconds=5,
		) as session:
			current = await get_user_trading_preferences(session, user_id)
			if is_read:
				from db.models import User
				from sqlalchemy import select
				from signalrank_telegram.timezones import effective_user_timezone
				from telegram import InlineKeyboardButton, InlineKeyboardMarkup

				timezone_user = (await session.execute(
					select(User).where(User.telegram_user_id == user_id)
				)).scalar_one_or_none()
				timezone_name = effective_user_timezone(
					getattr(timezone_user, "timezone", None), user_id
				)
				response_text = format_preferences(current) + f"\nTimezone: {timezone_name}"
				response_markup = InlineKeyboardMarkup([[
					InlineKeyboardButton("Timezone", callback_data="nav_timezone")
				]])
			else:
				cmd = args[0]
				next_prefs = UserTradingPreferences(**{
					field_name: getattr(current, field_name)
					for field_name in current.__dataclass_fields__
				})
				valid_update = True
				if cmd in {"scalp", "scalper", "day", "swing", "position", "all"}:
					next_prefs.trade_profile = normalize_trade_profile(cmd, default="all")
				elif cmd == "risk" and len(args) >= 2:
					next_prefs.risk_profile = normalize_risk_profile(args[1])
				elif cmd == "assets" and len(args) >= 2:
					classes = []
					for item in args[1:]:
						item = item.replace("forex", "fx").replace("indices", "index")
						if item in {"crypto", "fx", "commodity", "index", "stock", "all"}:
							classes.append(item)
					next_prefs.asset_classes = (
						("crypto", "fx", "commodity", "index", "stock")
						if "all" in classes else tuple(classes or current.asset_classes)
					)
				elif cmd == "timeframes" and len(args) >= 2:
					next_prefs.preferred_timeframes = tuple(dict.fromkeys(args[1:]))
				elif cmd == "strategies" and len(args) >= 2:
					next_prefs.preferred_strategies = tuple(dict.fromkeys(args[1:]))
				elif cmd == "sessions" and len(args) >= 2:
					next_prefs.sessions = tuple(args[1:]) or ("auto",)
				elif cmd == "notify" and len(args) >= 2:
					next_prefs.notification_style = args[1]
				elif cmd == "execution" and len(args) >= 2:
					mode = args[1]
					next_prefs.execution_mode = (
						mode if mode in {"manual", "semi", "semi_auto", "auto", "mt5", "bybit", "binance"}
						else "manual"
					)
				elif cmd == "block" and len(args) >= 2:
					next_prefs.blocked_assets = tuple(sorted(set(
						current.blocked_assets + tuple(a.upper() for a in args[1:])
					)))
				elif cmd == "prefer" and len(args) >= 2:
					next_prefs.preferred_assets = tuple(sorted(set(
						current.preferred_assets + tuple(a.upper() for a in args[1:])
					)))
				else:
					valid_update = False

				if valid_update:
					selected = await set_user_trading_preferences(session, user_id, next_prefs)
					await session.commit()
					response_text = "AI trading profile updated.\n\n" + format_preferences(selected)
				else:
					response_text = format_preferences(current)

		await update.message.reply_text(response_text, reply_markup=response_markup)
		if is_read:
			await maybe_prompt_timezone(update.message, user_id, user=timezone_user)
	except TimeoutError:
		logger.warning("[profile] DB admission timeout user=%s args=%s", user_id, args)
		action = "load" if is_read else "update"
		await update.message.reply_text(
			f"Trading profile is temporarily busy and could not {action}. Please retry /profile."
		)
	except Exception as exc:
		logger.exception("[profile] command failed user=%s args=%s", user_id, args)
		action = "load" if is_read else "update"
		await update.message.reply_text(
			f"Could not {action} trading profile: {type(exc).__name__}"
		)


async def mission_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Signal Mission Control: inspect live health and recommendation for an active signal."""
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = int(update.effective_user.id)
	args = [str(x).strip() for x in (context.args or []) if str(x).strip()]
	try:
		from db.pg_features import list_unresolved_signals_for_user
		from engine.price_validator import enrich_signal_with_live_price
		from services.mission_control import build_mission_snapshot, format_mission
		from services.trading_intelligence import enrich_signal_intelligence

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			rows = await list_unresolved_signals_for_user(session, telegram_user_id=user_id, lookback_days=30)
		if not rows:
			await update.message.reply_text("No active delivered signal mission is available right now.")
			return
		needle = args[0].lower() if args else ""
		selected = None
		for row in rows:
			sid = str(getattr(row, "signal_id", "") or "")
			asset = str(getattr(row, "asset", "") or "")
			if not needle or sid.lower().startswith(needle) or asset.lower() == needle:
				selected = row
				break
		if selected is None:
			await update.message.reply_text("Signal mission not found in your active delivered signals. Use /signals first.")
			return
		payload = {
			"signal_id": selected.signal_id,
			"asset": selected.asset,
			"timeframe": selected.timeframe,
			"direction": selected.direction,
			"entry": selected.entry,
			"stop_loss": selected.stop_loss,
			"take_profit": selected.take_profit,
			"rr_ratio": selected.rr_estimate,
			"score": selected.score,
			"confidence": getattr(selected, "confidence", 0.5),
			"regime": getattr(selected, "regime", None),
			"strength": getattr(selected, "strength", 0.5),
			"ml_probability": getattr(selected, "ml_probability", 0.5),
			"strategy_name": selected.strategy_name,
			"strategy_group": selected.strategy_group,
			"created_at": selected.created_at,
			"status": getattr(selected, "status", "active"),
		}
		try:
			payload = enrich_signal_with_live_price(payload)
		except Exception:
			pass
		try:
			payload = enrich_signal_intelligence(payload)
		except Exception:
			pass
		snapshot = build_mission_snapshot(payload, current_price=payload.get("current_price") or payload.get("live_price"))
		await update.message.reply_text(format_mission(snapshot))
	except Exception as exc:
		await update.message.reply_text(f"Mission control unavailable. Reference logged: {type(exc).__name__}")


@require_tier("ADMIN")
async def system_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Admin alias for the production system health view."""
	await ops_health_command(update, context)

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


async def timezone_command(update, context) -> None:
	"""Show or update timezone using an IANA name or a supported city alias."""
	if update.effective_user is None or update.message is None:
		return
	telegram_user_id = int(update.effective_user.id)
	requested = " ".join(str(arg or "").strip() for arg in (context.args or [])).strip()
	if requested:
		from signalrank_telegram.timezones import resolve_timezone_query
		valid = resolve_timezone_query(requested)
		if valid is None:
			await update.message.reply_text(
				"Timezone not recognized. Try /timezone Africa/Lagos, /timezone London, or /timezone New York."
			)
			return
		if await _save_user_timezone(telegram_user_id, valid, source="manual"):
			await update.message.reply_text(
				f"Timezone set to {valid}. Signal times will use your local time.",
				reply_markup=_timezone_location_keyboard(remove=True),
			)
		else:
			await update.message.reply_text("Run /start first, then set your timezone.")
		return
	await _send_timezone_panel(update.message, telegram_user_id)


def _timezone_location_keyboard(*, remove: bool = False):
	from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
	if remove:
		return ReplyKeyboardRemove()
	return ReplyKeyboardMarkup(
		[
			[KeyboardButton("Use my current location", request_location=True)],
			[KeyboardButton("Keep UTC")],
		],
		resize_keyboard=True,
		one_time_keyboard=True,
	)


def _timezone_inline_keyboard(*, travel_enabled: bool = False):
	from telegram import InlineKeyboardButton, InlineKeyboardMarkup
	from signalrank_telegram.timezones import COMMON_TIMEZONES
	rows = []
	for index in range(0, len(COMMON_TIMEZONES), 2):
		rows.append([
			InlineKeyboardButton(
				zone.split("/")[-1].replace("_", " "),
				callback_data=f"timezone_set_{zone.replace('/', '~')}",
			)
			for zone in COMMON_TIMEZONES[index:index + 2]
		])
	rows.extend([
		[InlineKeyboardButton("Choose manually", callback_data="timezone_manual")],
		[InlineKeyboardButton(
			"Travel mode: ON" if travel_enabled else "Travel mode: OFF",
			callback_data="timezone_travel_toggle",
		)],
		[InlineKeyboardButton("Keep UTC", callback_data="timezone_keep_utc")],
	])
	return InlineKeyboardMarkup(rows)


async def _get_timezone_user(telegram_user_id: int):
	from db.models import User
	from sqlalchemy import select
	async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
		return (await session.execute(
			select(User).where(User.telegram_user_id == int(telegram_user_id))
		)).scalar_one_or_none()


async def _save_user_timezone(
	telegram_user_id: int,
	timezone_name: str,
	*,
	source: str,
	location=None,
) -> bool:
	from datetime import datetime, timezone as datetime_timezone
	from db.models import User
	from sqlalchemy import select
	from signalrank_telegram.timezones import should_store_location_coordinates

	now = datetime.now(datetime_timezone.utc).replace(tzinfo=None)
	async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
		user = (await session.execute(
			select(User).where(User.telegram_user_id == int(telegram_user_id))
		)).scalar_one_or_none()
		if user is None:
			return False
		user.timezone = timezone_name
		user.timezone_source = source
		user.timezone_updated_at = now
		if location is not None:
			user.last_location_at = now
			if should_store_location_coordinates():
				user.last_location_lat = float(location.latitude)
				user.last_location_lon = float(location.longitude)
				user.last_location_accuracy_m = getattr(location, "horizontal_accuracy", None)
			else:
				user.last_location_lat = None
				user.last_location_lon = None
				user.last_location_accuracy_m = None
		await session.commit()
	return True


async def _send_timezone_panel(message, telegram_user_id: int) -> None:
	from datetime import datetime, timezone as datetime_timezone
	from signalrank_telegram.timezones import effective_user_timezone, format_user_time
	user = await _get_timezone_user(telegram_user_id)
	if user is None:
		await message.reply_text("Run /start first, then set your timezone.")
		return
	current = effective_user_timezone(user.timezone, telegram_user_id)
	local_time = format_user_time(datetime.now(datetime_timezone.utc), user, include_date=False)
	await message.reply_text(
		f"Timezone settings\n\nCurrent: {current}\nLocal time: {local_time}\n"
		f"Source: {getattr(user, 'timezone_source', None) or 'default'}\n\n"
		"Share your location, choose below, or type /timezone London.",
		reply_markup=_timezone_inline_keyboard(
			travel_enabled=bool(getattr(user, "timezone_auto_update", False))
		),
	)
	await message.reply_text(
		"Location is used only to resolve your timezone. Exact coordinates are not retained by default.",
		reply_markup=_timezone_location_keyboard(),
	)


async def timezone_location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None or update.message.location is None:
		return
	from signalrank_telegram.timezones import timezone_from_coordinates
	location = update.message.location
	timezone_name = timezone_from_coordinates(location.latitude, location.longitude)
	if timezone_name is None:
		await update.message.reply_text(
			"I could not resolve that location. Use /timezone Africa/Lagos or another city.",
			reply_markup=_timezone_location_keyboard(remove=True),
		)
		return
	await _save_user_timezone(
		int(update.effective_user.id), timezone_name, source="location", location=location
	)
	await update.message.reply_text(
		f"Timezone updated to {timezone_name}. Exact coordinates were not retained.",
		reply_markup=_timezone_location_keyboard(remove=True),
	)


async def timezone_keep_utc_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	await _save_user_timezone(int(update.effective_user.id), "UTC", source="manual")
	await update.message.reply_text(
		"Timezone fixed to UTC. You can change it anytime with /timezone.",
		reply_markup=_timezone_location_keyboard(remove=True),
	)


async def travelmode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	from datetime import datetime, timezone as datetime_timezone
	from db.models import User
	from sqlalchemy import select
	args = [str(arg).lower() for arg in (context.args or [])]
	if not args or args[0] not in {"on", "off"}:
		user = await _get_timezone_user(int(update.effective_user.id))
		status = "on" if user and user.timezone_auto_update else "off"
		await update.message.reply_text(f"Travel mode is {status}. Use /travelmode on or /travelmode off.")
		return
	enabled = args[0] == "on"
	async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
		user = (await session.execute(
			select(User).where(User.telegram_user_id == int(update.effective_user.id))
		)).scalar_one_or_none()
		if user is None:
			await update.message.reply_text("Run /start first.")
			return
		user.timezone_auto_update = enabled
		user.timezone_updated_at = user.timezone_updated_at or datetime.now(datetime_timezone.utc).replace(tzinfo=None)
		await session.commit()
	await update.message.reply_text(
		"Travel mode enabled. I will periodically ask you to refresh your location."
		if enabled else "Travel mode disabled. Your saved timezone will remain fixed."
	)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	from telegram import InlineKeyboardButton, InlineKeyboardMarkup
	user = await _get_timezone_user(int(update.effective_user.id))
	from signalrank_telegram.timezones import effective_user_timezone
	current = effective_user_timezone(getattr(user, "timezone", None), update.effective_user.id)
	await update.message.reply_text(
		f"Settings\n\nTimezone: {current}\nTravel mode: {'on' if user and user.timezone_auto_update else 'off'}",
		reply_markup=InlineKeyboardMarkup([
			[InlineKeyboardButton("Timezone", callback_data="nav_timezone")],
			[InlineKeyboardButton("Account", callback_data="nav_account")],
		]),
	)


async def maybe_prompt_timezone(message, telegram_user_id: int, *, user=None) -> bool:
	if user is None:
		user = await _get_timezone_user(telegram_user_id)
	if user is None or user.timezone:
		return False
	try:
		key = f"timezone_prompted:{int(telegram_user_id)}"
		if await state.cache_get(key):
			return False
		await state.cache_set(key, "1", ex=14 * 24 * 3600)
	except Exception:
		pass
	await message.reply_text(
		"Your timezone is not set. Signal times are currently shown in UTC. Use /timezone to set local time."
	)
	return True


async def handle_timezone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
	query = update.callback_query
	if query is None or update.effective_user is None:
		return False
	data = str(query.data or "")
	if data == "nav_timezone":
		await _send_timezone_panel(query.message, int(update.effective_user.id))
		return True
	if data.startswith("timezone_set_"):
		zone = data.replace("timezone_set_", "", 1).replace("~", "/")
		from signalrank_telegram.timezones import validate_timezone_name
		valid = validate_timezone_name(zone)
		if valid and await _save_user_timezone(int(update.effective_user.id), valid, source="manual"):
			await query.edit_message_text(f"Timezone set to {valid}.")
		return True
	if data == "timezone_keep_utc":
		await _save_user_timezone(int(update.effective_user.id), "UTC", source="manual")
		await query.edit_message_text("Timezone fixed to UTC. You can change it anytime with /timezone.")
		return True
	if data == "timezone_manual":
		await query.message.reply_text("Type /timezone Lagos, /timezone London, or an IANA name such as Asia/Dubai.")
		return True
	if data == "timezone_travel_toggle":
		user = await _get_timezone_user(int(update.effective_user.id))
		context.args = ["off" if user and user.timezone_auto_update else "on"]
		proxy = type("TimezoneUpdate", (), {
			"effective_user": update.effective_user,
			"message": query.message,
		})()
		await travelmode_command(proxy, context)
		return True
	return False

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
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	try:
		async with get_session(
			priority="interactive",
			label="referral.leaderboard",
			timeout_seconds=8.0,
		) as session:
			from sqlalchemy import select, func, desc
			rows = list((await session.execute(
				select(
					ReferralAttribution.referrer_user_id,
					func.count(ReferralAttribution.id).label("cnt"),
				)
				.group_by(ReferralAttribution.referrer_user_id)
				.order_by(desc("cnt"))
				.limit(10)
			)).all() or [])
			if not rows:
				await update.message.reply_text("No referral data yet.")
				return
			ids = [int(row[0]) for row in rows]
			user_rows = list((await session.execute(
				select(User.id, User.telegram_user_id, User.username).where(User.id.in_(ids))
			)).all() or [])
			users = {int(row[0]): (row[1], row[2]) for row in user_rows}
	except Exception as exc:
		logging.getLogger(__name__).exception(
			"[referral_leaderboard_failed] user=%s error=%s",
			update.effective_user.id,
			exc,
		)
		await update.message.reply_text("⚠️ Referral leaderboard is temporarily unavailable. Please try again.")
		return

	msg = "🏆 Referral Leaderboard:\n\n"
	for index, (uid, count) in enumerate(rows, 1):
		telegram_uid, username = users.get(int(uid), (None, None))
		if username:
			name = f"@{username}"
		elif telegram_uid:
			name = f"User ***{str(telegram_uid)[-3:]}"
		else:
			name = f"User ***{str(uid)[-3:]}"
		msg += f"{index}. {name}: {int(count)} valid referrals\n"
	await update.message.reply_text(msg)

async def referral_rewards_command(update, context) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = int(update.effective_user.id)
	try:
		async with get_session(
			priority="interactive",
			label="referral.rewards",
			timeout_seconds=8.0,
		) as session:
			from sqlalchemy import select, func
			from db.pg_features import get_referral_progress
			user = await get_or_create_user(session, telegram_user_id=user_id)
			rows = list((await session.execute(
				select(
					ReferralReward.reward_type,
					func.count(ReferralReward.id).label("cnt"),
					func.coalesce(func.sum(ReferralReward.reward_value), 0).label("total"),
				)
				.where(ReferralReward.referrer_user_id == int(user.id))
				.group_by(ReferralReward.reward_type)
			)).all() or [])
			progress = await get_referral_progress(session, referrer_telegram_user_id=user_id)
			await session.commit()
	except Exception as exc:
		logging.getLogger(__name__).exception(
			"[referral_rewards_failed] user=%s error=%s",
			user_id,
			exc,
		)
		await update.message.reply_text("⚠️ Referral rewards are temporarily unavailable. Please try again.")
		return

	total_days = sum(
		int(total or 0)
		for reward_type, _count, total in rows
		if str(reward_type).lower() == "premium_days"
	)
	if not rows:
		msg = "No rewards earned yet. Refer friends to earn rewards!"
	else:
		msg = "🎁 Your Referral Rewards:\n"
		for reward_type, count, total in rows:
			msg += f"• {reward_type}: {int(count or 0)} time(s), total value: {int(total or 0)}\n"
	if total_days > 0:
		msg += f"\n✅ Total Premium days earned: +{total_days}"
	requirement = int(progress.get("requirement", 3) or 3)
	msg += (
		f"\n\n📊 Progress: {int(progress.get('toward_next', 0) or 0)}/{requirement}"
		f" (invite {int(progress.get('needed_for_next', requirement) or requirement)} more "
		f"for the next +{int(progress.get('reward_days_per_3', 7) or 7)} days)"
		f"\n👥 Total valid referrals: {int(progress.get('total', 0) or 0)}"
	)
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

	if subcmd in {"discovered", "health", "providers", "coverage", "failing", "quarantined", "liquidity", "sessions", "pending", "inactive"}:
		try:
			from data.pair_discovery import get_asset_discovery_snapshot
			snapshot = get_asset_discovery_snapshot(force_refresh=subcmd in {"discovered", "health"})
		except Exception as exc:
			await update.message.reply_text(f"Asset discovery diagnostics unavailable: {type(exc).__name__}")
			return

		counts = dict(snapshot.get("counts") or {})
		samples = dict(snapshot.get("samples") or {})
		providers = dict(snapshot.get("providers") or {})
		lines: list[str] = [
			"Asset Discovery",
			f"Total discovered: {snapshot.get('total', 0)}",
			f"Refresh age: {snapshot.get('last_refresh_age_seconds', 'n/a')}s",
			"Counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
		]

		if subcmd in {"providers", "coverage", "health"}:
			lines.extend([
				"",
				"Providers:",
				f"- crypto provider: {providers.get('crypto_provider', 'auto')}",
				f"- auto all providers: {providers.get('auto_all_providers')}",
				f"- binance disabled: {providers.get('binance_disabled')} {providers.get('binance_disabled_reason') or ''}".strip(),
				f"- bybit disabled: {providers.get('bybit_disabled')} {providers.get('bybit_disabled_reason') or ''}".strip(),
			])

		if subcmd in {"discovered", "health", "pending", "coverage"}:
			lines.append("")
			lines.append("Samples:")
			for asset_type, vals in sorted(samples.items()):
				preview = ", ".join(str(v) for v in list(vals or [])[:12]) or "none"
				lines.append(f"- {asset_type}: {preview}")

		if subcmd == "inactive":
			async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
				rows = await list_all_managed_assets(session)
			inactive = [r for r in rows if not getattr(r, "is_active", False)]
			lines = ["Inactive Managed Assets"]
			if inactive:
				for r in inactive[:50]:
					lines.append(f"- {r.symbol} ({r.asset_type})")
			else:
				lines.append("None.")

		if subcmd in {"failing", "quarantined"}:
			try:
				from data.fetcher import get_provider_health_snapshot
				health = get_provider_health_snapshot()
				bad = {k: v for k, v in health.items() if not bool(v.get("healthy", True))}
			except Exception:
				bad = {}
			lines = [f"{subcmd.title()} Providers"]
			if bad:
				for name, info in sorted(bad.items()):
					lines.append(f"- {name}: failures={info.get('failure_count', 0)} last_error={info.get('last_error') or 'n/a'}")
			else:
				lines.append("None currently tracked.")

		if subcmd in {"liquidity", "sessions"}:
			lines.extend([
				"",
				"Detailed per-asset liquidity/session telemetry is tracked by market intelligence during scans.",
				"Use /market <SYMBOL> for a live asset view and /system for global health.",
			])

		if snapshot.get("error"):
			lines.append(f"Error: {snapshot.get('error')}")
		await update.message.reply_text("\n".join(lines[:80]))
		return

	if subcmd == "list":
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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
			parse_mode="MarkdownV2",
		)
		return

	if subcmd == "add":
		if len(args) < 2:
			await update.message.reply_text("Usage: /assets add <SYMBOL>")
			return
		symbol = args[1].upper().strip()
		atype = get_asset_type(symbol)
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			await add_managed_asset(
				session, symbol=symbol, asset_type=atype,
				added_by=update.effective_user.id,
			)
			await session.commit()
		await update.message.reply_text(f"✅ `{symbol}` pinned ({atype}).", parse_mode="MarkdownV2")
		return

	if subcmd == "remove":
		if len(args) < 2:
			await update.message.reply_text("Usage: /assets remove <SYMBOL>")
			return
		symbol = args[1].upper().strip()
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			found = await remove_managed_asset(session, symbol=symbol)
			await session.commit()
		if found:
			await update.message.reply_text(f"❌ `{symbol}` unpinned.", parse_mode="MarkdownV2")
		else:
			await update.message.reply_text(f"`{symbol}` was not in the managed list.", parse_mode="MarkdownV2")
		return

	await update.message.reply_text(
		"Usage:\n/assets list\n/assets add <SYMBOL>\n/assets remove <SYMBOL>\n"
		"/assets discovered\n/assets inactive\n/assets providers\n/assets coverage\n/assets failing\n/assets quarantined\n/assets liquidity\n/assets sessions"
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
	async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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
	running_on_railway = bool((os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
	
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

	# Railway env readiness check
	if running_on_railway:
		checks.append("✅ Railway: detected")
		checks.append("✅ GEMINI_API_KEY: set" if (os.getenv("GEMINI_API_KEY") or "").strip() else "❌ GEMINI_API_KEY: missing")
		checks.append("✅ META_API_TOKEN: set" if (os.getenv("META_API_TOKEN") or "").strip() else "❌ META_API_TOKEN: missing")
		checks.append("✅ ENCRYPTION_KEY: set" if (os.getenv("ENCRYPTION_KEY") or "").strip() else "❌ ENCRYPTION_KEY: missing")
		_owner_ids_raw = (os.getenv("OWNER_IDS") or "").strip()
		checks.append("✅ OWNER_IDS: set" if _owner_ids_raw else "⚠️ OWNER_IDS: missing (owner-only commands disabled)")
	
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
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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


@require_tier("ADMIN")
async def ops_health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Admin runtime reliability report.

	Reports:
	- delivered signals without outcomes
	- time-stop/force-closed outcomes
	- redis connectivity
	- mt5 credential-link success rate
	"""
	if update.message is None:
		return

	try:
		from datetime import datetime, timedelta
		from sqlalchemy import select, func, or_
		from db.session import get_engine_for_event_loop, get_session
		from db.models import Signal, SignalDelivery, Outcome, MT5Credentials

		if get_engine_for_event_loop() is None:
			await update.message.reply_text("⚠️ Database not configured.")
			return

		# Redis connectivity check (real connectivity, not local fallback).
		redis_status = "❌ disconnected"
		redis_url = (os.getenv("STATE_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
		if redis_url:
			try:
				import redis as _redis
				_rc = _redis.from_url(
					redis_url,
					decode_responses=True,
					socket_connect_timeout=3,
					socket_timeout=3,
				)
				await asyncio.to_thread(_rc.ping)
				try:
					await asyncio.to_thread(_rc.close)
				except Exception:
					pass
				redis_status = "✅ connected"
			except Exception as _re:
				redis_status = f"❌ error ({type(_re).__name__})"
		else:
			redis_status = "⚠️ REDIS_URL not set"

		window_days = 30
		now = now_utc_naive()
		window_start = now - timedelta(days=window_days)

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			# 1) Delivered signals without any outcome row.
			proof_states = ["sent", "confirmed", "delivered", "reconciled"]
			untracked_q = (
				select(func.count(func.distinct(SignalDelivery.signal_id)))
				.join(Signal, Signal.signal_id == SignalDelivery.signal_id)
				.outerjoin(Outcome, Outcome.signal_id == SignalDelivery.signal_id)
				.where(
					SignalDelivery.sent_ok.is_(True),
					SignalDelivery.telegram_chat_id.is_not(None),
					SignalDelivery.telegram_message_id.is_not(None),
					func.lower(SignalDelivery.delivery_state).in_(proof_states),
					Signal.archived.is_(False),
					Outcome.id.is_(None),
				)
			)
			untracked_count = int((await session.execute(untracked_q)).scalar() or 0)

			terminal_statuses = [
				"tp", "tp3", "sl", "invalid", "invalidated", "time_stop",
				"partial_win_be", "missed_entry", "expired",
			]
			pending_terminal_q = (
				select(func.count(func.distinct(SignalDelivery.signal_id)))
				.join(Signal, Signal.signal_id == SignalDelivery.signal_id)
				.outerjoin(Outcome, Outcome.signal_id == SignalDelivery.signal_id)
				.where(
					SignalDelivery.sent_ok.is_(True),
					SignalDelivery.telegram_chat_id.is_not(None),
					SignalDelivery.telegram_message_id.is_not(None),
					func.lower(SignalDelivery.delivery_state).in_(proof_states),
					Signal.archived.is_(False),
					or_(
						Outcome.id.is_(None),
						func.lower(Outcome.status).notin_(terminal_statuses),
					),
				)
			)
			pending_terminal_count = int((await session.execute(pending_terminal_q)).scalar() or 0)

			# 2) Stale force-closed outcomes (TIME_STOP policy, with invalid fallback).
			invalid_q = (
				select(func.count(Outcome.id))
				.where(
					Outcome.status.in_(["time_stop", "invalid"]),
					Outcome.closed_at.is_not(None),
					Outcome.closed_at >= window_start,
				)
			)
			invalid_count_30d = int((await session.execute(invalid_q)).scalar() or 0)

			# 3) MT5 link success rate over recent credentials rows.
			total_mt5_q = select(func.count(MT5Credentials.id)).where(MT5Credentials.created_at >= window_start)
			success_mt5_q = select(func.count(MT5Credentials.id)).where(
				MT5Credentials.created_at >= window_start,
				MT5Credentials.metaapi_account_id.is_not(None),
			)
			total_mt5 = int((await session.execute(total_mt5_q)).scalar() or 0)
			success_mt5 = int((await session.execute(success_mt5_q)).scalar() or 0)
			await session.commit()

		mt5_rate = (float(success_mt5) / float(total_mt5) * 100.0) if total_mt5 > 0 else 0.0

		db_health = {}
		try:
			db_health = await collect_database_health()
		except Exception:
			db_health = {}
		pool = dict(db_health.get("pool") or {})
		postgres = dict(db_health.get("postgres") or {})
		admission = dict(pool.get("priority_admission") or {})
		pool_size = int(pool.get("size") or pool.get("effective_pool_size") or 0)
		checked_out = int(pool.get("checkedout") or pool.get("checked_out") or 0)
		# Webhook handlers can run on an auxiliary event loop backed by NullPool.
		# Report the main pooled engine when available instead of claiming that
		# database pool metrics are unavailable.
		if pool_size <= 0:
			inventory = [
				item for item in (pool.get("engine_inventory") or [])
				if isinstance(item, dict) and not item.get("nullpool")
			]
			if inventory:
				primary_pool = max(inventory, key=lambda item: int(item.get("pool_size") or 0))
				pool_size = int(primary_pool.get("pool_size") or 0)
				checked_out = int(primary_pool.get("checked_out") or 0)
		max_connections = str(postgres.get("max_connections") or "unknown")
		db_pressure = (
			f"pool {checked_out}/{pool_size}" if pool_size > 0 else "pool metrics unavailable"
		)
		if admission:
			db_pressure += f" • admission {int(admission.get('active_total') or 0)}/{int(admission.get('capacity') or 0)}"

		msg = (
			"🛠️ <b>Ops Health</b>\n\n"
			"<b>Runtime</b>\n"
			f"• Redis: <b>{redis_status}</b>\n"
			f"• Database: <b>{db_pressure}</b> • PostgreSQL max: <b>{max_connections}</b>\n"
			f"• Proof-backed deliveries with no outcome row: <b>{untracked_count}</b>\n"
			f"• Proof-backed deliveries awaiting terminal outcome: <b>{pending_terminal_count}</b>\n"
			f"• Time-stop/force-closed outcomes (last {window_days}d): <b>{invalid_count_30d}</b>\n\n"
			"<b>Execution</b>\n"
			f"• MT5 link success (last {window_days}d): <b>{success_mt5}/{total_mt5}</b> (<b>{mt5_rate:.1f}%</b>)\n\n"
			"<i>High untracked counts indicate lifecycle discovery or price-provider failure; they do not by themselves prove that another database is required.</i>"
		)
		await update.message.reply_text(msg, parse_mode="HTML")
	except Exception as exc:
		await update.message.reply_text(f"❌ ops health failed: {exc}")

from telegram import Update
from telegram.helpers import escape_markdown
from telegram.ext import ContextTypes
# --------- NOTIFICATION CUSTOMIZATION COMMAND ---------
@require_tier("PREMIUM")
async def notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Persist notification asset/timeframe/strategy preferences in the canonical profile.

	Usage:
	  /notify assets BTCUSDT,ETHUSDT
	  /notify timeframes 15m,1h
	  /notify strategies ema_trend,breakout
	  /notify clear
	  /notify
	"""
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = int(update.effective_user.id)
	args = [str(x).strip() for x in (context.args or []) if str(x).strip()]
	from db.session import get_session
	from services.user_intelligence import (
		get_user_trading_preferences,
		set_user_trading_preferences,
	)

	try:
		async with get_session(priority="interactive", label="notify.preferences", timeout_seconds=5) as session:
			prefs = await get_user_trading_preferences(session, user_id)
			if not args:
				lines = [
					"Notification preferences",
					"",
					f"Assets: {', '.join(prefs.preferred_assets) if prefs.preferred_assets else 'all profile-eligible assets'}",
					f"Timeframes: {', '.join(prefs.preferred_timeframes) if prefs.preferred_timeframes else 'profile defaults'}",
					f"Strategies: {', '.join(prefs.preferred_strategies) if prefs.preferred_strategies else 'all qualified strategies'}",
				]
				await update.message.reply_text("\n".join(lines))
				return

			cmd = args[0].lower()
			if cmd == "clear":
				prefs.preferred_assets = ()
				prefs.preferred_timeframes = ()
				prefs.preferred_strategies = ()
				message = "✅ Notification preferences cleared. Profile and tier gates still apply."
			else:
				if len(args) < 2 or cmd not in {"assets", "timeframes", "strategies"}:
					await update.message.reply_text(
						"Usage: /notify assets|timeframes|strategies <comma-separated-list> OR /notify clear"
					)
					return
				values = [x.strip() for x in " ".join(args[1:]).split(",") if x.strip()]
				if cmd == "assets":
					prefs.preferred_assets = tuple(dict.fromkeys(x.upper() for x in values))
					message = f"✅ Assets updated: {', '.join(prefs.preferred_assets)}"
				elif cmd == "timeframes":
					prefs.preferred_timeframes = tuple(dict.fromkeys(x.lower() for x in values))
					message = f"✅ Timeframes updated: {', '.join(prefs.preferred_timeframes)}"
				else:
					prefs.preferred_strategies = tuple(dict.fromkeys(x.lower() for x in values))
					message = f"✅ Strategies updated: {', '.join(prefs.preferred_strategies)}"
			await set_user_trading_preferences(session, user_id, prefs)
			await session.commit()
		await update.message.reply_text(message)
	except TimeoutError:
		await update.message.reply_text("Notification preferences are temporarily busy. Please retry /notify.")
	except Exception as exc:
		logger.exception("[notify] preference update failed user=%s", user_id)
		await update.message.reply_text(f"Could not update notification preferences: {type(exc).__name__}")
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
			async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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
		if state.rate_limited_sync(
			user_id,
			limit=int(PUBLIC_COMMAND_RATE_LIMIT["limit"]),
			window_seconds=int(PUBLIC_COMMAND_RATE_LIMIT["window_seconds"]),
		):
			await update.message.reply_text("Rate limit exceeded. Please wait.")
			return True
	except Exception:
		pass
	return False



def _help_page_definitions() -> dict[int, dict[str, object]]:
	from signalrank_telegram.command_catalog import COMMANDS

	pages: dict[int, dict[str, object]] = {
		1: {"title": "🟢 Commands available now", "required_tier": "FREE", "commands": [], "footer": "Only functional launch commands are listed."},
		2: {"title": "⭐ Premium commands", "required_tier": "PREMIUM", "commands": [], "footer": "Premium includes Free commands plus detailed analytics and broker setup."},
		3: {"title": "💎 VIP commands", "required_tier": "VIP", "commands": [], "footer": "VIP includes evidence-based simulation and priority features."},
		4: {"title": "🛡 Admin operations", "required_tier": "ADMIN", "commands": [], "footer": "Restricted and audited. Never displayed to ordinary users."},
		5: {"title": "👑 Owner controls", "required_tier": "OWNER", "commands": [], "footer": "Restricted to configured owner identities."},
	}
	page_by_tier = {"FREE": 1, "PREMIUM": 2, "VIP": 3, "ADMIN": 4, "OWNER": 5}
	for spec in COMMANDS:
		page = page_by_tier.get(str(spec.tier).upper(), 1)
		pages[page]["commands"].append((f"/{spec.name}", spec.description))
	return pages

def _help_authorized_pages(user_id: int) -> list[int]:
	pages = [1, 2, 3]
	try:
		uid = int(user_id)
		if uid in ADMIN_IDS:
			pages.append(4)
		if uid in OWNER_IDS:
			pages.extend((4, 5))
	except Exception:
		pass
	return pages


def _help_page_is_locked(user_id: int, page: int) -> bool:
	tier = _effective_tier(int(user_id))
	page_defs = _help_page_definitions()
	page_info = page_defs.get(int(page), {})
	required_tier = str(page_info.get("required_tier") or "FREE")
	if int(page) in {4, 5}:
		try:
			uid = int(user_id)
			if int(page) == 5:
				return uid not in OWNER_IDS
			return uid not in ADMIN_IDS and uid not in OWNER_IDS
		except Exception:
			return True
	return tier_rank(tier) < tier_rank(required_tier)


def _build_help_pagination_keyboard(user_id: int, page: int):
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		authorized_pages = _help_authorized_pages(int(user_id))
		if page not in authorized_pages:
			page = authorized_pages[0]
		index = authorized_pages.index(page)
		rows = []
		jump_row = []
		for allowed_page in authorized_pages:
			label = f"• {allowed_page} •" if allowed_page == page else str(allowed_page)
			jump_row.append(InlineKeyboardButton(label, callback_data=f"help_page_{allowed_page}"))
		if jump_row:
			rows.append(jump_row)
		nav_row = []
		if index > 0:
			nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"help_page_{authorized_pages[index - 1]}"))
		if index < len(authorized_pages) - 1:
			nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"help_page_{authorized_pages[index + 1]}"))
		if nav_row:
			rows.append(nav_row)
		rows.append([
			InlineKeyboardButton("⚙️ Account", callback_data="nav_account"),
			InlineKeyboardButton("💳 Upgrade", callback_data="nav_upgrade"),
		])
		return InlineKeyboardMarkup(rows)
	except Exception:
		return None


async def _compose_help_page(user_id: int, page: int) -> tuple[str, object | None]:
	page_defs = _help_page_definitions()
	authorized_pages = _help_authorized_pages(int(user_id))
	if int(page) not in authorized_pages:
		page = authorized_pages[0]
	page_info = page_defs[int(page)]
	locked = _help_page_is_locked(int(user_id), int(page))
	commands = page_info.get("commands") or []
	lines = [
		f"{page_info['title']} — Page {page}/{authorized_pages[-1]}",
		"",
	]
	for cmd_name, desc in commands:
		prefix = "🔒 " if locked and int(page) in {2, 3} else "• "
		lines.append(f"{prefix}{cmd_name} — {desc}")
	footer = str(page_info.get("footer") or "")
	if locked and int(page) == 3 and tier_rank(_effective_tier(int(user_id))) >= tier_rank("PREMIUM"):
		footer = "💎 Upgrade to VIP to unlock these features."
	if footer:
		lines.extend(["", footer])
	keyboard = _build_help_pagination_keyboard(int(user_id), int(page))
	return "\n".join(lines), keyboard


async def help_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	if query is None or update.effective_user is None:
		return
	try:
		await query.answer()
	except Exception:
		pass
	data = str(query.data or "")
	try:
		page = int(data.rsplit("_", 1)[-1])
	except Exception:
		page = 1
	if page == 4:
		try:
			uid = int(update.effective_user.id)
			if uid not in ADMIN_IDS and uid not in OWNER_IDS:
				await query.answer("Access denied.", show_alert=True)
				return
		except Exception:
			return
	text, keyboard = await _compose_help_page(int(update.effective_user.id), int(page))
	try:
		await query.edit_message_text(text=text, reply_markup=keyboard)
	except Exception:
		pass


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	text, keyboard = await _compose_help_page(int(update.effective_user.id), 1)
	await update.message.reply_text(text, reply_markup=keyboard)


async def nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Handle inline navigation buttons used in /help and major command UIs."""
	query = update.callback_query
	if query is None:
		return
	try:
		await query.answer()
	except Exception:
		pass
	data = str(query.data or "")
	# Allow callback-driven command execution by reusing handlers.
	if data == "nav_home":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_main_menu_message(int(uid))
			await query.edit_message_text(text=msg, reply_markup=keyboard)
			return
		except Exception:
			return
	if data == "nav_signals":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_signals_menu_message(int(uid))
			await query.edit_message_text(text=msg, reply_markup=keyboard)
			return
		except Exception:
			return
	if data == "nav_performance":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_performance_menu_message(int(uid))
			await query.edit_message_text(text=msg, reply_markup=keyboard)
			return
		except Exception:
			return
	if data == "nav_account":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_status_message(int(uid))
			await _edit_message_or_reply(query, msg, keyboard)
			return
		except Exception:
			return
	if data == "nav_upgrade":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_upgrade_message(int(uid))
			await _edit_message_or_reply(query, msg, keyboard)
			return
		except Exception:
			return
	if data == "nav_support":
		try:
			uid = update.effective_user.id if update.effective_user else None
			if uid is None:
				return
			msg, keyboard = await _compose_support_menu_message(int(uid))
			await query.edit_message_text(text=msg, reply_markup=keyboard)
			return
		except Exception:
			return

# --------- MYID COMMAND ---------
async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	msg: str = f"Your Telegram user ID: `{user_id}`\nYour current tier: *{tier}*"
	await update.message.reply_text(msg, parse_mode="MarkdownV2")

# --------- DASHBOARD COMMAND ---------
@require_tier("PREMIUM")
async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show an inline bot dashboard — stats, execution mode, tier, quick links."""
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)

	try:
		from db.session import get_session, get_engine_for_event_loop
		from db.models import User, Signal, SignalDelivery, Outcome
		from db.pg_features import get_user_performance_30d
		from sqlalchemy import select, func, text
		from datetime import datetime, timedelta

		# If a web dashboard URL is configured, send premium users to it
		base_url = os.getenv("DASHBOARD_URL", "").strip()
		if base_url and tier.upper() in {"PREMIUM", "VIP", "ADMIN", "OWNER"}:
			sep = "&" if "?" in base_url else "?"
			url = f"{base_url}{sep}uid={user_id}"
			try:
				from telegram import InlineKeyboardMarkup, InlineKeyboardButton
				kbd = InlineKeyboardMarkup([[
					InlineKeyboardButton("🌐 Open Dashboard", url=url),
					InlineKeyboardButton("📊 Portfolio", callback_data="nav_portfolio"),
				]])
			except Exception:
				kbd = None
			await update.message.reply_text(
				f"🌐 <b>Your Dashboard</b>\n\n"
				f"Tier: <b>{tier.upper()}</b>\n"
				f"Tap the button below to open your full dashboard.",
				parse_mode="HTML",
				reply_markup=kbd,
			)
			return

		if get_engine_for_event_loop() is None:
			await update.message.reply_text(
				"📊 <b>Dashboard</b>\n\n"
				f"Tier: <b>{tier.upper()}</b>\n\n"
				"Use /stats, /portfolio, /mystats and /performance for your trading data.",
				parse_mode="HTML",
			)
			return

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			user_row = (await session.execute(
				select(User).where(User.telegram_user_id == user_id)
			)).scalar_one_or_none()

			cutoff = now_utc_naive() - timedelta(days=30)
			db_user_id = user_row.id if user_row else None

			# Signals received in last 30d
			total_signals = 0
			wins = 0
			losses = 0
			partial_wins = 0
			breakeven = 0
			expired = 0
			cancelled = 0
			missed_entry = 0
			tracking_failed = 0
			active_signals = 0
			outcome_pending = 0
			tracked = 0
			completed = 0
			outcome_coverage = 0.0
			completion_rate = 0.0
			open_limit_per_asset = 20
			open_limit_per_class = 20
			class_usage_txt = "N/A"
			asset_usage_txt = "N/A"
			try:
				open_limit_per_asset = max(1, int((os.getenv("OPEN_SIGNALS_MAX_PER_ASSET", "20") or "20").strip()))
				open_limit_per_class = max(1, int((os.getenv("OPEN_SIGNALS_MAX_PER_CLASS", "20") or "20").strip()))
			except Exception:
				open_limit_per_asset = 20
				open_limit_per_class = 20

			def _asset_class(sym: str) -> str:
				s = str(sym or "").upper().strip()
				if s.endswith(("USDT", "BUSD", "USDC", "BTC", "ETH")):
					return "crypto"
				if len(s) == 6 and s.isalpha():
					return "fx"
				if s in {"XAUUSD", "XAGUSD", "WTI", "BRENT", "CL=F", "GC=F", "SI=F"}:
					return "commodity"
				if s in {"DXY", "VIX", "US30", "NAS100", "SPX500", "SPY", "QQQ"}:
					return "index"
				return "stock"

			asset_open_counts: dict[str, int] = {}
			class_open_counts: dict[str, int] = {"crypto": 0, "fx": 0, "commodity": 0, "index": 0, "stock": 0}
			if db_user_id:
				stats = await get_user_performance_30d(session, int(user_id))
				total_signals = int((stats or {}).get("total") or 0)
				wins = int((stats or {}).get("terminal_wins", (stats or {}).get("wins", 0)) or 0)
				losses = int((stats or {}).get("losses") or 0)
				partial_wins = int((stats or {}).get("partial_wins") or 0)
				breakeven = int((stats or {}).get("breakeven") or 0)
				expired = int((stats or {}).get("expired") or (stats or {}).get("time_stops") or 0)
				cancelled = int((stats or {}).get("cancelled") or 0)
				missed_entry = int((stats or {}).get("missed_entry") or 0)
				tracking_failed = int((stats or {}).get("tracking_failed") or 0)
				active_signals = int((stats or {}).get("active") or 0)
				outcome_pending = int((stats or {}).get("outcome_pending") or 0)
				tracked = int((stats or {}).get("tracked_outcomes") or 0)
				completed = int((stats or {}).get("completed_outcomes") or 0)
				outcome_coverage = float((stats or {}).get("outcome_coverage") or 0.0) * 100.0
				completion_rate = float((stats or {}).get("completion_rate") or 0.0) * 100.0
				user_asset_rows = (await session.execute(
					text(
						"""
						WITH delivered AS (
							SELECT DISTINCT sd.signal_id, s.asset, s.status, s.expired, s.archived, s.expires_at
							FROM signal_deliveries sd
							JOIN signals s ON s.signal_id = sd.signal_id
							WHERE sd.user_id = :uid
							  AND sd.sent_ok IS TRUE
							  AND sd.delivered_at >= :cutoff
							  AND COALESCE(s.performance_version, 1) >= :performance_version
						),
						resolved AS (
							SELECT DISTINCT signal_id
							FROM outcomes
							WHERE LOWER(COALESCE(canonical_outcome, status, '')) IN (
								'tp','tp3','win','sl','loss','stop_loss','expired','time_stop','cancelled','canceled','superseded','missed','missed_entry','entry_missed'
							)
						)
						SELECT asset, COUNT(*) AS n
						FROM delivered d
						LEFT JOIN resolved r ON r.signal_id = d.signal_id
						WHERE r.signal_id IS NULL
						  AND COALESCE(d.archived, FALSE) IS FALSE
						  AND COALESCE(d.expired, FALSE) IS FALSE
						  AND (d.expires_at IS NULL OR d.expires_at >= NOW())
						GROUP BY asset
						ORDER BY n DESC, asset ASC
						"""
					)
					,
					{
						"uid": int(db_user_id),
						"cutoff": cutoff,
						"performance_version": max(1, int(os.getenv("PERFORMANCE_BASELINE_VERSION", "2") or 2)),
					},
				)).fetchall()
				for _asset, _count in user_asset_rows:
					_asset_key = str(_asset or "").upper().strip()
					_count_i = int(_count or 0)
					if not _asset_key:
						continue
					asset_open_counts[_asset_key] = _count_i
					_cls = _asset_class(_asset_key)
					class_open_counts[_cls] = int(class_open_counts.get(_cls, 0) + _count_i)
				if asset_open_counts:
					top_open = sorted(asset_open_counts.items(), key=lambda kv: kv[1], reverse=True)[:4]
					asset_usage_txt = " | ".join([f"{a} {c}/{open_limit_per_asset}" for a, c in top_open])
				else:
					asset_usage_txt = "No active delivered exposure"
			else:
				asset_open_rows = (await session.execute(
					select(Signal.asset, func.count(Signal.signal_id))
					.where(
						Signal.expired.is_(False),
						Signal.archived.is_(False),
					)
					.group_by(Signal.asset)
				)).fetchall()
				for _asset, _count in asset_open_rows:
					_asset_key = str(_asset or "").upper().strip()
					_count_i = int(_count or 0)
					if not _asset_key:
						continue
					asset_open_counts[_asset_key] = _count_i
					_cls = _asset_class(_asset_key)
					class_open_counts[_cls] = int(class_open_counts.get(_cls, 0) + _count_i)
				if asset_open_counts:
					top_open = sorted(asset_open_counts.items(), key=lambda kv: kv[1], reverse=True)[:4]
					asset_usage_txt = " | ".join([f"{a} {c}/{open_limit_per_asset}" for a, c in top_open])
			class_usage_txt = (
				f"CR {class_open_counts.get('crypto', 0)}/{open_limit_per_class} | "
				f"FX {class_open_counts.get('fx', 0)}/{open_limit_per_class} | "
				f"CM {class_open_counts.get('commodity', 0)}/{open_limit_per_class} | "
				f"IX {class_open_counts.get('index', 0)}/{open_limit_per_class} | "
				f"ST {class_open_counts.get('stock', 0)}/{open_limit_per_class}"
			)
			await session.commit()

		win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0.0
		exec_mode = str(getattr(user_row, "execution_mode", "manual") or "manual").upper() if user_row else "N/A"

		expiry_txt = ""
		if user_row:
			from datetime import timezone as _tz
			exp = getattr(user_row, "premium_until", None)
			if exp:
				if hasattr(exp, "tzinfo") and exp.tzinfo is None:
					exp = exp.replace(tzinfo=_tz.utc)
				expiry_txt = f"\n📅 Sub expires: <b>{exp.strftime('%d %b %Y')}</b>"

		msg = (
			f"<b>Dashboard - {tier.upper()}</b>\n\n"
			f"Signals delivered (30d): <b>{total_signals}</b>\n"
			f"Terminal wins: <b>{wins}</b> | Losses: <b>{losses}</b>\n"
			f"Completed win rate: <b>{win_rate:.1f}%</b> ({completed}/{total_signals})\n"
			f"Outcome coverage: <b>{outcome_coverage:.1f}%</b> ({tracked}/{total_signals})\n"
			f"Active: <b>{active_signals}</b> | Pending: <b>{outcome_pending}</b> | Completion: <b>{completion_rate:.1f}%</b>\n"
			f"Partial: <b>{partial_wins}</b> | BE: <b>{breakeven}</b> | Expired: <b>{expired}</b> | Missed: <b>{missed_entry}</b> | Failed: <b>{tracking_failed}</b> | Cancelled: <b>{cancelled}</b>\n"
			f"Open caps: <b>Asset {open_limit_per_asset}</b> | <b>Class {open_limit_per_class}</b>\n"
			f"Class usage: <b>{class_usage_txt}</b>\n"
			f"Asset usage: <b>{asset_usage_txt}</b>\n"
			f"Execution mode: <b>{exec_mode}</b>"
			f"{expiry_txt}\n\n"
			"<b>Quick commands:</b>\n"
			"/portfolio — live P&amp;L\n"
			"/mystats — full stats\n"
			"/history — signal history\n"
			"/performance — 30-day review\n"
			"/tiers — subscription info"
		)

		try:
			from telegram import InlineKeyboardMarkup, InlineKeyboardButton
			kbd = InlineKeyboardMarkup([
				[
					InlineKeyboardButton("📊 Portfolio", callback_data="nav_portfolio"),
					InlineKeyboardButton("📈 Performance", callback_data="nav_performance"),
				],
				[
					InlineKeyboardButton("⚙️ Execution", callback_data="nav_execution"),
					InlineKeyboardButton("🚀 Upgrade", callback_data="nav_upgrade"),
				],
			])
		except Exception:
			kbd = None

		await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kbd)

	except Exception as exc:
		await update.message.reply_text(
			"📊 <b>Dashboard</b>\n\n"
			f"Tier: <b>{tier.upper()}</b>\n\n"
			"Use /stats, /portfolio, /mystats, /performance for your trading data.",
			parse_mode="HTML",
		)


async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Fast delivered-signal index for the current user.

	This command must remain responsive during engine/delivery bursts. It uses a
	bounded interactive DB read and returns a compact index instead of rendering
	large cards. Full detail remains available through /signal <reference> or the
	inline Open buttons.
	"""
	if await _public_guard(update):
		return
	message = getattr(update, "message", None)
	if message is None and getattr(update, "callback_query", None) is not None:
		message = getattr(update.callback_query, "message", None)
	if message is None or update.effective_user is None:
		return
	user_id = int(update.effective_user.id)

	def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 200) -> int:
		try:
			return max(minimum, min(maximum, int(float(os.getenv(name, str(default)) or default))))
		except Exception:
			return default

	def _env_float(name: str, default: float, minimum: float = 1.0, maximum: float = 60.0) -> float:
		try:
			return max(minimum, min(maximum, float(os.getenv(name, str(default)) or default)))
		except Exception:
			return default

	args_norm = [str(x or "").strip() for x in (getattr(context, "args", []) or []) if str(x or "").strip()]
	status_filter = "active"
	lookback_days = _env_int("SIGNALS_COMMAND_LOOKBACK_DAYS", 7, 1, 30)
	limit = _env_int("SIGNALS_COMMAND_LIMIT", 8, 1, 25)
	asset_filter: str | None = None
	show_unvoted_only = False
	try:
		for idx, raw in enumerate(args_norm):
			token = raw.lower()
			if token in {"unvoted", "pending", "notvoted"}:
				show_unvoted_only = True
			elif token in {"active", "running", "closed", "all", "winners", "losers", "missed"}:
				status_filter = "active" if token == "running" else token
			elif token in {"today", "24h"}:
				lookback_days = 1
			elif token in {"week", "7d", "7days"}:
				lookback_days = 7
			elif token in {"30d", "30days", "month"}:
				lookback_days = 30
			elif token == "asset" and idx + 1 < len(args_norm):
				asset_filter = args_norm[idx + 1].upper().strip()
	except Exception:
		pass

	from signalrank_telegram.command_resilience import command_response_cache

	cache_key = ":".join([
		"signals",
		str(user_id),
		str(status_filter),
		str(lookback_days),
		str(limit),
		str(asset_filter or "*"),
		"unvoted" if show_unvoted_only else "all",
	])

	async def _reply_with_cached_response() -> bool:
		cached = command_response_cache.get(cache_key)
		if cached is None or not isinstance(cached.value, dict):
			return False
		payload = cached.value
		text = str(payload.get("text") or "")
		if not text:
			return False
		age = max(1, int(round(cached.age_seconds)))
		text = f"{text}\n\nCached {age}s ago; live data is temporarily busy."
		button_rows = []
		try:
			from telegram import InlineKeyboardButton, InlineKeyboardMarkup

			for row in list(payload.get("buttons") or []):
				button_rows.append([
					InlineKeyboardButton(str(label), callback_data=str(callback_data))
					for label, callback_data in row
				])
			markup = InlineKeyboardMarkup(button_rows) if button_rows else None
		except Exception:
			markup = None
		await message.reply_text(text, reply_markup=markup)
		return True

	try:
		from telegram import InlineKeyboardButton, InlineKeyboardMarkup
		from db.priority import DBPriority
		from db.pg_features import list_delivered_signals_for_user

		async def _query_rows():
			# Interactive command path gets the reserved foreground read lane. The
			# outer wait_for bounds the query itself as well as admission.
			async with get_session(priority=DBPriority.INTERACTIVE) as session:
				rows = await list_delivered_signals_for_user(
					session,
					telegram_user_id=int(user_id),
					lookback_days=int(lookback_days),
					status_filter=str(status_filter),
					asset=asset_filter,
					limit=int(limit),
					sent_ok_only=True,
				)
				await session.commit()
				return list(rows or [])

		db_timeout = _env_float("SIGNALS_COMMAND_DB_TIMEOUT_SECONDS", 6.0, 2.0, 20.0)
		rows = await asyncio.wait_for(_query_rows(), timeout=db_timeout)

		# Optional unvoted filter. Keep it bounded and skip it if the DB is busy;
		# /signals must never hang behind engagement analytics.
		if show_unvoted_only and rows:
			try:
				from sqlalchemy import select
				from db.models import SignalEngagement, User
				async def _engaged_ids():
					async with get_session(priority=DBPriority.INTERACTIVE) as session:
						user_row = (await session.execute(
							select(User).where(User.telegram_user_id == int(user_id)).limit(1)
						)).scalar_one_or_none()
						if user_row is None:
							return set()
						signal_ids = [str(getattr(r, "signal_id", "") or "") for r in rows]
						engaged_rows = await session.execute(
							select(SignalEngagement.signal_id)
							.where(SignalEngagement.user_id == int(user_row.id), SignalEngagement.signal_id.in_(signal_ids))
						)
						await session.commit()
						return {str(x) for x in (engaged_rows.scalars().all() or [])}
				engaged = await asyncio.wait_for(_engaged_ids(), timeout=min(3.0, db_timeout))
				rows = [r for r in rows if str(getattr(r, "signal_id", "") or "") not in engaged]
			except Exception as filter_err:
				_audit_logger.info("[signals_command] unvoted filter skipped user=%s err=%s", user_id, filter_err)

		if not rows:
			asset_txt = f" for {asset_filter}" if asset_filter else ""
			empty_text = f"No {status_filter} delivered signals{asset_txt} in the last {lookback_days} day(s)."
			command_response_cache.set(cache_key, {"text": empty_text, "buttons": []})
			await message.reply_text(empty_text)
			return

		button_rows = []
		button_specs = []
		lines = [
			f"📊 Your {status_filter.title()} Signals",
			f"{len(rows)} shown from the last {lookback_days} day(s)",
			"",
		]
		for idx, r in enumerate(rows, 1):
			ref = str(getattr(r, "signal_id", "") or "")
			score = float(getattr(r, "score", 0.0) or 0.0)
			asset = str(getattr(r, "asset", "") or "?")
			direction = str(getattr(r, "direction", "") or "?").upper()
			tf = str(getattr(r, "timeframe", "") or "?")
			lines.append(f"{idx}. {asset} {direction} {tf} | {score:.1f}% | {ref[:12]}")
			if ref and idx <= 8:
				button_text = f"Open {asset} {direction}"
				callback_data = f"open_signal_{ref}"
				button_rows.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
				button_specs.append([(button_text, callback_data)])
		lines.extend(["", "Open details with /signal <reference> or tap a button."])
		response_text = "\n".join(lines)
		command_response_cache.set(cache_key, {"text": response_text, "buttons": button_specs})
		await message.reply_text(response_text, reply_markup=InlineKeyboardMarkup(button_rows) if button_rows else None)
	except asyncio.TimeoutError:
		_audit_logger.warning("[signals_command] fast query timed out user=%s timeout_s=%s", user_id, os.getenv("SIGNALS_COMMAND_DB_TIMEOUT_SECONDS"))
		if not await _reply_with_cached_response():
			await message.reply_text("⚠️ /signals is busy because delivery/storage is active. Try again in a moment; signal delivery is still running.")
	except Exception as exc:
		_audit_logger.exception("[signals_command] failed user=%s err=%s", user_id, exc)
		if not await _reply_with_cached_response():
			await message.reply_text(f"⚠️ Could not load /signals right now: {type(exc).__name__}. Try again shortly.")


async def proof_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show a free-friendly proof feed with recent verified outcomes."""
	if await _public_guard(update):
		return
	if update.message is None:
		return
	try:
		from datetime import datetime, timedelta, timezone
		from sqlalchemy import select, func
		from db.models import Signal, Outcome
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton

		cutoff = datetime.now(timezone.utc) - timedelta(days=30)
		tp_statuses = {"tp", "tp1", "tp2", "tp3"}
		loss_statuses = {"sl"}

		recent_rows = []
		wins = 0
		losses = 0
		engine = get_engine_for_event_loop()
		if engine is not None:
			async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
				try:
					recent_rows = (
						await session.execute(
							select(Signal.asset, Signal.timeframe, Outcome.status)
							.join(Outcome, Outcome.signal_id == Signal.signal_id)
							.where(Signal.created_at >= cutoff)
							.where(func.lower(Outcome.status).in_(tp_statuses.union(loss_statuses)))
							.order_by(Signal.created_at.desc())
							.limit(5)
						)
					).all()
				except Exception as _recent_err:
					logger.debug(f"[proof] recent rows query failed: {_recent_err}")
					recent_rows = []

				try:
					summary_rows = (
						await session.execute(
							select(Outcome.status, func.count(Outcome.id))
							.join(Signal, Signal.signal_id == Outcome.signal_id)
							.where(Signal.created_at >= cutoff)
							.where(func.lower(Outcome.status).in_(tp_statuses.union(loss_statuses)))
							.group_by(Outcome.status)
						)
					).all()
					for status, count in summary_rows:
						st = str(status or "").lower()
						if st in tp_statuses:
							wins += int(count or 0)
						elif st in loss_statuses:
							losses += int(count or 0)
				except Exception as _summary_err:
					logger.debug(f"[proof] summary query failed: {_summary_err}")

		total = wins + losses
		win_rate = (wins / total * 100.0) if total > 0 else 0.0
		lines = [
			"✅ <b>Proof Feed</b>",
			"Recent verified outcomes to show real performance quality.",
			"",
			f"📊 Last 30d tracked outcomes: <b>{total}</b>",
			f"✅ Wins: <b>{wins}</b>   ❌ Losses: <b>{losses}</b>   🎯 Win rate: <b>{win_rate:.1f}%</b>",
			"",
			"🔎 Latest verified outcomes:",
		]
		if recent_rows:
			for asset, timeframe, status in recent_rows:
				st = str(status or "").upper()
				tag = "✅" if str(status or "").lower().startswith("tp") else "❌"
				lines.append(f"{tag} {asset} • {timeframe} • {st}")
		else:
			lines.append("No verified outcomes yet in this window.")
		lines.extend([
			"",
			"⚠️ Trading risk is real. No guaranteed returns.",
		])
		keyboard = InlineKeyboardMarkup([
			[InlineKeyboardButton("📊 View Signals", callback_data="nav_signals")],
			[InlineKeyboardButton("🚀 Upgrade", callback_data="nav_upgrade")],
		])
		await update.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
	except Exception as e:
		_audit_logger.error(f"Error in proof command: {e}")
		await update.message.reply_text("⚠️ Proof feed is temporarily unavailable. Please try again shortly.")


async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	arg: str = (context.args[0] if context.args else "").strip() if context.args else ""
	if not arg:
		await update.message.reply_text("Usage: /signal <reference>\nUse /signals to list your active signals.")
		return
	if arg.lower() in {"all", "active", "list"}:
		await update.message.reply_text("Use /signals to list your active signals, or /signal <reference> for one signal.")
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

	async def _current_price(asset: str) -> float | None:
		"""Fetch current price from live market data. Supports crypto, FX, and stocks."""
		try:
			from data.fetcher import async_get_candles, get_asset_type
			
			asset_type: str = get_asset_type(asset)
			if asset_type not in {"crypto", "fx", "stock"}:
				asset_type = "crypto"
			
			# Try short timeframes first; fall back if unavailable
			candles = []
			for tf in ("1m", "5m", "15m"):
				candles = await async_get_candles(asset, tf)
				if candles:
					break
			
			if not candles:
				# Last-resort fallbacks per asset type
				# 1) Crypto: Try Bybit spot tickers, then Yahoo last close
				try:
					atype: str = asset_type
					if atype == "crypto":
						# Bybit spot ticker (async)
						import httpx
						sym: str = (asset or "").upper().replace("/", "").replace("-", "")
						if sym.endswith("USD") and not sym.endswith("USDT"):
							sym: str = sym[:-3] + "USDT"
						url = "https://api.bybit.com/v5/market/tickers"
						params: dict[str, str] = {"category": "spot", "symbol": sym}
						try:
							async with httpx.AsyncClient(timeout=8) as client:
								resp = await client.get(url, params=params)
							data = resp.json() if resp.is_success else {}
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
							tkr = await asyncio.to_thread(yf.Ticker, ysym)
							h = await asyncio.to_thread(tkr.history, period="1d", interval="1m")
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
							tkr = await asyncio.to_thread(yf.Ticker, ysym)
							h = await asyncio.to_thread(tkr.history, period="1d", interval="1m")
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
		from db.pg_features import list_unresolved_signals_for_user, get_delivered_signal_by_ref
		from .formatter import format_signal, format_signal_free_limited
		# /signal lookup must remain delivery-first; pg_features enforces
		# SignalDelivery.sent_ok.is_(True) before exposing a signal to the user.

		if arg.lower() == "all":
			async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
				rows: list[Signal] = await list_unresolved_signals_for_user(session, telegram_user_id=int(user_id))
				await session.commit()
			if not rows:
				await update.message.reply_text("No active unresolved signals in the last 24h.")
				return
			lines: list[str] = ["📌 Active signals (last 24h):", ""]
			for s in rows[:20]:
				ref = str(getattr(s, "signal_id", "") or "")
				lines.append(f"• {ref} — {s.asset} {s.timeframe} {s.direction}")
			await update.message.reply_text("\n".join(lines))
			return

		display_timezone = None
		delivered_at = None
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			sig: Signal | None = await get_delivered_signal_by_ref(session, telegram_user_id=int(user_id), ref=str(arg))
			oc = None
			if sig is not None:
				try:
					from sqlalchemy import select
					from db.models import SignalDelivery, User
					delivery_row = (await session.execute(
						select(SignalDelivery, User.timezone)
						.join(User, User.id == SignalDelivery.user_id)
						.where(
							SignalDelivery.signal_id == str(sig.signal_id),
							User.telegram_user_id == int(user_id),
							SignalDelivery.sent_ok.is_(True),
						)
						.order_by(SignalDelivery.delivered_at.desc())
						.limit(1)
					)).first()
					if delivery_row is not None:
						delivery, user_timezone = delivery_row
						display_timezone = delivery.display_timezone or user_timezone
						delivered_at = delivery.delivered_at_utc or delivery.delivered_at
				except Exception:
					pass
				try:
					from db.pg_features import get_outcome_for_signal
					oc: Outcome | None = await get_outcome_for_signal(session, str(sig.signal_id))
				except Exception:
					oc = None
			await session.commit()
		if sig is None:
			await update.message.reply_text("Signal not found (or not delivered to you).")
			return

		if oc is None:
			try:
				from datetime import datetime, timezone
				expires_at = getattr(sig, "expires_at", None)
				if expires_at is not None and getattr(expires_at, "tzinfo", None) is None:
					expires_at = expires_at.replace(tzinfo=timezone.utc)
				is_retired = bool(getattr(sig, "expired", False) or getattr(sig, "archived", False))
				is_retired = is_retired or bool(expires_at and expires_at <= datetime.now(timezone.utc))
				if is_retired:
					await update.message.reply_text("This signal is expired or superseded and is no longer active.")
					return
			except Exception:
				pass

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
			"delivered_at": delivered_at,
			"display_timezone": display_timezone,
			"display_telegram_user_id": int(user_id),
		}
		
		# Enrich signal with live price and apply the same timeframe/profile-aware
		# age policy used by final Telegram delivery. The older asset-class-only
		# check incorrectly marked 1d crypto signals stale after five minutes.
		staleness_warning = None
		try:
			from engine.price_validator import enrich_signal_with_live_price
			from engine.delivery_freshness import evaluate_signal_age
			
			sig_dict = enrich_signal_with_live_price(sig_dict)
			age_result = evaluate_signal_age(sig_dict)
			if not age_result.ok:
				age_minutes = float(age_result.age_minutes or 0.0)
				max_minutes = float(age_result.max_age_minutes or 0.0)
				staleness_warning = (
					"⚠️ Warning: Signal is outside its active opportunity window "
					f"({age_minutes:.0f}m > {max_minutes:.0f}m)"
				)
			elif (
				age_result.opportunity_remaining_pct is not None
				and age_result.opportunity_remaining_pct < 50.0
			):
				staleness_warning = (
					f"⏰ Signal age: {float(age_result.age_minutes or 0.0):.0f}m "
					f"({float(age_result.opportunity_remaining_pct):.0f}% of opportunity window remains)"
				)
		except Exception as e:
			import logging
			logging.getLogger(__name__).debug(f"Failed to check signal freshness: {e}")
		
		# Enrich with entry_status and current price
		entry: float | None = _as_float(sig_dict.get("entry"))
		sl: float | None = _as_float(sig_dict.get("stop_loss"))
		tp: float | None = _parse_tp(sig_dict.get("take_profit"))
		asset: str = str(sig_dict.get("asset") or "").upper()
		price = None
		entry_status = "UNKNOWN"
		position_lines: list[str] = []
		advice_line = ""
		
		if entry is not None and _is_crypto(asset):
			price: float | None = await _current_price(asset)
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
				price: float | None = await _current_price(str(sig_dict.get("asset") or ""))
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
			await update.message.reply_text(base, reply_markup=_build_signal_action_keyboard(sig_dict))
			return

		base: None | str = format_signal(sig_dict, user_tier=tier)
		if base is None:
			base = format_signal_free_limited(sig_dict)
		if staleness_warning:
			base = f"{staleness_warning}\n\n{base}"
		if position_lines or advice_line:
			base += "\n\n📍 Position (best-effort)\n" + "\n".join(position_lines)
			if advice_line:
				base += "\n\n🧠 Suggestion\n" + str(advice_line)
		await update.message.reply_text(base, parse_mode="HTML", reply_markup=_build_signal_action_keyboard(sig_dict))
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
	if update.effective_user is None:
		return
	if update.message is None and getattr(update, "callback_query", None) is not None:
		try:
			update.message = update.callback_query.message
		except Exception:
			pass
	if update.message is None:
		return

	user_id: int = update.effective_user.id
	arg: str = (context.args[0] if context.args else "").strip()
	action: str | None = None
	if len(context.args or []) > 1:
		action = str(context.args[1] or "").strip().upper()
	if not arg:
		try:
			from datetime import datetime, timedelta, timezone
			from sqlalchemy import select, func
			from db.session import get_engine_for_event_loop, get_session
			from db.models import Signal, Outcome, SignalDelivery, User
			user_tier = str(_effective_tier(int(user_id)) or "FREE").upper()
			if user_tier == "FREE":
				outcome_row_limit = max(1, int(os.getenv("OUTCOME_GLOBAL_FREE_LIMIT", str(FREE_PROOF_FEED_LIMIT)) or FREE_PROOF_FEED_LIMIT))
			elif user_tier in {"OWNER", "ADMIN"}:
				outcome_row_limit = max(10, int(os.getenv("OUTCOME_GLOBAL_ADMIN_OWNER_LIMIT", "50") or 50))
			else:
				outcome_row_limit = max(5, int(os.getenv("OUTCOME_GLOBAL_PAID_LIMIT", "30") or 30))
			engine = get_engine_for_event_loop()
			if engine is None:
				raise RuntimeError("Postgres not configured")
			cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
			recorded_at_expr = func.coalesce(Outcome.closed_at, Outcome.opened_at, Signal.created_at)
			async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
				user_row = (
					await session.execute(
						select(User.id).where(User.telegram_user_id == int(user_id)).limit(1)
					)
				).scalar_one_or_none()
				if user_row is None:
					await update.message.reply_text("📭 No recorded outcomes for you in the last 24 hours.")
					return
				rows = (
					await session.execute(
						select(
							Signal.signal_id,
							Signal.asset,
							Signal.timeframe,
							Signal.direction,
							Outcome.status,
							Outcome.r_multiple,
							Outcome.percent,
							recorded_at_expr.label("recorded_at"),
						)
						.join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
						.join(Outcome, Outcome.signal_id == Signal.signal_id)
						.where(
							SignalDelivery.user_id == int(user_row),
							recorded_at_expr >= cutoff,
						)
						.order_by(recorded_at_expr.desc())
						.limit(int(outcome_row_limit))
					)
				).all()
			if not rows:
				await update.message.reply_text("📭 No recorded outcomes for you in the last 24 hours.")
				return
			lines = [
				f"📣 Your outcomes (last 24h • showing {len(rows)} up to {int(outcome_row_limit)})",
				"",
			]
			for signal_id, asset, timeframe, direction, status, r_multiple, percent, recorded_at in rows:
				try:
					_ts = recorded_at if getattr(recorded_at, "tzinfo", None) is not None else recorded_at.replace(tzinfo=timezone.utc)
					ts_txt = _ts.strftime("%Y-%m-%d %H:%M UTC")
				except Exception:
					ts_txt = "unknown time"
				status_txt = str(status or "").upper()
				lines.append(f"• {str(signal_id)[:8]} | {asset} {timeframe} {str(direction).upper()} | {status_txt} | {ts_txt}")
				if r_multiple is not None or percent is not None:
					try:
						parts = []
						if r_multiple is not None:
							parts.append(f"{float(r_multiple):.2f}R")
						if percent is not None:
							parts.append(f"{float(percent):.2f}%")
						if parts:
							lines.append(f"  ↳ {' | '.join(parts)}")
					except Exception:
						pass
			lines.extend([
				"",
				"Use /outcome <reference> for a full single-signal breakdown.",
			])
			await update.message.reply_text("\n".join(lines))
			return
		except Exception:
			await update.message.reply_text(
				"Usage: /outcome <reference> [WIN|LOSS|CANCEL|TP1|TP2|TP3]"
			)
			return

	try:
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is None:
			raise RuntimeError("Postgres not configured")
		from db.pg_features import get_delivered_signal_by_ref, get_outcome_for_signal, get_or_create_user, upsert_outcome
		from db.models import Signal, User, Outcome
		from sqlalchemy import select
		import json

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			# Ensure user exists
			user: User = await get_or_create_user(session, telegram_user_id=int(user_id))

			# Look up delivered signal for this user
			sig: Signal | None = await get_delivered_signal_by_ref(session, telegram_user_id=int(user_id), ref=str(arg))

			if sig is None:
				# Admin/owner fallback still uses the canonical ambiguity-safe resolver.
				from db.signal_reference import (
					AmbiguousSignalReference,
					SignalReferenceNotFound,
					resolve_signal_reference,
				)
				try:
					undelivered_sig = (await resolve_signal_reference(session, arg)).signal
				except AmbiguousSignalReference:
					await update.message.reply_text(
						"That reference is ambiguous. Use the complete Signal ID."
					)
					return
				except SignalReferenceNotFound:
					await update.message.reply_text("Signal not found.")
					return
				if not _is_admin(user_id):
					await update.message.reply_text("⚠️ This is not your signal. You were not sent this trade.")
					return
				sig = undelivered_sig

			# Manual resolution (ADMIN/OWNER only)
			if action:
				if not _is_admin(user_id):
					await update.message.reply_text("⛔ Access Denied.")
					return
				_map = {
					"WIN": "tp",
					"LOSS": "sl",
					"CANCEL": "invalid",
					"TP1": "tp1",
					"TP2": "tp2",
					"TP3": "tp3",
				}
				status = _map.get(action)
				if status is None:
					await update.message.reply_text(
						"Invalid resolution. Use WIN, LOSS, CANCEL, TP1, TP2, or TP3."
					)
					return
				await upsert_outcome(
					session,
					str(sig.signal_id),
					status,
					meta={"manual": True, "by": int(user_id), "action": action},
				)
				await session.commit()
				await update.message.reply_text(
					f"✅ Outcome updated: {str(sig.signal_id)[:8]} → {status.upper()}"
				)
				# Continue to display current status below

			# Check outcome
			oc: Outcome | None = await get_outcome_for_signal(session, str(sig.signal_id))

		# Format and reply outside session where possible
		if oc is not None:
			status = str(getattr(oc, "status", "") or "").lower()

			r = getattr(oc, "r_multiple", None)
			pct = getattr(oc, "percent", None)
			label = "PROFIT ✅" if status.startswith("tp") else ("LOSS ❌" if status == "sl" else status.upper())
			progress = ""
			if status in {"tp1", "tp2", "tp3"}:
				progress = f"TP Progress: {status.upper()}"
			elif status == "tp":
				progress = "TP Progress: FULL TP"
			lines = [
				"📣 Outcome",
				"",
				signal_id_line(sig),
				f"{sig.asset} {sig.timeframe} {sig.direction.upper()}",
				f"Entry: {sig.entry}",
				f"Result: {label} ({status})",
			]
			if progress:
				lines.append(progress)
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

			try:
				from telegram import InlineKeyboardMarkup, InlineKeyboardButton
				keyboard = InlineKeyboardMarkup([
					[
						InlineKeyboardButton("📈 Signals", callback_data="nav_signals"),
						InlineKeyboardButton("📊 Performance", callback_data="nav_performance"),
					],
					[
						InlineKeyboardButton("🚀 Upgrade", callback_data="nav_upgrade"),
						InlineKeyboardButton("🆘 Support", callback_data="nav_support"),
					],
				])
			except Exception:
				keyboard = None
			await update.message.reply_text("\n".join(lines), reply_markup=keyboard)
			return

		# No outcome yet — show basic in-progress details
		lines = ["🔄 Signal In Progress", "", signal_id_line(sig)]
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
			tp_list: list = []
			if isinstance(tp_raw, str):
				try:
					tp_data = json.loads(tp_raw)
					if isinstance(tp_data, list) and tp_data:
						tp_list = list(tp_data)
						for i, tp in enumerate(tp_data, 1):
							lines.append(f"Take Profit {i}: {tp}")
					else:
						lines.append(f"Take Profit: {tp_raw}")
				except Exception:
					lines.append(f"Take Profit: {tp_raw}")
			elif tp_raw is not None:
				try:
					tp_list = list(tp_raw) if isinstance(tp_raw, (list, tuple)) else [tp_raw]
				except Exception:
					tp_list = []
				lines.append(f"Take Profit: {tp_raw}")
			if tp_list:
				lines.append(f"TP Progress: 0/{len(tp_list)}")
		except Exception:
			pass

		try:
			from telegram import InlineKeyboardMarkup, InlineKeyboardButton
			keyboard = InlineKeyboardMarkup([
				[
					InlineKeyboardButton("📈 Signals", callback_data="nav_signals"),
					InlineKeyboardButton("📊 Performance", callback_data="nav_performance"),
				],
				[
					InlineKeyboardButton("🚀 Upgrade", callback_data="nav_upgrade"),
					InlineKeyboardButton("🆘 Support", callback_data="nav_support"),
				],
			])
		except Exception:
			keyboard = None
		await update.message.reply_text("\n".join(lines), reply_markup=keyboard)
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
	user_id = int(update.effective_user.id)
	try:
		from db.session import get_session
		from db.pg_features import get_or_create_referral_code, get_referral_progress
		async with get_session(
			priority="interactive",
			label="referral.invite",
			timeout_seconds=8.0,
		) as session:
			code = await get_or_create_referral_code(
				session,
				referrer_telegram_user_id=user_id,
			)
			progress = await get_referral_progress(
				session,
				referrer_telegram_user_id=user_id,
			)
			await session.commit()
	except Exception as exc:
		logging.getLogger(__name__).exception(
			"[referral_invite_failed] user=%s error=%s",
			user_id,
			exc,
		)
		await update.message.reply_text(
			"⚠️ Your referral link could not be loaded right now. "
			"No temporary or invalid code was created. Please try /invite again."
		)
		return

	bot_username = None
	try:
		me = await context.bot.get_me()
		bot_username = str(getattr(me, "username", None) or "").strip().lstrip("@") or None
	except Exception:
		bot_username = (os.getenv("BOT_USERNAME") or "").strip().lstrip("@") or None

	requirement = int(progress.get("requirement", 3) or 3)
	toward = int(progress.get("toward_next", 0) or 0)
	need = int(progress.get("needed_for_next", requirement) or requirement)
	total = int(progress.get("total", 0) or 0)
	reward_days = int(progress.get("reward_days_per_3", 7) or 7)
	progress_line = (
		f"Progress: {toward}/{requirement} "
		f"(invite {need} more to earn +{reward_days} days Premium). "
		f"Total valid referrals: {total}."
	)

	if not bot_username:
		await update.message.reply_text(
			f"🎁 Your durable invite code: {code}\n\n"
			f"Reward: invite {requirement} new users → get +{reward_days} days Premium.\n"
			"Invite link is unavailable because the bot username could not be resolved.\n\n"
			+ progress_line
		)
		return

	link = f"https://t.me/{bot_username}?start=ref_{code}"
	await update.message.reply_text(
		f"🎁 Invite link:\n{link}\n\n"
		f"Reward: invite {requirement} new users → get +{reward_days} days Premium.\n\n"
		+ progress_line
	)

async def pricing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	msg, keyboard = await _compose_pricing_message(int(user_id))
	await update.message.reply_text(msg, parse_mode="HTML", reply_markup=keyboard)


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
	if update.effective_user is None:
		return
	if update.message is None and getattr(update, "callback_query", None) is not None:
		try:
			update.message = update.callback_query.message
		except Exception:
			pass
	if update.message is None:
		return
	user_id = update.effective_user.id
	msg, keyboard = await _compose_upgrade_message(int(user_id))
	from telegram.constants import ParseMode

	await update.message.reply_text(
		msg,
		parse_mode=ParseMode.HTML,
		reply_markup=keyboard,
	)


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
						session.add(VIPWaitlist(user_id=u.id, joined_at=now_utc_naive()))
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
	try:
		from core.paper_trading_service import paper_trading_service
		await paper_trading_service.ensure_account(int(user_id))
	except Exception as exc:
		logger.warning("[terms] paper account initialization deferred user=%s err=%s", user_id, exc)
	welcome = (
		"✅ <b>Welcome to SignalRankAI!</b>\n\n"
		"You're all set. Here's what you get:\n"
		"• Risk-managed signals filtered for high-probability setups\n"
		"• Outcome tracking - no hype, no guarantees\n"
		"• Real-time market coverage: Crypto, Forex, Stocks, Commodities\n\n"
		"Use /pricing to see plans, or /upgrade to subscribe.\n"
		"Use /signals to see the latest setups."
	)
	try:
		await query.edit_message_text(welcome, parse_mode="HTML")
	except Exception:
		try:
			if update.effective_chat:
				await context.bot.send_message(
					chat_id=update.effective_chat.id, text=welcome, parse_mode="HTML"
				)
		except Exception:
			pass
	try:
		if query.message is not None:
			await maybe_prompt_timezone(query.message, int(user_id))
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

		now = now_utc_naive()
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
		await update.message.reply_text(msg, parse_mode="MarkdownV2")

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

		import asyncio
		from telegram.error import RetryAfter
		broadcast_text = f"📢 *SignalRankAI*\n\n{msg_text}"
		sent = 0
		failed = 0
		for uid in user_ids:
			try:
				while True:
					try:
						await context.bot.send_message(
							chat_id=int(uid),
							text=broadcast_text,
							parse_mode="MarkdownV2",
						)
						break
					except RetryAfter as e:
						await asyncio.sleep(float(getattr(e, "retry_after", 1.0) or 1.0))
				await asyncio.sleep(0.5)
				sent += 1
			except Exception:
				failed += 1

		status_label = "Broadcast complete" if sent > 0 else "Broadcast failed: no users received the message"
		await update.message.reply_text(
			f"{status_label}.\n\nSent: {sent} | Failed: {failed}"
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
				import asyncio
				from telegram.error import RetryAfter
				while True:
					try:
						await context.bot.send_message(
							chat_id=int(uid),
							text=disclaimer,
							parse_mode="MarkdownV2",
							reply_markup=_kbd_bt,
						)
						break
					except RetryAfter as e:
						await asyncio.sleep(float(getattr(e, "retry_after", 1.0) or 1.0))
				await asyncio.sleep(0.5)
				sent += 1
			except Exception:
				failed += 1

		status_label = "Terms blast complete" if sent > 0 else "Terms blast failed: no users received the message"
		await update.message.reply_text(
			f"{status_label}.\n\nSent: {sent} | Failed: {failed}"
		)
		return

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
				import asyncio
				from telegram.error import RetryAfter
				while True:
					try:
						await context.bot.send_message(
							chat_id=int(uid),
							text=disclaimer,
							parse_mode="MarkdownV2",
							reply_markup=_kbd_bt,
						)
						break
					except RetryAfter as e:
						await asyncio.sleep(float(getattr(e, "retry_after", 1.0) or 1.0))
				await asyncio.sleep(0.5)
				sent += 1
			except Exception:
				failed += 1

		status_label = "Terms blast complete" if sent > 0 else "Terms blast failed: no users received the message"
		await update.message.reply_text(
			f"{status_label}.\n\nSent: {sent} | Failed: {failed}"
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
			async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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
		if state.rate_limited_sync(
			int(user_id),
			limit=int(START_COMMAND_RATE_LIMIT["limit"]),
			window_seconds=int(START_COMMAND_RATE_LIMIT["window_seconds"]),
		):
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
			import asyncio
			timeout_s = float((os.getenv("DB_START_TIMEOUT") or "20").strip())
			max_attempts = 2
			for attempt in range(1, max_attempts + 1):
				try:
					async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
						logger.info("[/start] user_id=%s — DB session open, querying user row (attempt=%s)", user_id, attempt)
						res = await asyncio.wait_for(
							session.execute(select(User).where(User.telegram_user_id == int(user_id))),
							timeout=timeout_s,
						)
						existing: User | None = res.scalar_one_or_none()
						is_new: bool = existing is None
						user_row = await asyncio.wait_for(
							get_or_create_user(session, telegram_user_id=user_id, username=username),
							timeout=timeout_s,
						)
						try:
							user_row.locale = getattr(update.effective_user, "language_code", None)
							if not getattr(user_row, "timezone", None) and int(user_id) in (set(OWNER_IDS or set()) | set(ADMIN_IDS or set())):
								from datetime import datetime, timezone as _timezone
								user_row.timezone = "Africa/Lagos"
								user_row.timezone_source = "country_default"
								user_row.timezone_updated_at = datetime.now(_timezone.utc).replace(tzinfo=None)
						except Exception:
							pass
						# Avoid nested DB resolution inside /start; use env-configured tiers only.
						try:
							if int(user_id) in OWNER_IDS:
								effective_tier = "OWNER"
							elif int(user_id) in ADMIN_IDS:
								effective_tier = "ADMIN"
							else:
								effective_tier = "FREE"
						except Exception:
							effective_tier = "FREE"
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
							await asyncio.wait_for(ensure_alert_prefs(session, int(user_id)), timeout=timeout_s)
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
							except Exception as referral_exc:
								logging.getLogger(__name__).exception(
									"[referral_start_failed] referred_user=%s code=%s is_new=%s error=%s",
									user_id,
									code,
									is_new,
									referral_exc,
								)
								referral_outcome = {
									"status": "processing_failed",
									"referrer_id": None,
									"days_granted": 0,
									"error_type": type(referral_exc).__name__,
								}

						# Audit: always record the start event when Postgres is available
						try:
							await asyncio.wait_for(record_bot_event(
								session,
								telegram_user_id=int(user_id),
								username=username,
								event_type="user_start",
								meta={
									"is_new": bool(is_new),
									"ref_token": str(ref_token) if ref_token else None,
									"referral": referral_outcome,
								},
							), timeout=timeout_s)
						except Exception:
							pass

						# Read accepted_terms before session closes (object becomes detached after commit)
						terms_accepted: bool = bool(getattr(user_row, "accepted_terms", False))

						await asyncio.wait_for(session.commit(), timeout=timeout_s)
						logger.info("[/start] user_id=%s — DB session commit complete (attempt=%s)", user_id, attempt)
						break
				except asyncio.TimeoutError:
					if attempt >= max_attempts:
						raise
					logger.warning("[/start] user_id=%s timeout on attempt=%s, retrying", user_id, attempt)
					await asyncio.sleep(1.0)
		else:
			raise RuntimeError("DATABASE_URL not configured. Postgres is required.")
	except Exception as e:
		try:
			from db.session import get_session as _gs_start
			async with _gs_start() as _s:
				await _s.rollback()
		except Exception:
			pass
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
		"Use /proof for verified outcomes, /pricing to see plans, or /upgrade to subscribe."
	)
	# Referral feedback (minimal, non-spammy)
	if referral_outcome and update.message is not None:
		status = str(referral_outcome.get("status"))
		if status in {"attributed", "reward_granted", "reward_already_granted"}:
			await update.message.reply_text("✅ Referral applied. Welcome!")
		elif status == "invalid_code":
			await update.message.reply_text("⚠️ Referral code not recognized.")
		elif status == "processing_failed":
			await update.message.reply_text(
				"⚠️ Your referral could not be verified because the database was busy. "
				"The failure was logged; please send the invite link to support if it persists."
			)
		# else: silent for self_referral/already_referred/not_new

	if upgrade_notice and update.message is not None:
		await update.message.reply_text(upgrade_notice)

	# Notify the referrer once. Reward details are already included in the
	# canonical referrer_message, so a milestone must not generate duplicates.
	try:
		if referral_outcome:
			status = str(referral_outcome.get("status") or "")
			referrer_raw = referral_outcome.get("referrer_id")
			referrer_msg = referral_outcome.get("referrer_message")
			if status in {"attributed", "reward_granted", "reward_capped"} and referrer_raw and referrer_msg:
				await context.bot.send_message(
					chat_id=int(referrer_raw),
					text=str(referrer_msg),
				)
	except Exception as referral_notify_exc:
		logging.getLogger(__name__).exception(
			"[referral_notification_failed] referred_user=%s outcome=%s error=%s",
			user_id,
			referral_outcome,
			referral_notify_exc,
		)

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
		# Use plain text here to avoid MarkdownV2 parsing failures that can drop /start replies.
		await update.message.reply_text(disclaimer, reply_markup=_kbd)
		return  # Hold back welcome message until terms are accepted

	# Terms already accepted — send normal welcome
	_tier = _effective_tier(int(user_id))
	_kbd_start = _build_dynamic_menu(user_id=int(user_id), tier=_tier)
	await update.message.reply_text(msg, reply_markup=_kbd_start)
	try:
		from core.paper_trading_service import paper_trading_service
		await paper_trading_service.ensure_account(int(user_id))
	except Exception as exc:
		logger.warning("[/start] paper account initialization deferred user=%s err=%s", user_id, exc)
	await maybe_prompt_timezone(update.message, int(user_id))

# /about message
async def about_command(update, context) -> None:
	"""Show platform capabilities plus this user's verified delivery totals."""
	if update.message is None or update.effective_user is None:
		return
	uid = int(update.effective_user.id)
	tier = _effective_tier(uid)
	delivered = active = completed = 0
	try:
		from sqlalchemy import func, select
		from db.models import Outcome, Signal, SignalDelivery, User
		async with get_session(priority="interactive", label="about.metrics", timeout_seconds=5) as session:
			user = (
				await session.execute(select(User).where(User.telegram_user_id == uid).limit(1))
			).scalar_one_or_none()
			if user is not None:
				delivered = int((await session.execute(
					select(func.count(func.distinct(SignalDelivery.signal_id))).where(
						SignalDelivery.user_id == int(user.id),
						SignalDelivery.sent_ok.is_(True),
						func.upper(SignalDelivery.delivery_state).in_(["CONFIRMED", "RECONCILED", "DELIVERED"]),
					)
				)).scalar() or 0)
				active = int((await session.execute(
					select(func.count(func.distinct(SignalDelivery.signal_id)))
					.join(Signal, Signal.signal_id == SignalDelivery.signal_id)
					.where(
						SignalDelivery.user_id == int(user.id),
						SignalDelivery.sent_ok.is_(True),
						func.upper(SignalDelivery.delivery_state).in_(["CONFIRMED", "RECONCILED", "DELIVERED"]),
						Signal.expired.is_(False),
						Signal.status.in_(["issued", "active", "open"]),
					)
				)).scalar() or 0)
				completed = int((await session.execute(
					select(func.count(func.distinct(Outcome.signal_id)))
					.join(SignalDelivery, SignalDelivery.signal_id == Outcome.signal_id)
					.where(
						SignalDelivery.user_id == int(user.id),
						SignalDelivery.sent_ok.is_(True),
						func.upper(SignalDelivery.delivery_state).in_(["CONFIRMED", "RECONCILED", "DELIVERED"]),
					)
				)).scalar() or 0)
	except Exception:
		logger.exception("[/about] metric query failed user=%s", uid)

	paper_line = "Paper account: unavailable"
	try:
		from core.paper_trading_service import paper_trading_service
		paper = await paper_trading_service.snapshot(uid)
		if paper is not None:
			paper_line = (
				f"Paper equity: <b>${paper.equity:,.2f}</b> • "
				f"open: <b>{paper.open_positions}</b> • auto: <b>{'ON' if paper.auto_trade_enabled else 'OFF'}</b>"
			)
	except Exception:
		logger.exception("[/about] paper snapshot failed user=%s", uid)

	try:
		from core.version import APP_VERSION
		version = APP_VERSION
	except Exception:
		version = str(os.getenv("APP_VERSION") or "current")

	msg = (
		"📊 <b>About SignalRankAI</b>\n\n"
		"SignalRankAI is a Telegram-first, multi-user trading-intelligence ecosystem. "
		"It combines multi-provider market data, multiple existing strategy families, "
		"asset-specific adaptive evidence, ML/AI review, news and regime filters, risk controls, "
		"verified Telegram delivery, lifecycle monitoring, and isolated paper trading.\n\n"
		"<b>Your account</b>\n"
		f"Tier: <b>{tier}</b>\n"
		f"Signals confirmed delivered to you: <b>{delivered}</b>\n"
		f"Currently active delivered signals: <b>{active}</b>\n"
		f"Completed delivered-signal outcomes: <b>{completed}</b>\n"
		f"{paper_line}\n\n"
		"<b>Markets</b>\n"
		"Crypto • Forex • Stocks • Indices • Commodities\n\n"
		"<b>Execution</b>\n"
		"Signals can be monitored or paper-traded without a broker. Optional MT5/MetaApi execution "
		"requires a linked, verified account, explicit consent, tier access, and a successful risk preflight. "
		"Use /mt5_status before pressing a trade button.\n\n"
		f"Build: <code>{version}</code>\n"
		"Support: @theocrilox\n\n"
		"Educational information only. Trading involves risk and profits are never guaranteed."
	)
	await update.message.reply_text(msg, parse_mode="HTML")

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
		"Free: Proof-oriented feed (up to 3/day) with limited details.\n"
		"Premium: Broader active feed with full Entry, SL, TP, and analytics.\n"
		"VIP: Stricter high-conviction feed with elite controls and priority delivery.\n\n"
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
async def performance_command(update, context) -> None:
	"""Show canonical proof-backed user performance, details, or an owner audit."""
	if await _public_guard(update):
		return
	if update.message is None and getattr(update, "callback_query", None) is not None:
		update.message = update.callback_query.message
	if update.message is None:
		return

	user_id = int(update.effective_user.id)
	tier = str(_effective_tier(user_id) or "free").lower()
	args = [str(value).strip().lower() for value in (getattr(context, "args", None) or [])]
	mode = args[0] if args else "30d"
	if mode in {"7d", "30d", "90d"}:
		days = int(mode[:-1])
	elif mode in {"details", "audit"}:
		days = 30
	else:
		await update.message.reply_text("Usage: /performance [7d|30d|90d|details|audit]")
		return
	if mode == "audit" and tier not in {"owner", "admin"}:
		await update.message.reply_text("Performance audit is restricted to owner/admin accounts.")
		return

	try:
		from db.session import get_engine_for_event_loop, get_session
		from services.performance_ledger import audit_user_performance, get_user_performance_report

		if get_engine_for_event_loop() is None:
			raise RuntimeError("database unavailable")
		async with get_session(priority="interactive", label="canonical_performance_command") as session:
			report = await get_user_performance_report(session, telegram_user_id=user_id, days=days)
			if mode == "audit":
				audit = await audit_user_performance(
					session, telegram_user_id=user_id, days=days, snapshot=report,
				)
			await session.commit()
	except Exception as exc:
		_audit_logger.exception("/performance canonical ledger failed user=%s: %s", user_id, exc)
		await update.message.reply_text(
			"Performance is temporarily unavailable because the proof-backed ledger could not be verified. "
			"No estimated or unverified fallback was shown."
		)
		return

	buckets = dict(report.get("buckets") or {})
	if mode == "details":
		rows = list(report.get("rows") or [])[-20:]
		lines = [
			f"Performance details ({days}d)",
			"Basis: confirmed delivery cohort; timestamps use UTC.",
			"",
		]
		for row in rows:
			r_value = "n/a" if row.final_realized_r is None else f"{float(row.final_realized_r):+.2f}R"
			lines.append(f"{row.signal_id[:8]}  {row.primary_bucket}  {r_value}")
		if not rows:
			lines.append("No proof-backed ledger rows in this window.")
		lines.extend(["", f"Reconciliation: {report.get('reconciliation_id', 'n/a')}"])
		await update.message.reply_text("\n".join(lines))
		return

	if mode == "audit":
		await update.message.reply_text(
			f"Performance audit ({int(audit.get('window_days') or days)}d)\n\n"
			f"Snapshot: {audit.get('snapshot_id')}\n"
			f"Reconciliation: {audit.get('reconciliation_id')}\n"
			f"Confirmed deliveries: {audit.get('confirmed_delivery_count', 0)}\n"
			f"Bucket sum: {audit.get('bucket_sum', 0)}\n"
			f"Invariant: {'PASS' if audit.get('invariant_ok') else 'FAIL'}\n"
			f"Non-finite finalized R rows: {len(audit.get('invalid_final_r') or [])}"
		)
		return

	if not report.get("invariant_ok"):
		await update.message.reply_text(
			"Performance is temporarily unavailable: the delivery-to-bucket reconciliation invariant failed."
		)
		return
	if not report.get("report_verified", False):
		await update.message.reply_text(
			"Performance is temporarily unavailable: one or more terminal ledger rows "
			"lack a verified realized-R value. No estimated fallback was shown."
		)
		return

	completed = int(report.get("completed_r_count") or 0)
	avg_r = report.get("avg_r")
	median_r = report.get("median_r")
	risk_pct = float(report.get("risk_fraction_pct") or 0.0)
	_report_status = "CERTIFIED" if report.get("performance_certified") else "PROVISIONAL — NOT FOR PUBLIC CLAIMS"
	lines = [
		f"Performance ({int(report.get('window_days') or days)}d) — {_report_status}",
		str(report.get("basis_label") or "Confirmed delivery cohort"),
		"",
		f"Confirmed deliveries: {int(report.get('delivered') or 0)}",
		f"Completed results with R: {completed}",
		f"TP3 / SL: {buckets.get('TP3', 0)} / {buckets.get('SL', 0)}",
		f"Stopped TP1 / TP2: {buckets.get('STOPPED_AT_TP1', 0)} / {buckets.get('STOPPED_AT_TP2', 0)}",
		f"Breakeven: {buckets.get('BREAKEVEN', 0)}",
		f"Active / pending entry: {buckets.get('ACTIVE', 0)} / {buckets.get('PENDING_ENTRY', 0)}",
		f"Missed / expired / cancelled: {buckets.get('MISSED_ENTRY', 0)} / {buckets.get('EXPIRED', 0)} / {buckets.get('CANCELLED', 0)}",
		f"Tracking failed / provider unavailable: {buckets.get('TRACKING_FAILED', 0)} / {buckets.get('PROVIDER_UNAVAILABLE', 0)}",
		f"Duplicate thesis deliveries excluded: {buckets.get('DUPLICATE_EXCLUDED', 0)}",
		"",
		f"Net R: {float(report.get('net_r') or 0):+.2f}R",
		f"Average R: {'n/a' if avg_r is None else f'{float(avg_r):+.2f}R'}",
		f"Median R: {'n/a' if median_r is None else f'{float(median_r):+.2f}R'}",
		f"Standardized simple return ({risk_pct:g}% risk): {float(report.get('standardized_simple_return_pct') or 0):+.2f}%",
		f"Standardized compounded return ({risk_pct:g}% risk): {float(report.get('standardized_compounded_return_pct') or 0):+.2f}%",
		f"Raw delivered-signal win rate (TP3 vs SL): {float(report.get('strict_win_rate') or 0) * 100:.1f}%",
		f"Independent thesis sample: {int(report.get('independent_thesis_count') or 0)} "
		f"({int(report.get('independent_thesis_wins') or 0)}W / {int(report.get('independent_thesis_losses') or 0)}L)",
		f"Public 60% claim: {'ELIGIBLE' if report.get('public_claim_allowed') else 'NOT ELIGIBLE'} "
		f"({report.get('public_claim_reason') or 'unknown'})",
		f"95% lower confidence bound: {float(report.get('public_claim_wilson_lower_bound') or 0) * 100:.1f}%",
		f"Terminal coverage: {float(report.get('terminal_coverage') or 0) * 100:.1f}%",
		f"Performance certification: {'PASS' if report.get('performance_certified') else 'BLOCKED'} "
		f"({report.get('performance_certification_reason') or 'unknown'})",
		"",
		f"Returns are standardized illustrations at {risk_pct:g}% risk per completed result; they are not account returns, financial advice, or a guarantee.",
		f"Snapshot: {report.get('snapshot_id', 'n/a')}",
		f"Reconciliation: {report.get('reconciliation_id', 'n/a')}",
	]
	await update.message.reply_text("\n".join(lines))


@require_tier("PREMIUM")
async def quality_command(update, context) -> None:
	if await _public_guard(update):
		return
	if update.message is None:
		return

	try:
		from datetime import datetime, timedelta
		from collections import Counter
		from sqlalchemy import text
		from db.session import get_session

		cutoff = now_utc_naive() - timedelta(hours=24)
		rows = []
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			res = await session.execute(
				text(
					"""
					SELECT decision, COALESCE(reason, '') AS reason, COUNT(*) AS c
					FROM decision_log
					WHERE created_at >= :cutoff
					GROUP BY decision, reason
					"""
				),
				{"cutoff": cutoff},
			)
			rows = list(res.fetchall() or [])
			await session.commit()

		if not rows:
			await update.message.reply_text(
				"Quality (last 24h)\n\nNo decision data yet. Check again after more cycles.",
			)
			return

		issued = 0
		rejected = 0
		cats = Counter()
		top_reasons = Counter()

		for decision, reason, c in rows:
			cnt = int(c or 0)
			d = str(decision or "").lower()
			r = str(reason or "").lower()

			if d == "issued":
				issued += cnt
			if d in {"rejected", "skipped"}:
				rejected += cnt
				top_reasons[r or "(empty)"] += cnt
				if "slippage" in r:
					cats["slippage"] += cnt
				elif "stale" in r:
					cats["stale"] += cnt
				elif "news" in r:
					cats["news"] += cnt
				elif "ml" in r:
					cats["ml"] += cnt
				elif "score" in r:
					cats["score"] += cnt
				else:
					cats["other"] += cnt

		total = issued + rejected
		accept_rate = (issued / total * 100.0) if total > 0 else 0.0
		top_lines = []
		for reason, cnt in top_reasons.most_common(3):
			if not reason:
				continue
			top_lines.append(f"- {reason[:70]}: {cnt}")

		msg = (
			"🧪 Quality (last 24h)\n\n"
			f"Issued: {issued}\n"
			f"Rejected/Skipped: {rejected}\n"
			f"Acceptance rate: {accept_rate:.1f}%\n\n"
			"Reject buckets:\n"
			f"- score: {int(cats.get('score', 0))}\n"
			f"- ML: {int(cats.get('ml', 0))}\n"
			f"- news: {int(cats.get('news', 0))}\n"
			f"- stale: {int(cats.get('stale', 0))}\n"
			f"- slippage: {int(cats.get('slippage', 0))}\n"
			f"- other: {int(cats.get('other', 0))}"
		)
		if top_lines:
			msg += "\n\nTop reject reasons:\n" + "\n".join(top_lines)

		await update.message.reply_text(msg)
	except Exception as exc:
		await update.message.reply_text(f"❌ Could not build quality report: {exc}")


async def gemini_command(update, context) -> None:
	"""Admin-only: trigger Gemini review over all-time aggregate and retrain ML."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	if not (os.getenv("GEMINI_API_KEY") or "").strip():
		await update.message.reply_text(_railway_env_hint("Gemini", ["GEMINI_API_KEY"]))
		return

	from services.gemini_ml import run_gemini_review_pipeline

	await update.message.reply_text(
		"Running Gemini all-time review and ML retrain. This can take up to 2 minutes..."
	)
	try:
		result = await run_gemini_review_pipeline(
			trigger=f"admin:{int(update.effective_user.id)}",
			scope="all_time",
		)
		err = str(result.get("error") or "").strip()
		if not bool(result.get("ok", False)):
			await update.message.reply_text(f"Gemini run failed: {err or 'unknown error'}")
			return

		received = dict(result.get("received") or {})
		processed = dict(result.get("processed") or {})
		training = dict(result.get("training") or {})
		review = str(result.get("review") or "").strip()
		feature_suggestions = list(result.get("feature_suggestions") or [])

		msg = (
			"Gemini run completed.\n\n"
			"Received:\n"
			f"- outcomes: {int(received.get('outcomes_total', 0))}\n"
			f"- wins/losses: {int(received.get('wins', 0))}/{int(received.get('losses', 0))}\n"
			f"- issued: {int(received.get('issued', 0))}\n"
			f"- rejected/skipped: {int(received.get('rejected_or_skipped', 0))}\n"
			"Processed:\n"
			f"- prompt chars: {int(processed.get('prompt_chars', 0))}\n"
			f"- review chars: {int(processed.get('review_chars', 0))}\n"
			"ML training:\n"
			f"- attempted: {bool(training.get('attempted', False))}\n"
			f"- succeeded: {bool(training.get('succeeded', False))}\n"
			f"- note: {str(training.get('note') or 'n/a')}"
		)
		await update.message.reply_text(msg)
		if feature_suggestions:
			feat_lines = [f"- {str(x)[:180]}" for x in feature_suggestions[:6]]
			await update.message.reply_text(
				"Feature suggestions:\n" + "\n".join(feat_lines)
			)
		if review:
			await update.message.reply_text(
				"Gemini review:\n" + review[:3500]
			)
	except Exception as exc:
		await update.message.reply_text(f"Gemini run exception: {exc}")


async def gemini_review_command(update, context) -> None:
	"""Admin-only: show latest Gemini review/training rundown."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return

	from services.gemini_ml import get_last_gemini_review

	try:
		result = await get_last_gemini_review()
		if not result:
			await update.message.reply_text(
				"No Gemini review found yet. Run /gemini first or wait for the weekly job."
			)
			return

		received = dict(result.get("received") or {})
		processed = dict(result.get("processed") or {})
		training = dict(result.get("training") or {})
		review = str(result.get("review") or "").strip()
		feature_suggestions = list(result.get("feature_suggestions") or [])

		msg = (
			"Latest Gemini review.\n\n"
			f"Trigger: {str(result.get('trigger') or 'unknown')}\n"
			f"Scope: {str(result.get('scope') or 'unknown')}\n"
			f"Finished: {str(result.get('finished_at') or 'unknown')}\n\n"
			"Received:\n"
			f"- outcomes: {int(received.get('outcomes_total', 0))}\n"
			f"- wins/losses: {int(received.get('wins', 0))}/{int(received.get('losses', 0))}\n"
			f"- issued: {int(received.get('issued', 0))}\n"
			f"- rejected/skipped: {int(received.get('rejected_or_skipped', 0))}\n"
			"Processed:\n"
			f"- prompt chars: {int(processed.get('prompt_chars', 0))}\n"
			f"- review chars: {int(processed.get('review_chars', 0))}\n"
			"ML training:\n"
			f"- succeeded: {bool(training.get('succeeded', False))}\n"
			f"- note: {str(training.get('note') or 'n/a')}"
		)
		await update.message.reply_text(msg)
		if feature_suggestions:
			feat_lines = [f"- {str(x)[:180]}" for x in feature_suggestions[:6]]
			await update.message.reply_text(
				"Feature suggestions:\n" + "\n".join(feat_lines)
			)
		if review:
			await update.message.reply_text("Gemini review:\n" + review[:3500])
	except Exception as exc:
		await update.message.reply_text(f"Could not load Gemini review: {exc}")


async def gemini_analyze_command(update, context) -> None:
	"""Admin-only: analyze a single asset with recent signals and rejections."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	args = list(context.args or [])
	if not args:
		await update.message.reply_text("Usage: /gemini_analyze SYMBOL [limit]")
		return
	asset = str(args[0] or "").upper().strip()
	limit = int(args[1]) if len(args) > 1 else 20
	from services.gemini_ml import analyze_asset

	try:
		res = await analyze_asset(asset=asset, limit=limit)
		if not bool(res.get("ok", False)):
			await update.message.reply_text(f"Analyze failed: {res.get('error')}")
			return
		await update.message.reply_text(f"Analysis for {asset}: {len(res.get('recent_signals', []))} signals, {len(res.get('recent_rejections', []))} rejections")
	except Exception as exc:
		await update.message.reply_text(f"Analyze error: {exc}")


async def gemini_audit_command(update, context) -> None:
	"""Admin-only: quick audit of recent losses and rejections."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	args = list(context.args or [])
	limit = int(args[0]) if args else 50
	from services.gemini_ml import audit_recent

	try:
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			res = await audit_recent(session, limit=limit)
		if not bool(res.get("ok", True)):
			await update.message.reply_text(f"Audit failed: {res.get('error')}")
			return
		await update.message.reply_text(f"Recent losses: {len(res.get('recent_losses', []))}, recent rejections: {len(res.get('recent_rejections', []))}")
	except Exception as exc:
		await update.message.reply_text(f"Audit error: {exc}")


async def codex_audit_command(update, context) -> None:
	"""Admin-only: local Codex governance review with no external data transfer."""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	args = list(context.args or [])
	scope = str(args[0] if args else "weekly").strip().lower()
	if scope not in {"daily", "weekly", "monthly", "all_time"}:
		await update.message.reply_text("Usage: /codex_audit [daily|weekly|monthly|all_time]")
		return
	from services.codex_governance import run_codex_governance_review

	try:
		await update.message.reply_text("Running local Codex governance review from DB evidence...")
		result = await run_codex_governance_review(
			trigger=f"admin:{int(update.effective_user.id)}",
			scope=scope,
		)
		if not bool(result.get("ok", False)):
			await update.message.reply_text(f"Codex governance review failed: {result.get('review') or result.get('error')}")
			return
		review = dict(result.get("review") or {})
		external_review = dict(result.get("external_codex_review") or {})
		context_data = dict(result.get("context") or {})
		summary = dict(context_data.get("summary") or {})
		deliveries = dict(context_data.get("deliveries") or {})
		msg = (
			"Local Codex governance review complete.\n\n"
			f"Scope: {scope}\n"
			f"External aggregate AI: {'ran' if external_review.get('ok') else 'off/failed'}\n"
			f"Signals: {int(summary.get('signals') or 0)}\n"
			f"Outcomes: {int(summary.get('outcomes') or 0)}\n"
			f"Wins/Losses: {int(summary.get('wins') or 0)}/{int(summary.get('losses') or 0)}\n"
			f"Same-asset repeats <12h: {int(context_data.get('same_asset_deliveries_12h') or 0)}\n"
			f"Reserved not confirmed sent: {int(deliveries.get('reserved_not_confirmed') or 0)}\n\n"
			f"{str(review.get('assessment') or '')[:900]}"
		)
		await update.message.reply_text(msg)
		findings = [str(x) for x in review.get("highest_risk_findings") or []]
		if findings:
			await update.message.reply_text("Findings:\n" + "\n".join(f"- {x[:220]}" for x in findings[:6]))
		env_tweaks = [str(x) for x in review.get("recommended_env_tweaks") or []]
		if env_tweaks:
			await update.message.reply_text("Recommended env/risk tweaks:\n" + "\n".join(f"- {x[:220]}" for x in env_tweaks[:6]))
		code_changes = [str(x) for x in review.get("recommended_code_changes") or []]
		if code_changes:
			await update.message.reply_text("Recommended code checks:\n" + "\n".join(f"- {x[:220]}" for x in code_changes[:6]))
		if external_review.get("ok"):
			ai_review = dict(external_review.get("review") or {})
			ai_findings = [str(x) for x in ai_review.get("highest_risk_findings") or []]
			if ai_findings:
				await update.message.reply_text("OpenAI aggregate review findings:\n" + "\n".join(f"- {x[:220]}" for x in ai_findings[:6]))
	except Exception as exc:
		await update.message.reply_text(f"Codex audit error: {exc}")


async def gemini_predict_command(update, context) -> None:
	"""Admin-only: predict/assess a candidate. Provide JSON or simple args.

	Usage: /gemini_predict BTCUSD 1h long 123.4
	"""
	if update.effective_user is None or update.message is None:
		return
	if not _is_admin(update.effective_user.id):
		await update.message.reply_text("Admin only.")
		return
	args = list(context.args or [])
	if not args:
		await update.message.reply_text("Usage: /gemini_predict SYMBOL TIMEFRAME DIRECTION ENTRY")
		return
	try:
		if len(args) == 1:
			# try parse JSON
			import json as _json

			candidate = _json.loads(args[0])
		else:
			candidate = {"asset": args[0], "timeframe": args[1], "direction": args[2], "entry": float(args[3])}
	except Exception as exc:
		await update.message.reply_text(f"Candidate parse error: {exc}")
		return
	from services.gemini_ml import predict_candidate

	try:
		res = await predict_candidate(candidate)
		if not bool(res.get("ok", False)):
			await update.message.reply_text(f"Predict failed: {res.get('error')}")
			return
		dup = bool(res.get("is_duplicate"))
		await update.message.reply_text(f"Duplicate: {dup}. Neighbors: {len(res.get('recent_neighbors', []))}")
	except Exception as exc:
		await update.message.reply_text(f"Predict error: {exc}")


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
			async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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
				await update.message.reply_text(msg, parse_mode="MarkdownV2")
			return
	except Exception:
		pass
	
	if update.message is not None:
		await update.message.reply_text("Stats unavailable right now.")


@require_tier("PREMIUM")
async def history_command(update, context):
	"""Show last 10 signals delivered to this user, with outcome status."""
	if update.effective_user is None:
		return
	user_id = update.effective_user.id
	asset: str | None = None
	tf: str | None = None
	if context.args:
		asset = str(context.args[0]).upper()
		if len(context.args) > 1:
			tf = str(context.args[1])

	try:
		from db.session import get_engine_for_event_loop, get_session
		from db.models import Signal, Outcome
		from sqlalchemy import select

		engine = get_engine_for_event_loop()
		if engine is None:
			if update.message is not None:
				await update.message.reply_text("⚠️ Database not configured.")
			return

		from db.pg_features import list_recent_signals_delivered
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			rows: list[Signal] = await list_recent_signals_delivered(
				session,
				telegram_user_id=int(user_id),
				limit=15,
				asset=asset,
				timeframe=tf,
			)
			# Fetch outcomes for these signals
			if rows:
				sids = [s.signal_id for s in rows]
				oc_map: dict[str, Outcome] = {}
				oc_rows = (await session.execute(
					select(Outcome).where(Outcome.signal_id.in_(sids))
				)).scalars().all()
				for oc in oc_rows:
					oc_map[oc.signal_id] = oc
			else:
				oc_map = {}
			await session.commit()

		if not rows:
			if update.message is not None:
				await update.message.reply_text(
					"📭 No signal history found yet.\n\n"
					"You'll see your past signals here as they arrive."
				)
			return

		lines: list[str] = [f"🧾 <b>Signal History</b> (last {len(rows)})\n"]
		_r_values: list[float] = []
		for s in rows:
			oc = oc_map.get(s.signal_id)
			if oc is not None and oc.status:
				status_u = str(oc.status).upper()
				oc_emoji = "✅" if oc.status.startswith("tp") else ("❌" if oc.status == "sl" else "⏳")
				r_txt = ""
				if oc.r_multiple is not None:
					r_sign = "+" if float(oc.r_multiple) >= 0 else ""
					r_txt = f" | {r_sign}{float(oc.r_multiple):.1f}R"
					_r_values.append(float(oc.r_multiple))
				outcome_txt = f"{oc_emoji} <b>{status_u}</b>{r_txt}"
			else:
				outcome_txt = "⏳ Open"

			tf_txt = f" [{s.timeframe}]" if s.timeframe else ""
			entry_txt = f"{float(s.entry):.5f}" if s.entry is not None else "—"
			ref = s.signal_id[:8]
			lines.append(
				f"• <b>{s.asset}</b>{tf_txt} {str(s.direction or '').upper()}\n"
				f"  Entry: <code>{entry_txt}</code>  {outcome_txt}  Ref: <code>{ref}</code>"
			)

		if len(_r_values) >= 5:
			try:
				from engine.risk_analytics import sharpe_ratio, sortino_ratio
				_sr = sharpe_ratio(_r_values)
				_so = sortino_ratio(_r_values)
				lines.append("")
				lines.append("📐 <b>Advanced Ratios</b>")
				lines.append(f"• Sharpe: <b>{_sr:.2f}</b>")
				lines.append(f"• Sortino: <b>{_so:.2f}</b>")
			except Exception:
				pass

		lines.append("\n💡 /signal &lt;ref&gt; for full signal details")
		lines.append("💡 /simulate &lt;capital&gt; &lt;risk%&gt; for Monte Carlo forecast")
		if update.message is not None:
			await update.message.reply_text("\n".join(lines), parse_mode="HTML")
		return

	except Exception as exc:
		if update.message is not None:
			await update.message.reply_text(f"❌ Could not load history: {exc}")


@require_tier("VIP")
async def simulate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Project outcomes using only signals confirmed as delivered to this user.

	Usage:
	  /simulate
	  /simulate <starting_capital>
	  /simulate <starting_capital> <risk_pct>
	"""
	if update.message is None or update.effective_user is None:
		return

	uid = int(update.effective_user.id)
	args = [str(a).strip() for a in (context.args or []) if str(a).strip()]
	try:
		from core.paper_trading_service import paper_trading_service
		from engine.risk_analytics import monte_carlo_monthly_projection

		snapshot = await paper_trading_service.snapshot(uid)
		if snapshot is None:
			await update.message.reply_text("⚠️ Profile not found. Send /start first.")
			return
		capital = float(snapshot.equity)
		risk_pct = float(snapshot.risk_pct)
		if len(args) >= 1:
			try:
				capital = max(50.0, float(args[0]))
			except Exception:
				await update.message.reply_text("❌ Invalid capital. Example: /simulate 10000 1")
				return
		if len(args) >= 2:
			try:
				risk_pct = max(0.1, min(10.0, float(args[1])))
			except Exception:
				await update.message.reply_text("❌ Invalid risk %. Example: /simulate 10000 1")
				return

		evidence = await paper_trading_service.delivered_r_samples(uid)
		r_values = [float(v) for v in (evidence.get("r_values") or [])]
		minimum = max(5, int(os.getenv("SIMULATION_MIN_CONFIRMED_OUTCOMES", "10") or 10))
		if len(r_values) < minimum:
			pending_delivered = int(evidence.get("pending_delivered") or 0)
			partial_milestones = int(evidence.get("partial_milestones") or 0)
			delivered_total = int(evidence.get("delivered_total") or 0)
			await update.message.reply_text(
				"🧪 <b>Simulation evidence is not sufficient yet</b>\n\n"
				f"Completed delivered outcomes available: <b>{len(r_values)}</b>\n"
				f"Minimum required: <b>{minimum}</b>\n"
				f"Proof-backed delivered signals: <b>{delivered_total}</b>\n"
				f"Still awaiting a terminal outcome: <b>{pending_delivered}</b>\n"
				f"TP1/TP2 milestones recorded: <b>{partial_milestones}</b>\n"
				f"Current paper equity: <b>${snapshot.equity:,.2f}</b>\n"
				f"Open paper positions: <b>{snapshot.open_positions}</b>\n\n"
				"No default win rate or invented reward assumption was used. "
				"The projection becomes available after enough delivered signals reach a terminal outcome.",
				parse_mode="HTML",
			)
			return

		wins = [r for r in r_values if r > 0]
		losses = [r for r in r_values if r <= 0]
		win_rate = len(wins) / len(r_values)
		avg_win_r = sum(wins) / max(1, len(wins))
		avg_loss_r = abs(sum(losses) / max(1, len(losses))) if losses else 1.0
		first = evidence.get("first")
		last = evidence.get("last")
		days = 30.0
		try:
			if first is not None and last is not None:
				days = max(1.0, (last - first).total_seconds() / 86400.0)
		except Exception:
			days = 30.0
		trades_per_month = max(1, min(300, int(round(len(r_values) / days * 30.0))))
		runs = max(500, min(10000, int(os.getenv("SIMULATION_RUNS", "2000") or 2000)))
		result = monte_carlo_monthly_projection(
			starting_capital=capital,
			risk_pct_per_trade=risk_pct,
			win_rate=win_rate,
			avg_win_r=avg_win_r,
			avg_loss_r=avg_loss_r,
			trades_per_month=trades_per_month,
			runs=runs,
		)

		msg = (
			"🧪 <b>Delivered-Signal Simulation</b>\n\n"
			f"Evidence: <b>{len(r_values)} confirmed outcomes</b>\n"
			f"Observed win rate: <b>{win_rate * 100.0:.1f}%</b>\n"
			f"Observed average win/loss: <b>{avg_win_r:.2f}R / {avg_loss_r:.2f}R</b>\n"
			f"Observed delivery pace: <b>{trades_per_month} trades/month</b>\n"
			f"Starting capital: <b>${result['start']:.2f}</b>\n"
			f"Risk per trade: <b>{risk_pct:.2f}%</b>\n"
			f"Simulations: <b>{result['runs']}</b>\n\n"
			"Projected month-end range:\n"
			f"• 5th percentile: <b>${result['p05']:.2f}</b>\n"
			f"• Median: <b>${result['p50']:.2f}</b>\n"
			f"• 95th percentile: <b>${result['p95']:.2f}</b>\n\n"
			f"Ruin probability: <b>{result['ruin_probability_pct']:.2f}%</b>\n"
			f"Current paper equity/open positions: <b>${snapshot.equity:,.2f} / {snapshot.open_positions}</b>\n\n"
			"This is a statistical scenario based only on your confirmed delivered-signal history, not a profit forecast."
		)
		await update.message.reply_text(msg, parse_mode="HTML")
	except Exception as exc:
		logger.exception("[/simulate] failed user=%s", uid)
		await update.message.reply_text("❌ Simulation is temporarily unavailable. Your paper account and live broker state were not changed.")


@require_tier("PREMIUM")
async def risk_command(update, context) -> None:
	"""Show or update risk settings (recommended % per trade).

	Usage:
	  /risk           → show current setting
	  /risk 1.5       → set risk to 1.5% per trade
	"""
	if update.message is None or update.effective_user is None:
		return
	user_id: int = update.effective_user.id

	args = [str(a).strip() for a in (context.args or []) if str(a).strip()]

	try:
		from db.session import get_session as _gs, get_engine_for_event_loop
		from db.models import User
		from sqlalchemy import select

		if get_engine_for_event_loop() is None:
			await update.message.reply_text("⚠️ Database not configured.")
			return

		async with _gs() as session:
			user_row = (await session.execute(
				select(User).where(User.telegram_user_id == user_id)
			)).scalar_one_or_none()

			if user_row is None:
				await update.message.reply_text("⚠️ Profile not found. Send /start first.")
				return

			if not args:
				current = float(getattr(user_row, "max_risk_percentage", 1.0) or 1.0)
				await update.message.reply_text(
					"🛡️ <b>Risk Per Trade</b>\n\n"
					f"Current setting: <b>{current:.2f}%</b> per trade\n\n"
					"Recommended: 1% per trade. Never risk more than 2–3%.\n\n"
					"To update: <code>/risk 1.5</code>",
					parse_mode="HTML",
				)
				return

			try:
				new_risk = float(args[0])
			except ValueError:
				await update.message.reply_text("❌ Invalid value. Use a number, e.g. /risk 1.5")
				return

			if new_risk < 0.1 or new_risk > 10.0:
				await update.message.reply_text("❌ Risk must be between 0.1% and 10%.")
				return

			user_row.max_risk_percentage = round(new_risk, 2)
			await session.commit()

		await update.message.reply_text(
			f"✅ <b>Risk per trade updated</b>\n\n"
			f"New setting: <b>{round(new_risk, 2):.2f}%</b> per trade\n\n"
			"This setting is used for VIP risk-based lot sizing on AUTO execution.",
			parse_mode="HTML",
		)
	except Exception as exc:
		await update.message.reply_text(f"❌ Could not update risk: {exc}")


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
				async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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
				async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Set user execution mode for signals."""
	if update.effective_user is None or update.message is None:
		return
	user_id = int(update.effective_user.id)
	args = list(getattr(context, "args", []) or [])
	valid_modes = {"signals_only", "copy_trade", "manual", "none", "auto", "paper"}

	if not args:
		await update.message.reply_text(
			"Execution mode\n\n"
			"Use /mode signals_only, /mode copy_trade, /mode manual, /mode paper, or /mode auto."
		)
		return

	mode_arg = str(args[0]).strip().lower()
	if mode_arg not in valid_modes:
		await update.message.reply_text(f"Invalid mode. Use: {', '.join(sorted(valid_modes))}")
		return

	final_mode = {"none": "signals_only"}.get(mode_arg, mode_arg)
	if final_mode == "auto":
		try:
			from .access import resolve_user_tier
			user_tier = str(resolve_user_tier(user_id) or "free").lower()
			if user_tier not in {"vip", "owner", "admin"}:
				await update.message.reply_text("Auto-execution is only available for VIP users.")
				return
		except Exception:
			pass

	try:
		from db.session import get_session
		from db.models import User
		from sqlalchemy import update as sa_update

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			await session.execute(
				sa_update(User)
				.where(User.telegram_user_id == user_id)
				.values(execution_mode=final_mode)
			)
			await session.commit()
	except Exception as exc:
		await update.message.reply_text(f"Could not update mode: {exc}")
		return

	await update.message.reply_text(f"Mode updated: {final_mode.upper()}")


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
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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

	if not context.args:
		await update.message.reply_text(
			"Usage: /liveprice &lt;asset&gt;\n\n"
			"Examples:\n"
			"/liveprice BTCUSDT\n"
			"/liveprice EURUSD\n"
			"/liveprice AAPL",
			parse_mode="HTML",
		)
		return

	asset = context.args[0].strip().upper()

	try:
		import asyncio
		from engine.price_validator import get_current_price
		from datetime import datetime

		loop = asyncio.get_event_loop()
		current_price: float | None = await loop.run_in_executor(None, get_current_price, asset)

		if current_price is None:
			await update.message.reply_text(
				f"❌ Could not fetch price for <b>{asset}</b>.\n\n"
				f"Check the symbol and try again.",
				parse_mode="HTML",
			)
			return

		if asset.endswith(("USDT", "USDC", "BUSD")):
			price_str = f"${current_price:,.4f}" if current_price < 100 else f"${current_price:,.2f}"
			asset_type = "Crypto"
		elif len(asset) in (6, 7) and asset.isalpha():
			price_str = f"{current_price:.5f}"
			asset_type = "Forex"
		else:
			price_str = f"${current_price:,.2f}"
			asset_type = "Stock / Other"

		timestamp = now_utc_naive().strftime("%Y-%m-%d %H:%M:%S UTC")
		msg = (
			f"💰 <b>Live Price</b>\n\n"
			f"Asset: <b>{asset}</b>\n"
			f"Type: {asset_type}\n"
			f"Price: <b>{price_str}</b>\n\n"
			f"🕐 {timestamp}"
		)
		await update.message.reply_text(msg, parse_mode="HTML")

	except Exception as exc:
		await update.message.reply_text(f"❌ Error fetching price: {exc}")


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show all active signals with live P&L for the user."""
	if update.effective_user is None or update.message is None:
		return

	user_id: int = update.effective_user.id

	try:
		from db.session import get_session, get_engine_for_event_loop
		from db.models import Signal, SignalDelivery, User, Outcome
		from sqlalchemy import select
		from datetime import datetime, timedelta
		from engine.price_validator import get_current_price
		from engine.signal_calculations import calculate_profit_loss_pct
		import asyncio

		if get_engine_for_event_loop() is None:
			await update.message.reply_text("⚠️ Database not configured.")
			return

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			# Resolve the DB user record to get the FK id used in signal_deliveries
			user_row = (await session.execute(
				select(User).where(User.telegram_user_id == user_id)
			)).scalar_one_or_none()
			if user_row is None:
				await update.message.reply_text("⚠️ User profile not found. Send /start first.")
				return

			# Get signals delivered to this user (active = not archived, last 72 h)
			cutoff = now_utc_naive() - timedelta(hours=72)
			stmt = (
				select(Signal, Outcome)
				.join(SignalDelivery, Signal.signal_id == SignalDelivery.signal_id)
				.outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
				.where(
					SignalDelivery.user_id == user_row.id,
					Signal.archived == False,
					Signal.created_at >= cutoff,
				)
				.distinct(Signal.signal_id)
				.order_by(Signal.signal_id, Signal.created_at.desc())
			)
			rows = (await session.execute(stmt)).all()
			await session.commit()

		if not rows:
			await update.message.reply_text(
				"📊 <b>Portfolio</b>\n\n"
				"You have no active signals in the last 72 hours.\n\n"
				"Use /signals to view available signals.",
				parse_mode="HTML",
			)
			return

		# Deduplicate (distinct on signal_id returns first row per id)
		seen: set = set()
		signals_with_outcome: list = []
		for sig, oc in rows:
			if sig.signal_id not in seen:
				seen.add(sig.signal_id)
				signals_with_outcome.append((sig, oc))

		# Fetch live prices concurrently in a thread pool
		assets = list({sig.asset for sig, _ in signals_with_outcome})
		prices: dict[str, float | None] = {}
		loop = asyncio.get_event_loop()

		async def _fetch_price(asset: str) -> tuple[str, float | None]:
			try:
				px = await loop.run_in_executor(None, get_current_price, asset)
				return asset, px
			except Exception:
				return asset, None

		price_results = await asyncio.gather(*[_fetch_price(a) for a in assets])
		for asset, px in price_results:
			prices[asset] = px

		total_pnl = 0.0
		valid_count = 0
		lines: list[str] = [f"📊 <b>Your Active Portfolio</b> ({len(signals_with_outcome)} signals)\n"]

		for sig, oc in signals_with_outcome:
			try:
				asset = sig.asset
				direction = str(sig.direction or "long").upper()
				entry = float(sig.entry or 0)
				ref = sig.signal_id[:8]

				# If signal already has a recorded outcome, show it
				if oc is not None and oc.status is not None:
					status_u = str(oc.status).upper()
					r_txt = ""
					if oc.r_multiple is not None:
						r_sign = "+" if float(oc.r_multiple) >= 0 else ""
						r_txt = f" | R: {r_sign}{float(oc.r_multiple):.2f}R"
					status_emoji = "✅" if oc.status.startswith("tp") else "❌"
					lines.append(
						f"{status_emoji} <b>{asset}</b> {direction} — <b>{status_u}</b>{r_txt}\n"
						f"   Entry: <code>{entry:.5f}</code> | Ref: <code>{ref}</code>\n"
					)
					continue

				current_price = prices.get(asset)
				if current_price is None or entry <= 0:
					lines.append(
						f"⚪ <b>{asset}</b> {direction}\n"
						f"   Entry: <code>{entry:.5f}</code> | Price: unavailable | Ref: <code>{ref}</code>\n"
					)
					continue

				pnl_pct = calculate_profit_loss_pct(entry, current_price, direction)
				total_pnl += pnl_pct
				valid_count += 1
				pnl_sign = "+" if pnl_pct >= 0 else ""
				pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"

				lines.append(
					f"{pnl_emoji} <b>{asset}</b> {direction}\n"
					f"   Entry: <code>{entry:.5f}</code> → Now: <code>{current_price:.5f}</code>\n"
					f"   P&amp;L: <b>{pnl_sign}{pnl_pct:.2f}%</b> | Ref: <code>{ref}</code>\n"
				)
			except Exception:
				continue

		if valid_count > 0:
			avg_pnl = total_pnl / valid_count
			avg_sign = "+" if avg_pnl >= 0 else ""
			summary_emoji = "📈" if avg_pnl >= 0 else "📉"
			lines.append(
				f"━━━━━━━━━━━━━━━━\n"
				f"{summary_emoji} <b>Open P&amp;L avg:</b> {avg_sign}{avg_pnl:.2f}%\n"
			)

		lines.append("💡 Use /signal &lt;ref&gt; for full signal details")
		await update.message.reply_text("\n".join(lines), parse_mode="HTML")

	except Exception as exc:
		await update.message.reply_text(f"❌ Could not load portfolio: {exc}")


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show overall market conditions."""
	if update.effective_user is None or update.message is None:
		return

	import asyncio

	try:
		from engine.price_validator import get_current_price
		loop = asyncio.get_event_loop()

		# Define major assets to track
		major_assets = [
			("BTCUSDT",  "Bitcoin",     "₿"),
			("ETHUSDT",  "Ethereum",    "⬡"),
			("EURUSD",   "EUR/USD",     "🇪🇺"),
			("XAUUSD",   "Gold",        "🥇"),
			("GBPUSD",   "GBP/USD",     "🇬🇧"),
			("USDJPY",   "USD/JPY",     "🇯🇵"),
		]

		async def _fetch(symbol: str) -> tuple[str, float | None]:
			try:
				px = await loop.run_in_executor(None, get_current_price, symbol)
				return symbol, px
			except Exception:
				return symbol, None

		price_results = await asyncio.gather(*[_fetch(sym) for sym, _, _ in major_assets])
		price_map: dict[str, float | None] = dict(price_results)

		from datetime import datetime
		timestamp = now_utc_naive().strftime("%H:%M UTC")

		lines = [f"🌐 <b>Market Overview</b> — {timestamp}\n"]
		for symbol, name, icon in major_assets:
			price = price_map.get(symbol)
			if price is None:
				continue
			if "USDT" in symbol or symbol in ("EURUSD", "GBPUSD", "USDJPY"):
				if price >= 100:
					price_str = f"{price:,.2f}"
				elif price >= 1:
					price_str = f"{price:.5f}"
				else:
					price_str = f"{price:.6f}"
			else:
				price_str = f"{price:,.2f}"
			lines.append(f"{icon} <b>{name}</b>: <code>{price_str}</code>")

		lines.append("\n💡 /liveprice &lt;symbol&gt; for any asset  |  /signals for active trades")
		await update.message.reply_text("\n".join(lines), parse_mode="HTML")

	except Exception as exc:
		await update.message.reply_text(f"❌ Could not fetch market data: {exc}")


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

	missing_vars = []
	if not (os.getenv("ENCRYPTION_KEY") or "").strip():
		missing_vars.append("ENCRYPTION_KEY")
	if not (os.getenv("META_API_TOKEN") or "").strip():
		missing_vars.append("META_API_TOKEN")
	if missing_vars:
		await update.message.reply_text(_railway_env_hint("MT5 linking", missing_vars))
		return

	args = (context.args or [])
	if len(args) < 3:
		await update.message.reply_text(
			"⚙️ <b>Link your MT5 Account</b>\n\n"
			"Usage: <code>/mt5_link &lt;login&gt; &lt;password&gt; &lt;server&gt;</code>\n\n"
			"Example:\n<code>/mt5_link 123456 MyP@ssw0rd MetaQuotes-Demo</code>\n\n"
			"🔒 Your password is encrypted end-to-end with AES-256 (Fernet) before storage.\n"
			"Neither SignalRankAI staff nor Railway can read it in plaintext.",
			parse_mode="HTML"
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
		if result.get("success"):
			meta_id = result.get("metaapi_account_id") or ""
			reply = (
				"✅ MT5 Account Linked Successfully!\n\n"
				f"🏦 Server: {mt5_server}\n"
				f"🔐 Login: {mt5_login} (credentials encrypted)\n"
			)
			if meta_id:
				reply += f"☁️ MetaApi Account ID: {meta_id}\n"
			reply += (
				"\nYou can now use the Trade on MT5 button "
				"on any signal to execute instantly.\n\n"
				"⚙️ Configure execution routing with /execution\n"
				"• /execution manual (default)\n"
				"• /execution none\n"
				"• /execution auto 5 (VIP)"
			)
			if not result.get("executable"):
				reply = (
					"MT5 credentials saved, but live execution is not ready yet.\n\n"
					f"Server: {mt5_server}\n"
					f"Login: {mt5_login} (credentials encrypted)\n\n"
					"MetaApi did not return an executable account ID. "
					"Signals and paper trading can continue, but Trade on MT5 "
					"will stay disabled until the execution bridge is provisioned.\n\n"
					"Run /mt5_status to check readiness."
				)
		else:
			err = result.get("error", "Unknown error")
			reply = (
				"❌ MT5 Link Failed\n\n"
				f"Error: {err}\n\n"
				"Please check your login, password and server name, then try again.\n"
				"Use /mt5_link <login> <password> <server>"
			)
	except Exception as exc:
		reply = (
			f"❌ MT5 Link Error\n\n{type(exc).__name__}: {exc}\n\n"
			"Please try again or contact support with /support"
		)

	try:
		await processing_msg.edit_text(reply)
	except Exception:
		await update.effective_chat.send_message(reply)


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
		from services.mt5_client import get_user_mt5_link_status
		from db.session import get_session
		from db.models import MT5Credentials, User
		from sqlalchemy import select
		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			user_row = (await session.execute(
				select(User).where(User.telegram_user_id == int(user_id))
			)).scalar_one_or_none()
			if user_row is None:
				await update.message.reply_text("No account profile found. Send /start then try again.")
				return
			row = (await session.execute(
				select(MT5Credentials).where(MT5Credentials.user_id == int(user_row.id))
			)).scalar_one_or_none()
		if row is None:
			await update.message.reply_text(
				"No MT5 account linked.\n\nUse /mt5_link <login> <password> <server> to connect."
			)
			return
		reply = (
			"⚙️ Your Linked MT5 Account\n\n"
			f"🏦 Server: {row.server}\n"
			f"🔐 Login: {row.mt5_login} (password encrypted)\n"
		)
		if row.metaapi_account_id:
			reply += f"☁️ MetaApi ID: {row.metaapi_account_id}\n"
		status = await get_user_mt5_link_status(int(user_id))
		if status.get("executable"):
			reply += "\nExecution bridge: READY\nUse ⚡ buttons on signals to trade instantly."
		else:
			reply += (
				"\nExecution bridge: NOT READY\n"
				"Your credentials are saved, but MetaApi has not returned an executable account ID.\n"
				"Run /mt5_link again to retry provisioning, then check /mt5_status."
			)
		await update.message.reply_text(reply)
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
		from sqlalchemy import select, text

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

	global_cap = float(os.getenv("AUTO_MAX_RISK_CAP_PCT", "3.0") or 3.0)
	allowed_max = max(0.1, min(5.0, float(global_cap)))
	if not (0.1 <= pct <= allowed_max):
		await update.message.reply_text(
			f"❌ Risk must be between 0.1% and {allowed_max:.1f}% (global cap).",
			parse_mode="HTML",
		)
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


@require_tier("VIP")
async def setwebhook_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""VIP command to save or disable third-party execution webhook URL."""
	if update.effective_user is None or update.message is None:
		return
	user_id: int = int(update.effective_user.id)
	args = context.args or []
	if not args:
		await update.message.reply_text(
			"Usage:\n"
			"/setwebhook <https://your-endpoint>\n"
			"/setwebhook off",
		)
		return
	raw = str(args[0]).strip()
	disable = raw.lower() in {"off", "disable", "none"}
	if (not disable) and not (raw.startswith("https://") or raw.startswith("http://")):
		await update.message.reply_text("❌ Webhook URL must start with http:// or https://")
		return
	try:
		from sqlalchemy import select
		from db.models import User, UserWebhook
		from db.session import get_session as _gs
		async with _gs() as session:
			user = (await session.execute(
				select(User).where(User.telegram_user_id == int(user_id))
			)).scalar_one_or_none()
			if user is None:
				await update.message.reply_text("No account profile found. Send /start then try again.")
				return
			row = (await session.execute(
				select(UserWebhook).where(UserWebhook.user_id == int(user.id))
			)).scalar_one_or_none()
			if disable:
				if row is not None:
					row.is_active = False
					row.updated_at = now_utc_naive()
					await session.commit()
				await update.message.reply_text("✅ VIP execution webhook disabled.")
				return
			if row is None:
				session.add(
					UserWebhook(
						user_id=int(user.id),
						webhook_url=raw,
						is_active=True,
						updated_at=now_utc_naive(),
					)
				)
			else:
				row.webhook_url = raw
				row.is_active = True
				row.updated_at = now_utc_naive()
			await session.commit()
		await update.message.reply_text("✅ VIP execution webhook saved.")
	except Exception as exc:
		await update.message.reply_text(f"❌ Could not save webhook: {exc}")


async def execution_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Configure broker execution and provider selection.

	Usage:
	  /execution                              -> show current settings
	  /execution none                         -> disable broker execution
	  /execution manual [mt5|bybit|auto]       -> confirmed execution only
	  /execution auto [count|all] [provider]   -> VIP auto-execution
	  /execution copy [count|all] [provider]   -> VIP copy execution
	"""
	if update.effective_user is None or update.message is None:
		return

	user_id = int(update.effective_user.id)
	tier = _effective_tier(user_id)
	if tier_rank(tier) < tier_rank("PREMIUM"):
		await update.message.reply_text(
			"🔒 /execution is available on <b>PREMIUM</b> and above.",
			parse_mode="HTML",
		)
		return

	try:
		import json
		from db.session import get_session as _gs
		from db.models import RuntimeState, User
		from sqlalchemy import select, text

		args = [str(a).strip().lower() for a in (context.args or []) if str(a).strip()]
		provider_values = {"auto", "mt5", "bybit"}

		async with _gs(label="execution.command", timeout_seconds=8.0) as session:
			row = (await session.execute(select(User).where(User.telegram_user_id == user_id))).scalar_one_or_none()
			if row is None:
				await update.message.reply_text("❌ User profile not found. Send /start and try again.")
				return
			prefs_row = await session.get(RuntimeState, f"user_prefs:{user_id}")
			prefs = dict(getattr(prefs_row, "value", {}) or {}) if prefs_row else {}
			provider = str(prefs.get("execution_provider") or "auto").lower()

			if not args:
				mode = str(getattr(row, "execution_mode", "manual") or "manual").lower()
				cap = int(getattr(row, "auto_signals_daily_limit", -1) or 0)
				cap_txt = "all" if cap < 0 else str(cap)
				await update.message.reply_text(
					"⚙️ <b>Execution Settings</b>\n\n"
					f"Mode: <b>{mode.upper()}</b>\n"
					f"Provider: <b>{provider.upper()}</b>\n"
					f"Daily cap: <b>{cap_txt}</b>\n\n"
					"Use: <code>/execution none|manual|auto|copy [count|all] [auto|mt5|bybit]</code>",
					parse_mode="HTML",
				)
				return

			mode = args[0]
			if mode not in {"none", "manual", "auto", "copy"}:
				await update.message.reply_text(
					"❌ Invalid mode. Use <code>none</code>, <code>manual</code>, <code>auto</code> or <code>copy</code>.",
					parse_mode="HTML",
				)
				return
			if mode in {"auto", "copy"} and tier_rank(tier) < tier_rank("VIP"):
				await update.message.reply_text(
					"🔒 AUTO and COPY modes require <b>VIP</b>. PREMIUM supports NONE/MANUAL.",
					parse_mode="HTML",
				)
				return

			cap = int(getattr(row, "auto_signals_daily_limit", -1) or -1)
			remaining = args[1:]
			for value in remaining:
				if value in provider_values:
					provider = value
				elif mode in {"auto", "copy"}:
					if value == "all":
						cap = -1
					else:
						try:
							cap = max(1, min(int(value), 100))
						except Exception:
							await update.message.reply_text("❌ Invalid cap/provider. Example: /execution auto 5 bybit")
							return
				else:
					await update.message.reply_text("❌ Provider must be auto, mt5 or bybit.")
					return

			row.execution_mode = "copy_trade" if mode == "copy" else mode
			row.auto_signals_daily_limit = int(cap)
			prefs.update({"execution_provider": provider, "execution_mode": row.execution_mode, "updated_at": now_utc_naive().isoformat()})
			if prefs_row is None:
				session.add(RuntimeState(key=f"user_prefs:{user_id}", value=prefs))
			else:
				prefs_row.value = prefs
				prefs_row.updated_at = now_utc_naive()

			for key_name in (f"autoexec_user_optin:{user_id}", f"copyexec_user_optin:{user_id}"):
				await session.execute(text("DELETE FROM runtime_state WHERE key = :k"), {"k": key_name})
			if mode in {"auto", "copy"}:
				key_name = f"{'copyexec' if mode == 'copy' else 'autoexec'}_user_optin:{user_id}"
				await session.execute(
					text("""
						INSERT INTO runtime_state(key, value, expires_at, updated_at)
						VALUES (:k, CAST(:v AS JSONB), NULL, NOW())
						ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, expires_at = NULL, updated_at = NOW()
					"""),
					{"k": key_name, "v": json.dumps({"enabled": True, "provider": provider})},
				)
			await session.commit()

		cap_txt = "all" if int(cap) < 0 else str(int(cap))
		await update.message.reply_text(
			"✅ <b>Execution settings updated</b>\n\n"
			f"Mode: <b>{mode.upper()}</b>\n"
			f"Provider: <b>{provider.upper()}</b>\n"
			f"Daily cap: <b>{cap_txt}</b>\n\n"
			"Live execution still requires linked trade-only credentials, accepted terms, risk checks, and global production activation.",
			parse_mode="HTML",
		)
	except Exception as exc:
		await update.message.reply_text(f"❌ Could not update execution mode: {type(exc).__name__}")


async def drawdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Set daily drawdown circuit-breaker threshold.

	Usage:
	  /drawdown           -> show current threshold
	  /drawdown 4         -> pause AUTO at -4% (rolling 24h)
	  /drawdown off       -> disable circuit breaker
	"""
	if update.effective_user is None or update.message is None:
		return

	user_id: int = int(update.effective_user.id)
	tier: str = _effective_tier(user_id)
	if tier_rank(tier) < tier_rank("PREMIUM"):
		await update.message.reply_text(
			"🔒 /drawdown is available on <b>PREMIUM</b> and above.",
			parse_mode="HTML",
		)
		return

	args = [str(a).strip().lower() for a in (context.args or []) if str(a).strip()]

	try:
		from db.session import get_session as _gs
		from db.models import User
		from sqlalchemy import select

		async with _gs() as session:
			row = (await session.execute(select(User).where(User.telegram_user_id == user_id))).scalar_one_or_none()
			if row is None:
				await update.message.reply_text("❌ User profile not found. Send /start and try again.")
				return

			if not args:
				cap = float(getattr(row, "max_daily_drawdown_pct", 8.0) or 0.0)
				cap_txt = "OFF" if cap <= 0 else f"{cap:.2f}%"
				await update.message.reply_text(
					"🛡️ <b>Daily Drawdown Guard</b>\n\n"
					f"Current threshold: <b>{cap_txt}</b>\n"
					"Window: rolling 24h realized P&L\n\n"
					"Use: <code>/drawdown 4</code> or <code>/drawdown off</code>",
					parse_mode="HTML",
				)
				return

			arg0 = args[0]
			if arg0 in {"off", "none", "disable", "0"}:
				row.max_daily_drawdown_pct = 0.0
				await session.commit()
				await update.message.reply_text(
					"✅ Daily drawdown circuit breaker is now <b>OFF</b>.",
					parse_mode="HTML",
				)
				return

			try:
				cap = float(arg0)
			except Exception:
				await update.message.reply_text("❌ Invalid value. Use a number like 4 or 'off'.")
				return

			if cap < 0.5 or cap > 25:
				await update.message.reply_text("❌ Allowed range is 0.5 to 25 (%).")
				return

			row.max_daily_drawdown_pct = float(round(cap, 2))
			await session.commit()

		await update.message.reply_text(
			"✅ <b>Daily drawdown guard updated</b>\n\n"
			f"Threshold: <b>{float(round(cap, 2)):.2f}%</b>\n"
			"If rolling 24h realized P&L reaches this loss, AUTO switches to MANUAL.",
			parse_mode="HTML",
		)
	except Exception as exc:
		await update.message.reply_text(f"❌ Could not update drawdown setting: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /tiers  — Subscription comparison table
# ─────────────────────────────────────────────────────────────────────────────

async def tiers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Display a tier comparison table and upgrade links."""
	if update.effective_user is None or update.message is None:
		return

	premium_price = int(os.getenv("PREMIUM_MONTHLY_PRICE_NGN", os.getenv("PREMIUM_PRICE_NGN", "24000")))
	vip_price = int(os.getenv("VIP_MONTHLY_PRICE_NGN", os.getenv("VIP_PRICE_NGN", "40000")))
	vip_limit = int(os.getenv("VIP_SEAT_LIMIT", "0") or 0)
	vip_capacity_label = "open enrollment" if vip_limit <= 0 else f"only {vip_limit} seats"

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
		f"<b>👑 VIP — ₦{vip_price:,}/month</b> ({vip_capacity_label})\n"
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
		from db.session import get_session as _gs, get_engine_for_event_loop
		from db.models import MT5Execution, User, Outcome, SignalDelivery
		from sqlalchemy import select, func

		if get_engine_for_event_loop() is None:
			await update.message.reply_text("⚠️ Database not configured.")
			return

		async with _gs() as session:
			# Resolve DB user — MT5Execution.user_id is FK to users.id, NOT telegram_user_id
			user_row = (await session.execute(
				select(User).where(User.telegram_user_id == user_id)
			)).scalar_one_or_none()

			db_user_id: int | None = user_row.id if user_row is not None else None

			if db_user_id is None:
				await update.message.reply_text("⚠️ Profile not found. Send /start first.")
				return

			# Total MT5 executions (correct FK)
			total_exec = (await session.execute(
				select(func.count()).where(MT5Execution.user_id == db_user_id)
			)).scalar() or 0

			# Win / loss from MT5 executions
			# Status values: 'tp1' | 'tp2' | 'tp3' | 'tp' — wins; 'sl' — losses
			wins_exec = (await session.execute(
				select(func.count()).where(
					MT5Execution.user_id == db_user_id,
					MT5Execution.status.in_(["tp", "tp1", "tp2", "tp3"]),
				)
			)).scalar() or 0

			losses_exec = (await session.execute(
				select(func.count()).where(
					MT5Execution.user_id == db_user_id,
					MT5Execution.status == "sl",
				)
			)).scalar() or 0

			# Realized PnL sum from MT5 executions
			total_pnl = (await session.execute(
				select(func.sum(MT5Execution.realized_pnl)).where(
					MT5Execution.user_id == db_user_id,
					MT5Execution.realized_pnl.isnot(None),
				)
			)).scalar() or 0.0

			# Also count from signal outcomes (broader — covers non-MT5 users too)
			oc_rows = (await session.execute(
				select(Outcome)
				.join(SignalDelivery, SignalDelivery.signal_id == Outcome.signal_id)
				.where(SignalDelivery.user_id == db_user_id)
				.order_by(Outcome.closed_at.desc())
				.limit(200)
			)).scalars().all()
			await session.commit()

		# If no MT5 executions, fall back to signal outcome counts
		if total_exec > 0:
			wins = wins_exec
			losses = losses_exec
		else:
			wins = sum(1 for o in oc_rows if str(o.status or "").startswith("tp"))
			losses = sum(1 for o in oc_rows if o.status == "sl")

		tracked = wins + losses
		win_rate = (wins / tracked * 100) if tracked > 0 else 0.0

		# Net/avg R from outcomes
		r_values = [float(o.r_multiple) for o in oc_rows if o.r_multiple is not None]
		net_r = sum(r_values) if r_values else None
		avg_r = (sum(r_values) / len(r_values)) if r_values else None

		# Subscription expiry
		sub_expiry = ""
		if user_row:
			from datetime import timezone as _tz
			expiry = getattr(user_row, "premium_until", None)
			if expiry:
				if hasattr(expiry, "tzinfo") and expiry.tzinfo is None:
					expiry = expiry.replace(tzinfo=_tz.utc)
				sub_expiry = f"\n📅 Subscription expires: <b>{expiry.strftime('%d %b %Y')}</b>"

		# Daily execution counter
		daily_exec = 0
		if user_row:
			try:
				from engine.tiered_executor import reset_daily_counter_if_needed
				reset_daily_counter_if_needed(user_row)
			except Exception:
				pass
			daily_exec = int(getattr(user_row, "daily_executions_today", 0) or 0)

		tier_disp = tier.upper()
		msg = (
			f"<b>📈 My Stats — {tier_disp}</b>\n\n"
			f"🔢 MT5 executions: <b>{total_exec}</b>\n"
			f"✅ Wins: <b>{wins}</b>  ❌ Losses: <b>{losses}</b>\n"
			f"🎯 Win rate: <b>{win_rate:.1f}%</b>\n"
		)
		if net_r is not None:
			net_sign = "+" if net_r >= 0 else ""
			msg += f"📐 Net R: <b>{net_sign}{net_r:.2f}R</b>\n"
		if avg_r is not None:
			avg_sign = "+" if avg_r >= 0 else ""
			msg += f"📏 Avg R/trade: <b>{avg_sign}{avg_r:.2f}R</b>\n"
		if total_exec > 0:
			pnl_sign = "+" if float(total_pnl) >= 0 else ""
			msg += f"💰 Realized P&amp;L: <b>{pnl_sign}${float(total_pnl):.2f}</b>\n"
		if tier.upper() in ("PREMIUM", "VIP"):
			try:
				from engine.tiered_executor import PREMIUM_DAILY_LIMIT
				remaining = max(0, PREMIUM_DAILY_LIMIT - daily_exec)
				msg += f"📋 Today's executions: <b>{daily_exec}/{PREMIUM_DAILY_LIMIT}</b> ({remaining} remaining)\n"
			except Exception:
				pass
		msg += sub_expiry
		await update.message.reply_text(msg, parse_mode="HTML")

	except Exception as exc:
		await update.message.reply_text(f"⚠️ Could not load stats: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /referral  — Generate referral deep-link
# ─────────────────────────────────────────────────────────────────────────────

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Generate a durable personal referral link and show canonical stats."""
	if update.effective_user is None or update.message is None:
		return
	user_id = int(update.effective_user.id)
	bot_username = ""
	try:
		bot_username = str((await context.bot.get_me()).username or "")
	except Exception:
		bot_username = os.getenv("BOT_USERNAME", "")
	bot_username = bot_username.strip().lstrip("@")

	try:
		from db.session import get_session as _gs
		from db.models import User, ReferralReward
		from sqlalchemy import select, func
		from db.pg_features import get_or_create_referral_code, get_referral_progress
		async with _gs(
			priority="interactive",
			label="referral.dashboard",
			timeout_seconds=8.0,
		) as session:
			referral_code = await get_or_create_referral_code(
				session,
				referrer_telegram_user_id=user_id,
			)
			progress = await get_referral_progress(
				session,
				referrer_telegram_user_id=user_id,
			)
			user_row = (
				await session.execute(
					select(User).where(User.telegram_user_id == user_id)
				)
			).scalar_one()
			bonus_earned_days = int(
				(
					await session.execute(
						select(func.coalesce(func.sum(ReferralReward.reward_value), 0)).where(
							ReferralReward.referrer_user_id == int(user_row.id),
							ReferralReward.reward_type == "premium_days",
						)
					)
				).scalar()
				or 0
			)
			await session.commit()
	except Exception as exc:
		logging.getLogger(__name__).exception(
			"[referral_dashboard_failed] user=%s error=%s",
			user_id,
			exc,
		)
		await update.message.reply_text(
			"⚠️ Referral information is temporarily unavailable because the database is busy. "
			"No invalid fallback link was generated. Please try /referral again."
		)
		return

	referred_count = int(progress.get("total", 0) or 0)
	toward_next = int(progress.get("toward_next", 0) or 0)
	needed_for_next = int(progress.get("needed_for_next", 3) or 3)
	requirement = int(progress.get("requirement", 3) or 3)
	bonus_days = int(progress.get("reward_days_per_3", 7) or 7)
	referral_url = (
		f"https://t.me/{bot_username}?start=ref_{referral_code}"
		if bot_username
		else ""
	)
	msg = (
		f"🔗 <b>Your Referral Link</b>\n\n"
		f"<code>{referral_url or referral_code}</code>\n\n"
		f"📊 Valid referrals: <b>{referred_count}</b>\n"
		f"🎁 Bonus earned: <b>+{bonus_earned_days} days</b> subscription\n"
		f"📈 Progress: <b>{toward_next}/{requirement}</b> "
		f"(invite {needed_for_next} more)\n\n"
		f"💡 Earn <b>+{bonus_days} free days</b> for every {requirement} valid referrals."
	)
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		share_url = f"https://t.me/share/url?url={referral_url}" if referral_url else ""
		rows = []
		if share_url:
			rows.append([InlineKeyboardButton("📣 Share", url=share_url)])
		rows.append([
			InlineKeyboardButton("💳 Upgrade", callback_data="nav_upgrade"),
			InlineKeyboardButton("🎧 Support", callback_data="nav_support"),
		])
		keyboard = InlineKeyboardMarkup(rows)
	except Exception:
		keyboard = None
	await update.message.reply_text(
		msg,
		parse_mode="HTML",
		disable_web_page_preview=True,
		reply_markup=keyboard,
	)


# ─────────────────────────────────────────────────────────────────────────────
# /leaderboard  — Weekly signal performance leaderboard (VIP)
# ─────────────────────────────────────────────────────────────────────────────

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Show the weekly signal performance leaderboard.

	VIP users are included with their username/alias.
	Free/Premium users see the board anonymised.
	"""
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)

	try:
		from db.session import get_session, get_engine_for_event_loop
		from sqlalchemy import text
		from datetime import datetime

		if get_engine_for_event_loop() is None:
			await update.message.reply_text("⚠️ Database not configured.")
			return

		min_trades = max(3, int(os.getenv("LEADERBOARD_MIN_TRACKED_TRADES", "5") or 5))
		min_win_rate = max(0.0, min(float(os.getenv("LEADERBOARD_MIN_WIN_RATE", "45") or 45), 100.0))
		min_avg_r = float(os.getenv("LEADERBOARD_MIN_AVG_R", "0.05") or 0.05)
		# Use last 7 days. Only show positive, qualified performance.
		query = text("""
			SELECT
				u.username,
				u.tier,
				COUNT(o.id) AS tracked,
				SUM(CASE WHEN o.status LIKE 'tp%' THEN 1 ELSE 0 END) AS wins,
				SUM(CASE WHEN o.status = 'sl' THEN 1 ELSE 0 END) AS losses,
				AVG(o.r_multiple) AS avg_r
			FROM users u
			JOIN signal_deliveries sd ON sd.user_id = u.id
			JOIN signals s ON s.signal_id = sd.signal_id
			JOIN outcomes o ON o.signal_id = sd.signal_id
			WHERE o.closed_at >= NOW() - INTERVAL '7 days'
			  AND sd.sent_ok IS TRUE
			  AND COALESCE(s.performance_version, 1) >= :performance_version
			GROUP BY u.id, u.username, u.tier
			HAVING COUNT(o.id) >= :min_trades
			   AND AVG(o.r_multiple) >= :min_avg_r
			   AND (
			       SUM(CASE WHEN o.status LIKE 'tp%' THEN 1 ELSE 0 END)::float
			       / NULLIF(
			           SUM(CASE WHEN o.status LIKE 'tp%' OR o.status = 'sl' THEN 1 ELSE 0 END),
			           0
			       )
			   ) * 100.0 >= :min_win_rate
			ORDER BY avg_r DESC NULLS LAST, wins DESC
			LIMIT 15
		""")

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
			rows = (await session.execute(
				query,
				{
					"min_trades": min_trades,
					"min_win_rate": min_win_rate,
					"min_avg_r": min_avg_r,
					"performance_version": max(1, int(os.getenv("PERFORMANCE_BASELINE_VERSION", "2") or 2)),
				},
			)).fetchall()
			await session.commit()

		if not rows:
			await update.message.reply_text(
				"🏆 <b>Weekly Leaderboard</b>\n\n"
				"No qualifying entries yet this week.\n\n"
				"Leaderboard updates as signal outcomes are tracked.",
				parse_mode="HTML",
			)
			return

		viewer_in_vip = tier.upper() in {"VIP", "ADMIN", "OWNER"}
		lines = ["🏆 <b>Weekly Signal Leaderboard</b> (last 7 days)\n"]
		medals = ["🥇", "🥈", "🥉"]

		for i, row in enumerate(rows, 1):
			username = str(row[0] or "")
			row_tier = str(row[1] or "").upper()
			tracked = int(row[2] or 0)
			wins = int(row[3] or 0)
			losses = int(row[4] or 0)
			avg_r = float(row[5]) if row[5] is not None else 0.0

			win_rate = wins / max(1, wins + losses) * 100
			rank_emoji = medals[i - 1] if i <= 3 else f"#{i}"

			# Show username only for VIP users (privacy)
			if row_tier == "VIP" and username and viewer_in_vip:
				name_txt = f"@{username}"
			elif row_tier == "VIP":
				name_txt = "👑 VIP Member"
			else:
				name_txt = f"💎 Trader #{i}"

			r_sign = "+" if avg_r >= 0 else ""
			lines.append(
				f"{rank_emoji} <b>{name_txt}</b>\n"
				f"   {wins}W / {losses}L  •  {win_rate:.0f}% WR  •  Avg R: {r_sign}{avg_r:.2f}R\n"
			)

		lines.append("━━━━━━━━━━━━━━━━")
		if tier.upper() not in {"VIP", "ADMIN", "OWNER"}:
			lines.append("👑 Upgrade to VIP to appear on the leaderboard with your name.")
		else:
			lines.append("Your trades are included when their outcomes are recorded.")

		await update.message.reply_text("\n".join(lines), parse_mode="HTML")

	except Exception as exc:
		await update.message.reply_text(f"❌ Could not load leaderboard: {exc}")


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

	missing_vars = []
	if not (os.getenv("ENCRYPTION_KEY") or "").strip():
		missing_vars.append("ENCRYPTION_KEY")
	if not (os.getenv("META_API_TOKEN") or "").strip():
		missing_vars.append("META_API_TOKEN")
	if missing_vars:
		await update.message.reply_text(_railway_env_hint("MT5 linking", missing_vars))
		return -1

	await update.message.reply_text("⏳ Linking your account via MetaApi… (this may take 30–60 s)")

	try:
		from services.mt5_client import link_mt5_account
		result = await link_mt5_account(
			telegram_user_id=user_id,
			mt5_login=login,
			mt5_password=password,
			mt5_server=server,
		)
		if bool(result.get("success")):
			account_id = result.get("metaapi_account_id") or result.get("id") or "pending"
			await update.message.reply_text(
				f"✅ <b>MT5 account linked!</b>\n\n"
				f"☁️ MetaApi ID: <code>{account_id}</code>\n\n"
				"You can now use ⚡ buttons on signals to execute trades instantly.\n"
				"Use /setlot to configure your lot size.\n"
				"Use /execution manual|none|auto [count|all] to choose execution mode.",
				parse_mode="HTML",
			)
		else:
			err = str(result.get("error") or "unknown error")
			await update.message.reply_text(
				f"❌ <b>Failed to link account:</b> {err}\n\n"
				"Check your login/password/server and try /connect_broker again.",
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

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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
		await update.message.reply_text(msg, reply_markup=keyboard, parse_mode="MarkdownV2")

	except Exception as e:
		logger.error(f"[cancel] cancel_command failed for user {user_id}: {e}")
		await update.message.reply_text(
			"\u274c Could not process cancellation. Please contact /support."
		)


async def _cancel_and_disable_paystack(user_id: int) -> dict:
	"""Shared helper: call Paystack /subscription/disable and set auto_renew=False in DB.

	Returns:
	  {"success": bool, "gateway_cancelled": bool, "tier": str, "retry_attempts": int, "escalate_admin": bool}
	Used by cancel_confirm_callback to perform the actual cancellation work.
	"""
	try:
		from db.session import get_session
		from db.models import User
		from sqlalchemy import select, update as sa_update

		async with get_session(priority="interactive", label="signalrank_telegram_commands") as session:
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
			retry_attempts = 0
			if sub_code:
				try:
					import httpx as _httpx, os as _os
					secret = _os.getenv("PAYSTACK_SECRET_KEY", "").strip()
					if secret:
						try:
							max_retries = max(1, int(_os.getenv("PAYSTACK_CANCEL_RETRY_ATTEMPTS", "3") or 3))
						except Exception:
							max_retries = 3
						headers = {
							"Authorization": f"Bearer {secret}",
							"Content-Type": "application/json",
						}
						for attempt in range(1, max_retries + 1):
							retry_attempts = attempt
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
								if gateway_cancelled:
									break
				except Exception as _ge:
					# Non-fatal — DB cancellation still proceeds
					logger.warning(f"[cancel] Paystack gateway cancel failed: {_ge}")

			# Mark auto_renew=False; access expires naturally at period end (no downgrade)
			await session.execute(
				sa_update(User).where(User.id == user.id).values(auto_renew=False)
			)
			await session.commit()
			return {
				"success": True,
				"gateway_cancelled": gateway_cancelled,
				"tier": current_tier,
				"retry_attempts": int(retry_attempts),
				"escalate_admin": bool(sub_code and not gateway_cancelled),
			}

	except Exception as e:
		logger.error(f"[cancel] _cancel_and_disable_paystack failed for user {user_id}: {e}")
		return {"success": False, "gateway_cancelled": False, "tier": "free", "retry_attempts": 0, "escalate_admin": True}


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
				parse_mode="MarkdownV2",
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
			parse_mode="MarkdownV2",
		)
		if result.get("escalate_admin"):
			try:
				admin_msg = (
					f"⚠️ Paystack cancel gateway failed after retries.\n"
					f"user_id={int(user_id)} tier={tier} attempts={int(result.get('retry_attempts') or 0)}\n"
					"DB auto_renew was set to False."
				)
				target_ids = set()
				for _id in (list(ADMIN_IDS) + list(OWNER_IDS)):
					try:
						target_ids.add(int(_id))
					except Exception:
						continue
				for _chat_id in target_ids:
					try:
						await context.bot.send_message(chat_id=int(_chat_id), text=admin_msg)
					except Exception:
						pass
			except Exception:
				pass

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
			parse_mode="MarkdownV2",
		)
	except Exception as e:
		logger.warning(f"[cancel] cancel_nevermind_callback edit failed: {e}")
