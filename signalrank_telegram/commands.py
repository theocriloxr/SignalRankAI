# /pricing command
import os

from telegram import Update
from telegram.ext import CallbackContext

from core.redis_state import state
from .access import resolve_user_tier

def pricing_command(update: Update, context: CallbackContext):
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
		"• Highest confidence signals only (score ≥ 85)\n"
		"• Reduced frequency (quality > quantity)\n"
		"• Early alerts + priority notifications\n"
		"• Monthly performance report\n\n"
		"📌 No hype. Transparent tracking.\n"
		"Use /upgrade to subscribe.\n\n"
		"⚠️ Disclaimer: Educational only. Not financial advice. Trading involves risk."
	)
	update.message.reply_text(msg)


def upgrade_command(update: Update, context: CallbackContext):
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
	links.append(
		("VIP (₦20,000 / 30 days)", generate_paystack_link(user_id, 20000, tier="vip", duration_days=30, plan_code=vip_monthly_code))
	)

	msg = "📌 Choose a plan:\n\n" + "\n".join([f"• {label}: {url}" for (label, url) in links])
	msg += "\n\nPayments are processed by Paystack. No access to your funds."
	msg += "\n⚠️ Educational only. Not financial advice."
	update.message.reply_text(msg)
# --- Extra Signal Purchase Logic ---
from telegram import Update
from db.database import get_user_tier

def buy_extra_premium(update, context):
	user_id = update.effective_user.id
	tier = get_user_tier(user_id)
	if tier != "FREE":
		update.message.reply_text(
			"Extra Premium signals are only available for Free users.\n"
			"Upgrade to Premium or VIP for unlimited real-time access."
		)
		return
	if not context.args or len(context.args) != 1:
		update.message.reply_text(
			"Usage: /buy_extra_premium <count>\n"
			"Example: /buy_extra_premium 2\n\n"
			"You can buy up to 5 extra signals per day."
		)
		return
	try:
		count = int(context.args[0])
		if count < 1 or count > 5:
			update.message.reply_text("Count must be between 1 and 5.")
			return
	except ValueError:
		update.message.reply_text("Count must be a number.")
		return
	price = 300 * count
	from paystack.paystack import generate_paystack_link
	paywall_link = generate_paystack_link(user_id, price, tier="PREMIUM", extra_count=count)
	update.message.reply_text(
		f"To unlock {count} extra Premium signals for today, pay ₦{price}: {paywall_link}\n\n"
		"After payment, your extra signals will be delivered instantly.\n"
		"All payments are final and non-refundable.\n\n"
		"For questions, use /faq or contact support."
	)

def buy_extra_vip(update, context):
	user_id = update.effective_user.id
	tier = get_user_tier(user_id)
	if tier != "FREE":
		update.message.reply_text(
			"Extra VIP signals are only available for Free users.\n"
			"Upgrade to VIP for unlimited real-time access."
		)
		return
	if not context.args or len(context.args) != 1:
		update.message.reply_text(
			"Usage: /buy_extra_vip <count>\n"
			"Example: /buy_extra_vip 1\n\n"
			"You can buy up to 3 extra VIP signals per day."
		)
		return
	try:
		count = int(context.args[0])
		if count < 1 or count > 3:
			update.message.reply_text("Count must be between 1 and 3.")
			return
	except ValueError:
		update.message.reply_text("Count must be a number.")
		return
	price = 500 * count
	from paystack.paystack import generate_paystack_link
	paywall_link = generate_paystack_link(user_id, price, tier="VIP", extra_count=count)
	update.message.reply_text(
		f"To unlock {count} extra VIP signals for today, pay ₦{price}: {paywall_link}\n\n"
		"After payment, your extra signals will be delivered instantly.\n"
		"All payments are final and non-refundable.\n\n"
		"For questions, use /faq or contact support."
	)

# /policy or /refunds command
def policy_command(update, context):
    msg = (
		"📄 Subscription & Refund Policy\n\n"
		"• Due to the digital and time-sensitive nature of the service, payments are non-refundable.\n"
		"• If technical issues prevent delivery, subscription time may be extended.\n\n"
		"Subscriptions activate after successful verification and expire at the end of the purchased period.\n\n"
		"⚠️ Disclaimer: Educational only. Not financial advice. Trading involves risk."
	)
    update.message.reply_text(msg)

# /recap command (weekly recap)
def recap_command(update, context):
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
	update.message.reply_text(recap_msg)


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
		def inner(update, context):
			user_id = update.effective_user.id
			# Global kill-switch
			try:
				ks = state.get_killswitch_sync()
			except Exception:
				ks = type("KS", (), {"enabled": False})()
			if getattr(ks, "enabled", False):
				update.message.reply_text("🚨 Signals are temporarily paused.")
				return

			# Rate limit (20/min)
			try:
				limited = state.rate_limited_sync(user_id, limit=20, window_seconds=60)
			except Exception:
				limited = False
			if limited:
				update.message.reply_text("Rate limit exceeded. Please wait.")
				return
			tier = resolve_user_tier(user_id)
			try:
				if state.has_temp_owner_sync(user_id):
					tier = "OWNER"
			except Exception:
				pass
			if tier_rank(tier) < tier_rank(min_tier):
				update.message.reply_text("Upgrade required.")
				return
			return func(update, context)
		return inner
	return wrapper


# /start or welcome message
def start_command(update, context):
	msg = (
		"SignalRankAI provides algorithmic market analysis for educational purposes only. "
		"This is not financial advice. Trading involves risk.\n\n"
		"What you get:\n"
		"• Risk-managed signals filtered for high-probability setups\n"
		"• Outcome tracking (no hype, no guarantees)\n\n"
		"Use /pricing to see plans, or /upgrade to subscribe."
	)
	update.message.reply_text(msg)

# /about message
def about_command(update, context):
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
	update.message.reply_text(msg)

# /faq message
def faq_command(update, context):
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
	update.message.reply_text(msg)

# /disclaimer message
def disclaimer_command(update, context):
	msg = (
		"\u26A0\uFE0F Disclaimer\n\n"
		"SignalRankAI provides trading signals for informational and educational purposes only.\n\n"
		"Nothing provided by this bot constitutes financial advice, investment advice, or a recommendation to buy or sell any asset.\n\n"
		"Trading involves risk, and you are fully responsible for your trading decisions.\n"
		"Past performance does not guarantee future results.\n\n"
		"By using SignalRankAI, you acknowledge and accept these risks."
	)
	update.message.reply_text(msg)

# /performance command for Premium+
@require_tier("PREMIUM")
def performance_command(update, context):
	from db.database import fetch_user_trades
	from datetime import datetime, timedelta
	user_id = update.effective_user.id
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
	else:
		# Win rate: count TP outcomes
		win_count = sum(1 for t in trades_30d if (len(t) > 15 and t[15] == 'TP'))
		win_rate = win_count / total if total > 0 else 0
		rr_ratios = [t[7] for t in trades_30d if t[7] is not None]
		avg_rr = round(sum(rr_ratios)/len(rr_ratios), 2) if rr_ratios else 'N/A'
		msg = f"Last 30 days:\n✔ Win rate: {round(win_rate*100,1)}%\n✔ Avg RR: {avg_rr}\n✔ Signals: {total}"
	update.message.reply_text(msg)
