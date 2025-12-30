MAX_DAILY_LOSS = 0.05
MAX_MONTHLY_DRAWDOWN = 0.20
SYSTEM_ACTIVE = True

# Placeholder functions for loss/drawdown

def daily_loss():
    return 0.0

def monthly_drawdown():
    return 0.0

def halt_system(reason):
    global SYSTEM_ACTIVE
    SYSTEM_ACTIVE = False
    notify_owner(f"🚨 System halted: {reason}")

def notify_owner(msg):
    # Implement Telegram notification to OWNER
    pass

def evaluate_system_health():
    if daily_loss() > MAX_DAILY_LOSS:
        halt_system("Daily loss exceeded")
    if monthly_drawdown() > MAX_MONTHLY_DRAWDOWN:
        halt_system("Monthly drawdown exceeded")
