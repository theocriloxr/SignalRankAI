
import os

class Config:
		self.MARKET_MONITOR_ENABLED = self._env_bool("MARKET_MONITOR_ENABLED", True)
		self.CRYPTO_WS_ENABLED = self._env_bool("CRYPTO_WS_ENABLED", False)
		self.ML_TRAIN_ENABLED = self._env_bool("ML_TRAIN_ENABLED", True)
		self.ML_TRAIN_INTERVAL_SECONDS = self._env_int("ML_TRAIN_INTERVAL_SECONDS", 86400)
	"""Centralized configuration, secrets, and feature toggles."""
	def __init__(self):
		self.DATABASE_URL = os.getenv("DATABASE_URL", "")
		self.REDIS_URL = os.getenv("REDIS_URL", "")
		self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
		self.OWNER_TELEGRAM_ID = self._env_int("TELEGRAM_OWNER_ID", 0)
		self.OWNER_TELEGRAM_IDS = self._env_int_set("OWNER_TELEGRAM_IDS")
		self.OWNER_IDS = set()
		if self.OWNER_TELEGRAM_ID:
			self.OWNER_IDS.add(self.OWNER_TELEGRAM_ID)
		self.OWNER_IDS |= self.OWNER_TELEGRAM_IDS
		self.PAYMENTS_ENABLED = os.getenv("PAYMENTS_ENABLED", "true").lower() == "true"
		self.PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
		self.ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
		self.BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
		self.BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
		self.FX_PAIRS = [p.strip() for p in os.getenv("FX_PAIRS", "").split(",") if p.strip()]
		self.FX_MAX_PAIRS_PER_CYCLE = self._env_int("FX_MAX_PAIRS_PER_CYCLE", 3)
		self.DRY_RUN = self._env_bool("DRY_RUN", False)
		self.MIN_TRADE_SIZE = self._env_float("MIN_TRADE_SIZE", 0.001)
		self.MAX_ACTIVE_TRADES = self._env_int("MAX_ACTIVE_TRADES", 5)
		self.RISK_PER_TRADE_PCT = self._env_float("RISK_PER_TRADE_PCT", 1.0)
		self.RAILWAY_SERVICE_NAME = os.getenv("RAILWAY_SERVICE_NAME", "")
		self.RAILWAY_ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", "")
		self.RAILWAY_DEPLOYMENT_ID = os.getenv("RAILWAY_DEPLOYMENT_ID", "")
		self.GIT_COMMIT_SHA = os.getenv("RAILWAY_GIT_COMMIT_SHA", "")

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
