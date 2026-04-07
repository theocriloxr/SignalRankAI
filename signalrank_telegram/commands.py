import os

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
from core.command_limits import (
	REQUIRE_TIER_RATE_LIMIT,
	PUBLIC_COMMAND_RATE_LIMIT,
	START_COMMAND_RATE_LIMIT,
	FREE_MIN_SCORE,
	FREE_SIGNAL_DAILY_LIMIT,
)

TIER_RANKS: dict[str, int] = {
	"FREE": 0,
	"PREMIUM": 1,
	"VIP": 2,
	"ADMIN": 3,
	"OWNER": 3,
}

def tier_rank(tier) -> int:
	return TIER_RANKS.get((tier or "").strip().upper(), 0)


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
				ks: KS = type("KS", (), {"enabled": False})()
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
		# Admin shortcut
		try:
			if int(user_id) in ADMIN_IDS:
				rows.append([InlineKeyboardButton("🛡️ Admin Dashboard", callback_data="admin_dashboard")])
		except Exception:
			pass
		return InlineKeyboardMarkup(rows)
	except Exception:
		return None


def _build_signal_action_keyboard(signal: dict | None = None):
	"""Build inline buttons for /signals output (chart + trade)."""
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		broker_prefix, asset = _chart_symbol_for_broker(signal)
		_chart_symbol = asset.replace("/", "").replace(" ", "")
		chart_url = "https://www.tradingview.com/chart/"
		if _chart_symbol:
			chart_url = f"https://www.tradingview.com/chart/?symbol={broker_prefix}:{_chart_symbol}"
		signal_id = str((signal or {}).get("signal_id") or "")[:36]
		trade_cb = f"mt5_trade_{signal_id}" if signal_id else "mt5_trade"
		rows = [[
			InlineKeyboardButton("📈 View Chart", url=chart_url),
			InlineKeyboardButton("⚡ Trade Now", callback_data=trade_cb),
		]]
		if signal_id:
			rows.append([
				InlineKeyboardButton("🔥 Taking It", callback_data=f"signal_reaction_{signal_id}|taking_it"),
				InlineKeyboardButton("👀 Watching", callback_data=f"signal_reaction_{signal_id}|watching"),
			])
			rows.append([
				InlineKeyboardButton("📈 Monitor", callback_data=f"monitor_signal_{signal_id}"),
				InlineKeyboardButton("🔍 Check Outcome", callback_data=f"check_outcome_{signal_id}"),
			])
		keyboard = InlineKeyboardMarkup(rows)
		return keyboard
	except Exception:
		return None


MAX_VIP_SEATS = 15


async def _get_live_vip_seat_state() -> tuple[int, int, bool]:
	vip_used = 0
	try:
		from db.session import get_engine_for_event_loop, get_session
		if get_engine_for_event_loop() is not None:
			from db.repository import count_active_vip_users
			async with get_session() as session:
				vip_used = await count_active_vip_users(session, exclude_telegram_user_ids=set())
	except Exception:
		pass
	vip_seats_left = max(0, int(MAX_VIP_SEATS) - int(vip_used))
	return vip_used, vip_seats_left, vip_seats_left <= 0


def _vip_plan_line(*, MarkdownV2: bool, seats_left: int, sold_out: bool) -> str:
	if sold_out:
		return "💎 VIP Monthly — ₦40,000 | 🔴 VIP Sold Out"
	if MarkdownV2:
		return f"💎 VIP Monthly — ₦40,000 | 🟢 {seats_left} seats left"
	return f"💎 VIP Monthly — ₦40,000 | 🟢 {seats_left} seats left"


async def _build_plan_keyboard(user_id: int, *, include_navigation: bool) -> object | None:
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		from paystack.paystack import generate_paystack_link
		_, vip_seats_left, vip_sold_out = await _get_live_vip_seat_state()
		rows = []
		if vip_sold_out:
			rows.append([InlineKeyboardButton("💎 VIP Sold Out", callback_data="vip_sold_out")])
			rows.append([InlineKeyboardButton("📋 Join VIP Waitlist", callback_data="vip_waitlist_join")])
		else:
			vip_link = generate_paystack_link(user_id=user_id, price=40000, tier="VIP", duration="MONTHLY", duration_days=30)
			if vip_link:
				rows.append([InlineKeyboardButton(f"💎 VIP Monthly — ₦40,000 ({vip_seats_left} left)", url=vip_link)])
		prem_month_price = int(os.getenv("PREMIUM_MONTHLY_PRICE_NGN", "24000"))
		prem_qtr_price = int(os.getenv("PREMIUM_QUARTERLY_PRICE_NGN", "56000"))
		prem_year_price = int(os.getenv("PREMIUM_YEARLY_PRICE_NGN", "192000"))
		prem_month = generate_paystack_link(user_id=user_id, price=prem_month_price, tier="PREMIUM", duration="MONTHLY", duration_days=30)
		prem_qtr = generate_paystack_link(user_id=user_id, price=prem_qtr_price, tier="PREMIUM", duration="QUARTERLY", duration_days=90)
		prem_year = generate_paystack_link(user_id=user_id, price=prem_year_price, tier="PREMIUM", duration="YEARLY", duration_days=365)
		if prem_month:
			rows.append([InlineKeyboardButton(f"⭐ Premium Monthly — ₦{prem_month_price:,}", url=prem_month)])
		if prem_qtr:
			rows.append([InlineKeyboardButton(f"⭐ Premium Quarterly — ₦{prem_qtr_price:,}", url=prem_qtr)])
		if prem_year:
			rows.append([InlineKeyboardButton(f"🔥 Premium Yearly (Best Value) — ₦{prem_year_price:,}", url=prem_year)])
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
	_, vip_seats_left, vip_sold_out = await _get_live_vip_seat_state()
	vip_line = _vip_plan_line(MarkdownV2=False, seats_left=vip_seats_left, sold_out=vip_sold_out)
	prem_month_price = int(os.getenv("PREMIUM_MONTHLY_PRICE_NGN", "24000"))
	prem_qtr_price = int(os.getenv("PREMIUM_QUARTERLY_PRICE_NGN", "56000"))
	prem_year_price = int(os.getenv("PREMIUM_YEARLY_PRICE_NGN", "192000"))
	msg = (
		"🚀 SignalRankAI — Choose Your Plan\n\n"
		f"{vip_line}\n"
		f"⭐ Premium — ₦{prem_month_price:,}/mo · ₦{prem_qtr_price:,}/qtr · ₦{prem_year_price:,}/yr (Best Value)\n\n"
		"⚠️ Trading involves risk. No guaranteed returns."
	)
	keyboard = await _build_plan_keyboard(int(user_id), include_navigation=False)
	return msg, keyboard


async def _compose_upgrade_message(user_id: int) -> tuple[str, object | None]:
	_, vip_seats_left, vip_sold_out = await _get_live_vip_seat_state()
	vip_line = _vip_plan_line(MarkdownV2=True, seats_left=vip_seats_left, sold_out=vip_sold_out)
	prem_month_price = int(os.getenv("PREMIUM_MONTHLY_PRICE_NGN", "24000"))
	prem_qtr_price = int(os.getenv("PREMIUM_QUARTERLY_PRICE_NGN", "56000"))
	prem_year_price = int(os.getenv("PREMIUM_YEARLY_PRICE_NGN", "192000"))
	msg = (
		"🚀 *SignalRankAI — Choose Your Plan*\n\n"
		f"{vip_line}\n"
		f"⭐ Premium — ₦{prem_month_price:,}/mo · ₦{prem_qtr_price:,}/qtr · ₦{prem_year_price:,}/yr \\(Best Value\\)\n\n"
		"✅ *What you unlock:*\n"
		"• Premium: broader trade coverage, full Entry/SL/TP, analytics tools\n"
		"• VIP: stricter quality stream, priority delivery, elite automation controls\n\n"
		"⚠️ _No guaranteed profits. Trade responsibly._\n\n"
		"_Tap a plan below to subscribe instantly via Paystack:_"
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
	if data.startswith("trade_now_"):
		try:
			signal_id = str(data.replace("trade_now_", "", 1) or "").strip()[:36]
			if signal_id:
				from telegram import InlineKeyboardMarkup, InlineKeyboardButton
				new_kbd = InlineKeyboardMarkup([
					[InlineKeyboardButton("⚡ Trade Now", callback_data=f"mt5_trade_{signal_id}")],
					[
						InlineKeyboardButton("📈 Monitor", callback_data=f"monitor_signal_{signal_id}"),
						InlineKeyboardButton("🔍 Check Outcome", callback_data=f"check_outcome_{signal_id}"),
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
						[InlineKeyboardButton("⚡ Take Trade", callback_data=f"mt5_trade_{signal_id}")]
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

	threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.65"))

	try:
		from db.session import get_session
		from db.models import Signal, AdminEvent
		from sqlalchemy import select
		from datetime import datetime, timedelta
		cutoff = datetime.utcnow() - timedelta(hours=4)
		async with get_session() as session:
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
			session.add(
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
			await session.commit()
		except Exception:
			pass

	except Exception:
		await update.message.reply_text("⚠️ Scan failed. Check logs for details.")
		return

	await update.message.reply_text(
		f"🤖 Market scan complete. Signals={len(signals)} | "
		f"approved={approved} | rejected={rejected} | errors={errors} | "
		f"threshold={threshold:.2f}"
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
	expires = datetime.utcnow() + timedelta(days=max(1, min(int(ttl_days), 365)))
	async with get_session() as session:
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
	async with get_session() as session:
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
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	if get_engine_for_event_loop() is None:
		await update.message.reply_text("Database unavailable.")
		return
	async with get_session() as session:
		from sqlalchemy import select, func, desc

		res = await session.execute(
			select(
				ReferralAttribution.referrer_user_id,
				func.count(ReferralAttribution.id).label("cnt"),
			)
			.group_by(ReferralAttribution.referrer_user_id)
			.order_by(desc("cnt"))
			.limit(10)
		)
		rows = list(res.all() or [])
		if not rows:
			await update.message.reply_text("No referral data yet.")
			await session.commit()
			return

		# Get usernames if possible
		ids = [int(r[0]) for r in rows]
		users = {}
		if ids:
			res2 = await session.execute(
				select(User.id, User.telegram_user_id, User.username).where(User.id.in_(ids))
			)
			users = {int(r[0]): (r[1], r[2]) for r in (res2.all() or [])}

		msg = "🏆 Referral Leaderboard:\n\n"
		for i, (uid, cnt) in enumerate(rows, 1):
			uid = int(uid)
			telegram_uid, username = users.get(uid, (None, None))
			if username:
				uname = f"@{username}"
			elif telegram_uid:
				uname = f"User ***{str(telegram_uid)[-3:]}"
			else:
				uname = f"User ***{str(uid)[-3:]}"
			msg += f"{i}. {uname}: {cnt} referrals\n"
		await session.commit()
		await update.message.reply_text(msg)

async def referral_rewards_command(update, context) -> None:
	if await _public_guard(update):
		return
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	if get_engine_for_event_loop() is None:
		await update.message.reply_text("Database unavailable.")
		return
	async with get_session() as session:
		user: User = await get_or_create_user(session, telegram_user_id=int(user_id))
		from sqlalchemy import select, func
		from db.pg_features import get_referral_progress

		res = await session.execute(
			select(
				ReferralReward.reward_type,
				func.count(ReferralReward.id).label("cnt"),
				func.coalesce(func.sum(ReferralReward.reward_value), 0).label("total"),
			)
			.where(ReferralReward.referrer_user_id == int(user.id))
			.group_by(ReferralReward.reward_type)
		)
		rows = list(res.all() or [])

		progress = await get_referral_progress(session, referrer_telegram_user_id=int(user_id))
		total_refs = int(progress.get("total", 0) or 0)
		toward_next = int(progress.get("toward_next", 0) or 0)
		needed = int(progress.get("needed_for_next", 0) or 0)

		total_days = 0
		for rtype, _cnt, total in rows:
			if str(rtype).lower().startswith("premium_days"):
				total_days += int(total or 0)

		if not rows:
			msg = "No rewards earned yet. Refer friends to earn rewards!"
		else:
			msg = "🎁 Your Referral Rewards:\n"
			for rtype, cnt, total in rows:
				msg += f"• {rtype}: {int(cnt or 0)} time(s), total value: {int(total or 0)}\n"

		if total_days > 0:
			msg += f"\n✅ Total premium days earned: +{total_days}"

		msg += f"\n\n📊 Progress: {toward_next}/3"
		if needed > 0:
			msg += f" (invite {needed} more for next +7 days)"
		else:
			msg += " (milestone reached on latest referral)"
		msg += f"\n👥 Total referrals: {total_refs}"
		await session.commit()
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
			parse_mode="MarkdownV2",
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
		await update.message.reply_text(f"✅ `{symbol}` pinned ({atype}).", parse_mode="MarkdownV2")
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
			await update.message.reply_text(f"❌ `{symbol}` unpinned.", parse_mode="MarkdownV2")
		else:
			await update.message.reply_text(f"`{symbol}` was not in the managed list.", parse_mode="MarkdownV2")
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
from telegram.helpers import escape_markdown
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
	return {
		1: {
			"title": "🟢 Basics & Free",
			"required_tier": "FREE",
			"commands": [
				("/start", "Start or re-register the bot"),
				("/help", "Open the paginated help menu"),
				("/status", "Check your current tier and subscription"),
				("/tiers", "See tier feature differences"),
				("/signals", "View the latest signal feed"),
				("/proof", "See recent verified outcomes and wins"),
				("/signal", "Look up a specific signal by reference"),
				("/outcome", "Check the result of a delivered signal"),
				("/pricing", "See current plan pricing"),
				("/upgrade", "Open the upgrade menu"),
				("/liveprice", "Fetch the real-time price of any asset"),
				("/market", "View a quick market overview"),
				("/leaderboard", "View weekly performance leaderboard"),
				("/language", "Change language preference"),
				("/invite", "Get your referral link and rewards status"),
				("/referral_leaderboard", "View top referrers"),
				("/referral_rewards", "See referral reward details"),
				("/support", "Contact support"),
				("/faq", "Common questions and answers"),
				("/about", "About SignalRankAI"),
				("/disclaimer", "Financial risk disclaimer"),
				("/policy", "Subscription and refund policy"),
				("/refunds", "Subscription and refund policy"),
				("/recap", "Weekly performance recap"),
				("/myid", "View your Telegram ID and tier"),
			],
			"footer": "Tip: start with /proof, /signals, /status, and /upgrade if you want more access.",
		},
		2: {
			"title": "⭐️ Premium Analytics",
			"required_tier": "PREMIUM",
			"commands": [
				("/performance", "30-day performance summary"),
				("/quality", "24h reject-reason quality diagnostics"),
				("/stats", "Win rate, avg R, and net R"),
				("/history", "Recent signal history"),
				("/mystats", "Personal trading and signal stats"),
				("/execution", "Set execution mode (none/manual; auto on VIP)"),
				("/drawdown", "Set daily drawdown auto-pause threshold"),
				("/alerts", "Custom TP/SL alerts and quiet hours"),
				("/analyze", "AI market analysis for any asset"),
				("/filter", "Custom score, RR, and regime filters"),
				("/notify", "Signal notification preferences"),
				("/reports", "Opt into scheduled summaries"),
				("/account", "View profile and subscription details"),
				("/feedback", "Rate a signal or report an issue"),
				("/dashboard", "Open your analytics dashboard"),
				("/portfolio", "Track active positions and P&L"),
				("/apikey", "Get your API key for integrations"),
				("/referral", "View your referral link and stats"),
				("/cancel", "Cancel subscription auto-renewal"),
				("/mt5", "Show MT5 quick help and status"),
				("/mt5_link", "Link your MT5 account"),
				("/mt5_status", "Check MT5 connection status"),
				("/connect_broker", "Broker connection walkthrough"),
				("/setlot", "Set fixed lot size"),
			],
			"footer": "⭐️ Upgrade to unlock these features.",
		},
		3: {
			"title": "💎 VIP Exclusive",
			"required_tier": "VIP",
			"commands": [
				("/setrisk", "Set risk limits per trade"),
				("/elite", "High-conviction elite signals"),
				("/early", "Early-access VIP flow"),
				("/report", "VIP monthly performance report"),
			],
			"footer": "💎 VIP includes all Free and Premium commands plus these exclusives.",
		},
		4: {
			"title": "👑 Admin & God Mode",
			"required_tier": "ADMIN",
			"commands": [
				("/admin", "Open the admin dashboard"),
				("/admin_dashboard", "Open extended admin dashboard"),
				("/gemini", "Run all-time Gemini review + ML retrain"),
				("/gemini_review", "Show latest Gemini review/training rundown"),
				("/admin_top_assets", "Top assets by signal quality"),
				("/admin_top_strategies", "Top strategies by performance"),
				("/admin_user_engagement", "User engagement analytics"),
				("/admin_broadcast", "Broadcast a message to users"),
				("/assets", "Manage pinned asset universe"),
				("/force_market_scan", "Run the ML market scan now"),
				("/dev_pause", "Pause the engine"),
				("/dev_resume", "Resume the engine"),
				("/force_signal", "Generate and send a fresh signal"),
				("/version", "Runtime/build diagnostic info"),
				("/owner_users", "Inspect user metrics"),
				("/owner_revenue", "Review revenue analytics"),
				("/correct_signal", "Correct a signal outcome"),
				("/blast_terms", "Send terms gate prompts"),
				("/provider_status", "Inspect provider health"),
				("/selfcheck", "Run a system health check"),
			],
			"footer": "Restricted admin surface.",
		},
	}


def _help_authorized_pages(user_id: int) -> list[int]:
	pages = [1, 2, 3]
	try:
		uid = int(user_id)
		if uid in ADMIN_IDS or uid in OWNER_IDS:
			pages.append(4)
	except Exception:
		pass
	return pages


def _help_page_is_locked(user_id: int, page: int) -> bool:
	tier = _effective_tier(int(user_id))
	page_defs = _help_page_definitions()
	page_info = page_defs.get(int(page), {})
	required_tier = str(page_info.get("required_tier") or "FREE")
	if int(page) == 4:
		try:
			uid = int(user_id)
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
		from sqlalchemy import select, func
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

		async with get_session() as session:
			user_row = (await session.execute(
				select(User).where(User.telegram_user_id == user_id)
			)).scalar_one_or_none()

			cutoff = datetime.utcnow() - timedelta(days=30)
			db_user_id = user_row.id if user_row else None

			# Signals received in last 30d
			total_signals = 0
			wins = 0
			losses = 0
			if db_user_id:
				total_signals = (await session.execute(
					select(func.count(SignalDelivery.id)).where(
						SignalDelivery.user_id == db_user_id,
						SignalDelivery.delivered_at >= cutoff,
					)
				)).scalar() or 0

				oc_rows = (await session.execute(
					select(Outcome)
					.join(SignalDelivery, SignalDelivery.signal_id == Outcome.signal_id)
					.where(
						SignalDelivery.user_id == db_user_id,
						Outcome.closed_at >= cutoff,
					)
				)).scalars().all()
				wins = sum(1 for o in oc_rows if str(o.status or "").startswith("tp"))
				losses = sum(1 for o in oc_rows if o.status == "sl")
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
			f"📊 <b>Dashboard — {tier.upper()}</b>\n\n"
			f"🎯 Signals (30d): <b>{total_signals}</b>\n"
			f"✅ Wins: <b>{wins}</b>  ❌ Losses: <b>{losses}</b>\n"
			f"📈 Win rate: <b>{win_rate:.1f}%</b>\n"
			f"⚙️ Execution mode: <b>{exec_mode}</b>"
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
	"""Show user's signals with tier-specific formatting.
	
	FREE: Show last 5 delivered today (resolved + unresolved proof cards)
	PREMIUM/VIP: Show unresolved active signals from last 30 days
	"""
	if await _public_guard(update):
		return
	if update.message is None and getattr(update, "callback_query", None) is not None:
		try:
			update.message = update.callback_query.message
		except Exception:
			pass
	if update.message is None:
		return
	user_id: int = update.effective_user.id
	tier: str = _effective_tier(user_id)
	show_unvoted_only: bool = False
	try:
		arg0 = str((context.args or [""])[0] or "").strip().lower()
		show_unvoted_only = arg0 in {"unvoted", "pending", "notvoted"}
	except Exception:
		show_unvoted_only = False
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		_nav_kbd = InlineKeyboardMarkup([
			[
				InlineKeyboardButton("📊 Performance", callback_data="nav_performance"),
				InlineKeyboardButton("🚀 Upgrade", callback_data="nav_upgrade"),
			],
			[
				InlineKeyboardButton("👤 Account", callback_data="nav_account"),
				InlineKeyboardButton("🆘 Support", callback_data="nav_support"),
			],
		])
	except Exception:
		_nav_kbd = None
	
	# Import freshness validation at function level
	from engine.price_validator import enrich_signal_with_live_price

	# Owner and admin always get VIP format
	if tier.lower() in {"owner", "admin"}:
		tier = "VIP"

	signals_list: list[dict] = []

	async def _filter_unvoted(signals_in: list[dict]) -> list[dict]:
		if not show_unvoted_only or not signals_in:
			return signals_in
		try:
			from sqlalchemy import select
			from db.models import SignalEngagement, User
			from db.session import get_session
			signal_ids = [str(s.get("signal_id") or "") for s in signals_in if s.get("signal_id")]
			if not signal_ids:
				return []
			async with get_session() as session:
				user_row = (await session.execute(
					select(User).where(User.telegram_user_id == int(user_id)).limit(1)
				)).scalar_one_or_none()
				if user_row is None:
					return signals_in
				engaged_rows = await session.execute(
					select(SignalEngagement.signal_id)
					.where(
						SignalEngagement.user_id == int(user_row.id),
						SignalEngagement.signal_id.in_(signal_ids),
					)
				)
				engaged_set = {str(x) for x in (engaged_rows.scalars().all() or [])}
				await session.commit()
			return [s for s in signals_in if str(s.get("signal_id") or "") not in engaged_set]
		except Exception:
			return signals_in
	
	# FREE tier: show last 5 delivered signals from today (resolved + unresolved).
	if tier_rank(tier) < tier_rank("PREMIUM"):
		try:
			from db.session import get_session
			engine = get_engine_for_event_loop()
			if engine is not None:
				from db.pg_features import list_signals_sent_today
				async with get_session() as session:
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
				await update.message.reply_text("✅ No signal proof cards yet today. Check back after the next cycle.")
			return

		signals_list = await _filter_unvoted(signals_list)
		eligible = list(signals_list)

		if not eligible:
			if update.message is not None:
				from core.tier_constants import TIER_SCORE_THRESHOLDS
				free_min = int(float(TIER_SCORE_THRESHOLDS.get("free", FREE_MIN_SCORE)))
				if show_unvoted_only:
					await update.message.reply_text("✅ No unvoted FREE proof cards right now.")
				else:
					await update.message.reply_text(
						f"⚠️ No FREE-eligible proof cards ({free_min}+) right now. Upgrade for full active feed access."
					)
			return
		picked = eligible[:5]
		from .formatter import format_signal_free_new
		for s in picked:
			try:
				formatted = format_signal_free_new(
					s,
					signals_sent_today=len(signals_list),
					daily_limit=int(FREE_SIGNAL_DAILY_LIMIT),
				)
				if formatted and update.message is not None:
					await update.message.reply_text(
						formatted,
						parse_mode="HTML",
						reply_markup=_build_signal_action_keyboard(s),
					)
			except Exception as e:
				_audit_logger.error(f"Error formatting free signal for {user_id}: {e}")
		if update.message is not None:
			await update.message.reply_text("👆 Upgrade to PREMIUM for full signal intelligence, full TP ladder and execution tools.")
		return
	
	# PREMIUM/VIP: show unresolved active signals delivered in the last 30 days.
	unresolved_signals: list[dict] = []
	try:
		from db.session import get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
			from db.pg_features import list_unresolved_signals_for_user
			async with get_session() as session:
				rows: list[Signal] = await list_unresolved_signals_for_user(
					session,
					telegram_user_id=int(user_id),
					lookback_days=30,
				)
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
	unresolved_signals = await _filter_unvoted(unresolved_signals)
	filtered_signals = []
	for s in unresolved_signals:
		# PREMIUM/VIP/ADMIN/OWNER: show active unresolved signals user received.
		filtered_signals.append(s)

	if not filtered_signals:
		if update.message is not None:
			if show_unvoted_only:
				await update.message.reply_text("✅ No unvoted active unresolved signals right now.")
			else:
				await update.message.reply_text(
					"✅ No active unresolved signals in your range right now."
				)
		return

	# PREMIUM/VIP: use consistent box-style template
	from .formatter import format_signal

	total_active: int = len(filtered_signals)
	if update.message is not None and total_active > 0:
		await update.message.reply_text(f"📊 Your Active Signals ({total_active} in last 30 days):")

	for idx, s in enumerate(filtered_signals, 1):
		try:
			formatted = format_signal(s, user_tier=tier)
			if not formatted:
				continue
			if update.message is not None:
				await update.message.reply_text(
					formatted,
					parse_mode="HTML",
					reply_markup=_build_signal_action_keyboard(s),
				)
		except Exception as e:
			_audit_logger.error(f"Error formatting signal for {user_id}: {e}")
			continue


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
			async with get_session() as session:
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
		from db.pg_features import list_unresolved_signals_for_user, get_delivered_signal_by_ref
		from .formatter import format_signal, format_signal_free_limited

		if arg.lower() == "all":
			async with get_session() as session:
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

		try:
			from datetime import datetime, timedelta, timezone
			_created = getattr(sig, "created_at", None)
			if _created is not None:
				_created_utc = _created if getattr(_created, "tzinfo", None) is not None else _created.replace(tzinfo=timezone.utc)
				if _created_utc < datetime.now(timezone.utc) - timedelta(days=1):
					await update.message.reply_text("⏰ This signal is older than 24h and is no longer active.")
					return
		except Exception:
			pass
		if oc is not None:
			await update.message.reply_text("✅ This signal already has an outcome. Use /outcome <ref> for details.")
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
					# Only admin/owner can view or manually resolve undelivered signals
					if not _is_admin(user_id):
						await update.message.reply_text("⚠️ This is not your signal. You were not sent this trade.")
						return
					sig = undelivered_sig
				else:
					await update.message.reply_text("Signal not found.")
					return

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
				f"Reference: {sig.signal_id[:8]}",
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
	user_id: int = update.effective_user.id
	code = None
	progress = None
	try:
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is None:
			try:
				from db.session import _get_global_engine
				engine = _get_global_engine()
			except Exception:
				engine = None
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
	if update.effective_user is None or update.message is None:
		return
	user_id = update.effective_user.id
	msg, keyboard = await _compose_pricing_message(int(user_id))
	await update.message.reply_text(msg, reply_markup=keyboard)


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
	await update.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=keyboard)


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
					async with get_session() as session:
						logger.info("[/start] user_id=%s — DB session open, querying user row (attempt=%s)", user_id, attempt)
						res: Result[Tuple[User]] = await asyncio.wait_for(
							session.execute(select(User).where(User.telegram_user_id == int(user_id))),
							timeout=timeout_s,
						)
						existing: User | None = res.scalar_one_or_none()
						is_new: bool = existing is None
						user_row = await asyncio.wait_for(
							get_or_create_user(session, telegram_user_id=user_id, username=username),
							timeout=timeout_s,
						)
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
							except Exception:
								referral_outcome = None

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
					text=(
						f"🎁 Bonus Plan Extension\n\n"
						f"+{days} premium days have been added to your current plan!\n\n"
						"Use /signals to get the latest trading ideas."
					)
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
		await update.message.reply_text(disclaimer, parse_mode="MarkdownV2", reply_markup=_kbd)
		return  # Hold back welcome message until terms are accepted

	# Terms already accepted — send normal welcome
	_tier = _effective_tier(int(user_id))
	_kbd_start = _build_dynamic_menu(user_id=int(user_id), tier=_tier)
	await update.message.reply_text(msg, reply_markup=_kbd_start)

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
async def performance_command(update, context):
	if await _public_guard(update):
		return
	from datetime import datetime, timedelta
	if update.message is None and getattr(update, "callback_query", None) is not None:
		try:
			update.message = update.callback_query.message
		except Exception:
			pass
	if update.message is None:
		return
	user_id = update.effective_user.id
	tier: str = _effective_tier(user_id)
	try:
		from telegram import InlineKeyboardMarkup, InlineKeyboardButton
		_perf_kbd = InlineKeyboardMarkup([
			[
				InlineKeyboardButton("📈 Signals", callback_data="nav_signals"),
				InlineKeyboardButton("👤 Account", callback_data="nav_account"),
			],
			[
				InlineKeyboardButton("🚀 Upgrade", callback_data="nav_upgrade"),
				InlineKeyboardButton("🆘 Support", callback_data="nav_support"),
			],
		])
	except Exception:
		_perf_kbd = None

	# Prefer Postgres (deliveries + outcomes)
	try:
		from db.session import get_engine_for_event_loop, get_session
		engine = get_engine_for_event_loop()
		if engine is not None:
			from db.pg_features import get_user_performance_30d
			from sqlalchemy import text

			async def _fallback_performance_stats(session, tg_user_id: int) -> dict[str, object]:
				"""Fallback aggregate in case helper query fails in production."""
				row = (
					await session.execute(
						text(
							"""
							SELECT
							  COUNT(DISTINCT sd.id) AS total,
							  SUM(CASE WHEN LOWER(COALESCE(o.status, '')) IN ('tp','tp1','tp2','partial_tp') THEN 1 ELSE 0 END) AS wins,
							  SUM(CASE WHEN LOWER(COALESCE(o.status, '')) = 'sl' THEN 1 ELSE 0 END) AS losses,
							  AVG(o.r_multiple) AS avg_r,
							  SUM(o.r_multiple) AS net_r
							FROM users u
							LEFT JOIN signal_deliveries sd
							  ON sd.user_id = u.id
							  AND sd.delivered_at >= (NOW() - INTERVAL '30 days')
							LEFT JOIN outcomes o
							  ON o.signal_id = sd.signal_id
							WHERE u.telegram_user_id = :uid
							"""
						),
						{"uid": int(tg_user_id)},
					)
				).first()
				if not row:
					return {
						"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
						"avg_r": None, "net_r": None, "tracked_outcomes": 0, "profit_loss_pct": 0.0,
					}
				total = int(row[0] or 0)
				wins = int(row[1] or 0)
				losses = int(row[2] or 0)
				tracked = wins + losses
				avg_r = float(row[3]) if row[3] is not None else None
				net_r = float(row[4]) if row[4] is not None else None
				profit_loss_pct = ((float(net_r) / tracked) * 1.0) if (net_r is not None and tracked > 0) else 0.0
				return {
					"total": total,
					"wins": wins,
					"losses": losses,
					"win_rate": (wins / max(1, tracked)) if tracked > 0 else 0.0,
					"avg_r": avg_r,
					"net_r": net_r,
					"tracked_outcomes": tracked,
					"profit_loss_pct": float(profit_loss_pct),
				}

			# Fetch performance stats
			stats = {}
			try:
				async with get_session() as session:
					stats = await get_user_performance_30d(session, int(user_id))
			except Exception as e:
				_audit_logger.error(f"/performance db fetch failed for user={user_id}: {e}")
				try:
					async with get_session() as session:
						stats = await _fallback_performance_stats(session, int(user_id))
				except Exception as e2:
					_audit_logger.error(f"/performance fallback query failed for user={user_id}: {e2}")

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
						res_u = await session.execute(select(User).where(User.telegram_user_id == int(user_id)))
						u = res_u.scalar_one_or_none()
						if u is None:
							deliveries_30d = 0
						else:
							res_d = await session.execute(
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
					await update.message.reply_text(msg, reply_markup=_perf_kbd)
				return

			if tier_rank(tier) < tier_rank("PREMIUM"):
				bucket: str = "strong" if win_rate >= 0.6 else ("cautious" if win_rate <= 0.4 else "mixed")
				msg: str = (
					"📊 Performance (limited)\n\n"
					f"Recent trend: {bucket}.\n"
					"Upgrade to Premium for full stats and history."
				)
				if update.message is not None:
					await update.message.reply_text(msg, reply_markup=_perf_kbd)
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
				await update.message.reply_text(msg, reply_markup=_perf_kbd)
			return
	except Exception as e:
		_audit_logger.error(f"/performance failed for user={user_id}: {e}")
		if update.message is not None:
			await update.message.reply_text(
				"No performance data available right now. Use /signals for recent activity.",
				reply_markup=_perf_kbd,
			)
		return


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

		cutoff = datetime.utcnow() - timedelta(hours=24)
		rows = []
		async with get_session() as session:
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
				"📉 Quality (last 24h)\n\nNo decision data yet. Check again after more cycles.",
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
		async with get_session() as session:
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
		for s in rows:
			oc = oc_map.get(s.signal_id)
			if oc is not None and oc.status:
				status_u = str(oc.status).upper()
				oc_emoji = "✅" if oc.status.startswith("tp") else ("❌" if oc.status == "sl" else "⏳")
				r_txt = ""
				if oc.r_multiple is not None:
					r_sign = "+" if float(oc.r_multiple) >= 0 else ""
					r_txt = f" | {r_sign}{float(oc.r_multiple):.1f}R"
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

		lines.append("\n💡 /signal &lt;ref&gt; for full signal details")
		if update.message is not None:
			await update.message.reply_text("\n".join(lines), parse_mode="HTML")
		return

	except Exception as exc:
		if update.message is not None:
			await update.message.reply_text(f"❌ Could not load history: {exc}")


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

		timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
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

		async with get_session() as session:
			# Resolve the DB user record to get the FK id used in signal_deliveries
			user_row = (await session.execute(
				select(User).where(User.telegram_user_id == user_id)
			)).scalar_one_or_none()
			if user_row is None:
				await update.message.reply_text("⚠️ User profile not found. Send /start first.")
				return

			# Get signals delivered to this user (active = not archived, last 72 h)
			cutoff = datetime.utcnow() - timedelta(hours=72)
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
		timestamp = datetime.utcnow().strftime("%H:%M UTC")

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
			"⚙️ *Link your MT5 Account*\n\n"
			"Usage: `/mt5_link <login> <password> <server>`\n\n"
			"Example:\n`/mt5_link 123456 MyP@ssw0rd MetaQuotes-Demo`\n\n"
			"🔒 Your password is encrypted end-to-end with AES-256 (Fernet) before storage.\n"
			"Neither SignalRankAI staff nor Railway can read it in plaintext.",
			parse_mode="MarkdownV2"
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
		from services.mt5_client import get_user_mt5_account_id
		from db.session import get_session
		from db.models import MT5Credentials, User
		from sqlalchemy import select
		async with get_session() as session:
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
		reply += "\nUse ⚡ buttons on signals to trade instantly."
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
					row.updated_at = datetime.utcnow()
					await session.commit()
				await update.message.reply_text("✅ VIP execution webhook disabled.")
				return
			if row is None:
				session.add(
					UserWebhook(
						user_id=int(user.id),
						webhook_url=raw,
						is_active=True,
						updated_at=datetime.utcnow(),
					)
				)
			else:
				row.webhook_url = raw
				row.is_active = True
				row.updated_at = datetime.utcnow()
			await session.commit()
		await update.message.reply_text("✅ VIP execution webhook saved.")
	except Exception as exc:
		await update.message.reply_text(f"❌ Could not save webhook: {exc}")


async def execution_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Configure broker execution mode: none | manual | auto.

	Usage:
	  /execution                      -> show current mode
	  /execution manual               -> one-click only
	  /execution none                 -> disable broker execution
	  /execution auto 5               -> auto execute up to 5/day
	  /execution auto all             -> unlimited auto executions
	"""
	if update.effective_user is None or update.message is None:
		return

	user_id: int = int(update.effective_user.id)
	tier: str = _effective_tier(user_id)

	if tier_rank(tier) < tier_rank("PREMIUM"):
		await update.message.reply_text(
			"🔒 /execution is available on <b>PREMIUM</b> and above.",
			parse_mode="HTML",
		)
		return

	try:
		from db.session import get_session as _gs
		from db.models import User
		from sqlalchemy import select

		args = [str(a).strip().lower() for a in (context.args or []) if str(a).strip()]

		async with _gs() as session:
			row = (await session.execute(select(User).where(User.telegram_user_id == user_id))).scalar_one_or_none()
			if row is None:
				await update.message.reply_text("❌ User profile not found. Send /start and try again.")
				return

			if not args:
				mode = str(getattr(row, "execution_mode", "manual") or "manual").lower()
				cap = int(getattr(row, "auto_signals_daily_limit", 3) or 0)
				cap_txt = "all" if cap < 0 else str(cap)
				await update.message.reply_text(
					"⚙️ <b>Execution Settings</b>\n\n"
					f"Mode: <b>{mode.upper()}</b>\n"
					f"AUTO daily cap: <b>{cap_txt}</b>\n\n"
					"Use: <code>/execution none|manual|auto [count|all]</code>",
					parse_mode="HTML",
				)
				return

			mode = args[0]
			if mode not in {"none", "manual", "auto"}:
				await update.message.reply_text(
					"❌ Invalid mode. Use <code>none</code>, <code>manual</code> or <code>auto</code>.",
					parse_mode="HTML",
				)
				return

			if mode == "auto" and tier_rank(tier) < tier_rank("VIP"):
				await update.message.reply_text(
					"🔒 AUTO mode requires <b>VIP</b>. PREMIUM supports NONE/MANUAL.",
					parse_mode="HTML",
				)
				return

			cap = int(getattr(row, "auto_signals_daily_limit", 3) or 3)
			if mode == "auto":
				if len(args) >= 2:
					arg2 = args[1]
					if arg2 == "all":
						cap = -1
					else:
						try:
							cap = max(1, min(int(arg2), 100))
						except Exception:
							await update.message.reply_text("❌ Invalid AUTO cap. Use number or 'all'.")
							return

			row.execution_mode = mode
			row.auto_signals_daily_limit = int(cap)
			optin_key = f"autoexec_user_optin:{int(user_id)}"
			if mode == "auto":
				await session.execute(
					text(
						"""
						INSERT INTO runtime_state(key, value, expires_at, updated_at)
						VALUES (:k, CAST(:v AS JSONB), NULL, NOW())
						ON CONFLICT (key) DO UPDATE
						SET value = EXCLUDED.value, expires_at = NULL, updated_at = NOW()
						"""
					),
					{"k": optin_key, "v": '{"enabled": true}'},
				)
			else:
				await session.execute(
					text("DELETE FROM runtime_state WHERE key = :k"),
					{"k": optin_key},
				)
			await session.commit()

		cap_txt = "all" if int(cap) < 0 else str(int(cap))
		await update.message.reply_text(
			"✅ <b>Execution mode updated</b>\n\n"
			f"Mode: <b>{mode.upper()}</b>\n"
			f"AUTO daily cap: <b>{cap_txt}</b>",
			parse_mode="HTML",
		)
	except Exception as exc:
		await update.message.reply_text(f"❌ Could not update execution mode: {exc}")


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
	"""Generate a personal referral link and show referral stats."""
	if update.effective_user is None or update.message is None:
		return
	user_id: int = update.effective_user.id

	bot_username = ""
	try:
		bot_username = (await context.bot.get_me()).username or ""
	except Exception:
		bot_username = os.getenv("BOT_USERNAME", "")
	bot_username = (bot_username or "").strip().lstrip("@")

	referral_code = str(user_id)
	referral_url = ""
	bonus_days = int(os.getenv("REFERRAL_BONUS_DAYS", "7"))

	# Source of truth: referral_code + attributions + reward ledger in Postgres.
	referred_count = 0
	toward_next = 0
	needed_for_next = 0
	bonus_earned_days = 0
	try:
		from db.session import get_session as _gs
		from db.models import User, ReferralReward
		from sqlalchemy import select, func
		from db.pg_features import get_or_create_referral_code, get_referral_progress

		async with _gs() as session:
			referral_code = await get_or_create_referral_code(session, referrer_telegram_user_id=int(user_id))
			progress = await get_referral_progress(session, referrer_telegram_user_id=int(user_id))
			referred_count = int(progress.get("total", 0) or 0)
			toward_next = int(progress.get("toward_next", 0) or 0)
			needed_for_next = int(progress.get("needed_for_next", 0) or 0)

			user_row = (await session.execute(
				select(User).where(User.telegram_user_id == int(user_id))
			)).scalar_one_or_none()
			if user_row is not None:
				bonus_earned_days = int((await session.execute(
					select(func.coalesce(func.sum(ReferralReward.reward_value), 0)).where(
						ReferralReward.referrer_user_id == user_row.id,
						ReferralReward.reward_type == "premium_days",
					)
				)).scalar() or 0)
	except Exception:
		pass

	if bot_username:
		referral_url = f"https://t.me/{bot_username}?start=ref_{referral_code}"

	msg = (
		f"🔗 <b>Your Referral Link</b>\n\n"
		f"<code>{referral_url or 'Bot username not set'}</code>\n\n"
		f"📊 Referrals: <b>{referred_count}</b>\n"
		f"🎁 Bonus earned: <b>+{bonus_earned_days} days</b> subscription\n"
		f"📈 Progress: <b>{toward_next}/3</b>"
		f"{' (invite ' + str(needed_for_next) + ' more)' if needed_for_next else ' (reward unlocked on your latest milestone)'}\n\n"
		f"💡 Earn <b>+{bonus_days} free days</b> for every 3 valid referrals.\n"
		f"Share your link and grow your streak!"
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
	await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)


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

		since = datetime.utcnow()
		# Use last 7 days
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
			JOIN outcomes o ON o.signal_id = sd.signal_id
			WHERE o.closed_at >= NOW() - INTERVAL '7 days'
			GROUP BY u.id, u.username, u.tier
			HAVING COUNT(o.id) >= 2
			ORDER BY avg_r DESC NULLS LAST, wins DESC
			LIMIT 15
		""")

		async with get_session() as session:
			rows = (await session.execute(query)).fetchall()
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
		await update.message.reply_text(msg, reply_markup=keyboard, parse_mode="MarkdownV2")

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
