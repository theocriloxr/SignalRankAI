
import os

class Config:
	"""
	Centralized configuration, secrets, and feature toggles for SignalRankAI.

	All environment variables and feature toggles are loaded once at startup.
	Access all config via the global `config` instance.

	Example usage:
		from config import config
		db_url = config.DATABASE_URL

	Environment variable mapping:
		DATABASE_URL, REDIS_URL, TELEGRAM_BOT_TOKEN, OWNER_TELEGRAM_ID, OWNER_TELEGRAM_IDS,
		PAYMENTS_ENABLED, PAYSTACK_SECRET_KEY, ALPHAVANTAGE_API_KEY, BINANCE_API_KEY, BINANCE_API_SECRET,
		FX_PAIRS, FX_MAX_PAIRS_PER_CYCLE, DRY_RUN, MIN_TRADE_SIZE, MAX_ACTIVE_TRADES, RISK_PER_TRADE_PCT,
		RAILWAY_SERVICE_NAME, RAILWAY_ENVIRONMENT, RAILWAY_DEPLOYMENT_ID, GIT_COMMIT_SHA, etc.
	"""
	def __init__(self):
		# Database and cache
		self.DATABASE_URL = os.getenv("DATABASE_URL", "")
		self.REDIS_URL = os.getenv("REDIS_URL", "")

		# Telegram bot and owner(s)
		self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
		self.OWNER_TELEGRAM_ID = self._env_int("TELEGRAM_OWNER_ID", 0)
		if not self.OWNER_TELEGRAM_ID:
			self.OWNER_TELEGRAM_ID = self._env_int("OWNER_TELEGRAM_ID", 0)
		self.OWNER_TELEGRAM_IDS = self._env_int_set("OWNER_TELEGRAM_IDS")
		self.OWNER_IDS = self._env_int_set("OWNER_IDS")
		self.owner_ids: set[int] = set()
		if self.OWNER_TELEGRAM_ID:
			self.owner_ids.add(self.OWNER_TELEGRAM_ID)
		self.owner_ids |= self.OWNER_TELEGRAM_IDS
		self.owner_ids |= self.OWNER_IDS

		# Admin IDs — separate from owner; set via ADMIN_IDS (CSV) or ADMIN_ID (single)
		# These users get admin-tier access without being full owners.
		self.ADMIN_IDS: set[int] = self._env_int_set("ADMIN_IDS")
		_single_admin = self._env_int("ADMIN_ID", 0)
		if _single_admin:
			self.ADMIN_IDS.add(_single_admin)

		# Payments and API keys
		self.PAYMENTS_ENABLED = os.getenv("PAYMENTS_ENABLED", "true").lower() == "true"
		self.PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
		self.PAYSTACK_WEBHOOK_SECRET = os.getenv("PAYSTACK_WEBHOOK_SECRET", "")
		self.ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
		self.BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
		self.BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

		# Trading and risk management
		self.FX_PAIRS = [p.strip() for p in os.getenv("FX_PAIRS", "").split(",") if p.strip()]
		self.FX_MAX_PAIRS_PER_CYCLE = self._env_int("FX_MAX_PAIRS_PER_CYCLE", 3)
		self.DRY_RUN = self._env_bool("DRY_RUN", False)
		self.MIN_TRADE_SIZE = self._env_float("MIN_TRADE_SIZE", 0.001)
		self.MAX_ACTIVE_TRADES = self._env_int("MAX_ACTIVE_TRADES", 5)
		self.RISK_PER_TRADE_PCT = self._env_float("RISK_PER_TRADE_PCT", 1.0)

		# Railway/infra metadata
		self.RAILWAY_SERVICE_NAME = os.getenv("RAILWAY_SERVICE_NAME", "")
		self.RAILWAY_ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", "")
		self.RAILWAY_DEPLOYMENT_ID = os.getenv("RAILWAY_DEPLOYMENT_ID", "")
		self.GIT_COMMIT_SHA = os.getenv("RAILWAY_GIT_COMMIT_SHA", "")

		# Feature toggles (add more as needed)
		self.MARKET_MONITOR_ENABLED = self._env_bool("MARKET_MONITOR_ENABLED", True)
		self.CRYPTO_WS_ENABLED = self._env_bool("CRYPTO_WS_ENABLED", False)
		self.ML_TRAIN_ENABLED = self._env_bool("ML_TRAIN_ENABLED", True)
		self.ML_TRAIN_INTERVAL_SECONDS = self._env_int("ML_TRAIN_INTERVAL_SECONDS", 86400)

	def _env_int(self, name: str, default: int = 0) -> int:
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

	def _env_int_set(self, name: str) -> set[int]:
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

	def _env_bool(self, name: str, default: bool = False) -> bool:
		val = os.getenv(name)
		if val is None:
			return default
		return val.strip().lower() in {"1", "true", "yes", "y", "on"}

	def _env_float(self, name: str, default: float = 0.0) -> float:
		raw = os.getenv(name)
		if raw is None:
			return default
		try:
			return float(raw.strip())
		except Exception:
			return default


# Global config instance
config = Config()
# Backwards-compatible top-level exports for modules that import names directly from `config`
from typing import Set


OWNER_IDS: Set[int] = config.owner_ids
OWNER_TELEGRAM_ID = config.OWNER_TELEGRAM_ID
OWNER_TELEGRAM_IDS = config.OWNER_TELEGRAM_IDS
ADMIN_IDS: Set[int] = config.ADMIN_IDS
TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
DATABASE_URL = config.DATABASE_URL
REDIS_URL = config.REDIS_URL
