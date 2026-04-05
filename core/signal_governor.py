from core.tier_constants import TIER_DAILY_LIMITS


MAX_SIGNALS_PER_DAY = {
    "PREMIUM": TIER_DAILY_LIMITS.get("premium", float("inf")),
    "VIP": TIER_DAILY_LIMITS.get("vip", float("inf")),
}

signals_sent_today = {"PREMIUM": 0, "VIP": 0}

def can_send_signal(tier):
    if tier not in MAX_SIGNALS_PER_DAY:
        return True
    return signals_sent_today[tier] < MAX_SIGNALS_PER_DAY[tier]

def record_signal_sent(tier):
    if tier in signals_sent_today:
        signals_sent_today[tier] += 1
