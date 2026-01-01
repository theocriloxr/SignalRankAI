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


def _env_int_set(name: str) -> set[int]:
	raw = (os.getenv(name) or "").strip()
	if not raw:
		return set()
	out: set[int] = set()
	for part in raw.split(","):
		p = part.strip()
		if not p:
			continue
		try:
			out.add(int(p))
		except Exception:
			continue
	return out


_single = _env_int("OWNER_TELEGRAM_ID", 0)
OWNER_IDS = set()
if _single:
	OWNER_IDS.add(_single)
OWNER_IDS |= _env_int_set("OWNER_TELEGRAM_IDS")
PAYMENTS_ENABLED = os.getenv("PAYMENTS_ENABLED", "true").lower() == "true"
