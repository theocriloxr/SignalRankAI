# /pricing command
def pricing_command(update, context):
	msg = (
		"\U0001F4B3 SignalRankAI Pricing\n\n"
		"🆓 Free – ₦0\n"
		"• Delayed daily summaries\n"
		"• Example signals for learning\n\n"
		"⭐ Premium\n"
		"₦2,000 / week\n"
		"₦6,000 / month\n"
		"• Real-time ranked trade signals\n"
		"• Clear entries, stops, and targets\n\n"
		"🚀 VIP\n"
		"₦5,000 / week\n"
		"₦18,000 / month\n"
		"• Early access to signals\n"
		"• AI confidence display\n"
		"• High-quality filtering\n\n"
		"━━━━━━━━━━━━━━\n\n"
		"\U0001F4B8 Need more signals as a Free user?\n"
		"• Buy extra Premium signal: ₦300 each (/buy_extra_premium <count>)\n"
		"• Buy extra VIP signal: ₦500 each (/buy_extra_vip <count>)\n\n"
		"All subscriptions activate automatically after payment\n"
		"and expire at the end of the selected period.\n\n"
		"Use /faq to learn more."
	)
	update.message.reply_text(msg)
# --- Extra Signal Purchase Logic ---
from telegram import Update
from db.database import get_user_tier

def buy_extra_premium(update, context):
	user_id = update.effective_user.id
	tier = get_user_tier(user_id)
	if tier != "FREE":
		update.message.reply_text("Extra Premium signals are only for Free users. Upgrade for unlimited access.")
		return
	if not context.args or len(context.args) != 1:
		update.message.reply_text("Usage: /buy_extra_premium <count>\nExample: /buy_extra_premium 2")
		return
	try:
		count = int(context.args[0])
		if count < 1:
			update.message.reply_text("Count must be at least 1.")
			return
	except ValueError:
		update.message.reply_text("Count must be a number.")
		return
	price = 300 * count
	from paystack.paystack import generate_paystack_link
	paywall_link = generate_paystack_link(user_id, price, tier="PREMIUM", extra_count=count)
	update.message.reply_text(
		f"To unlock {count} extra Premium signals for today, pay ₦{price}: {paywall_link}\n"
		"You will receive real-time Premium signals after payment."
	)

def buy_extra_vip(update, context):
	user_id = update.effective_user.id
	tier = get_user_tier(user_id)
	if tier != "FREE":
		update.message.reply_text("Extra VIP signals are only for Free users. Upgrade for unlimited access.")
		return
	if not context.args or len(context.args) != 1:
		update.message.reply_text("Usage: /buy_extra_vip <count>\nExample: /buy_extra_vip 1")
		return
	try:
		count = int(context.args[0])
		if count < 1:
			update.message.reply_text("Count must be at least 1.")
			return
	except ValueError:
		update.message.reply_text("Count must be a number.")
		return
	price = 500 * count
	from paystack.paystack import generate_paystack_link
	paywall_link = generate_paystack_link(user_id, price, tier="VIP", extra_count=count)
	update.message.reply_text(
		f"To unlock {count} extra VIP signals for today, pay ₦{price}: {paywall_link}\n"
		"You will receive real-time VIP signals after payment."
	)

# /policy or /refunds command
def policy_command(update, context):
	msg = (
		"\U0001F4DC Subscription & Refund Policy\n\n"
		"• All payments to SignalRankAI are final.\n"
		"• We do not offer refunds under any circumstances.\n"
		"• Payments sent with incorrect amounts or incorrect details are non-refundable.\n"
		"• It is the user’s responsibility to confirm payment details before completing a transaction.\n\n"
		"Subscriptions activate automatically after successful payment verification and expire at the end of the purchased period.\n\n"
		"By subscribing, you acknowledge and agree to this policy."
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

from telegram.access import resolve_user_tier

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
			tier = resolve_user_tier(user_id)
			if rate_limited(user_id):
				update.message.reply_text("Rate limit exceeded. Please wait.")
				return
			if tier_rank(tier) < tier_rank(min_tier):
				update.message.reply_text("Upgrade required.")
				return
			return func(update, context)
		return inner
	return wrapper


# /start or welcome message
def start_command(update, context):
	msg = (
		"SignalRankAI is a trading signal bot that helps you spot high-quality trade opportunities.\n\n"
		"It analyzes the market using multiple strategies, filters out risky setups, and delivers only the strongest signals — directly on Telegram.\n\n"
		"No hype. No guarantees. Just structured, risk-aware signals."
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
