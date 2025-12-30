import os
OWNER_IDS = {int(os.getenv("OWNER_TELEGRAM_ID", "0"))}
PAYMENTS_ENABLED = os.getenv("PAYMENTS_ENABLED", "true").lower() == "true"
