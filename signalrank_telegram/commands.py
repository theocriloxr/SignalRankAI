
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

# /performance command for Premium+
@require_tier("PREMIUM")
def performance_command(update, context):
	# Example: aggregate stats for last 30 days
	win_rate, avg_rr = strategy_stats("ALL")
	signals_count = 112  # Replace with real count
	msg = f"Last 30 days:\n✔ Win rate: {round(win_rate*100,1)}%\n✔ Avg RR: {round(avg_rr,2)}\n✔ Signals: {signals_count}"
	update.message.reply_text(msg)
