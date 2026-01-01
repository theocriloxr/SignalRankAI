import os


def _env_int(name: str, default: int = 0) -> int:
	raw = os.getenv(name)
	if raw is None:
		return default
	raw = raw.strip()
	if not raw:
		return default
	try:
		return int(raw)
	except Exception:
		return default


OWNER_IDS = {_env_int("OWNER_TELEGRAM_ID", 0)}
PAYMENTS_ENABLED = os.getenv("PAYMENTS_ENABLED", "true").lower() == "true"
