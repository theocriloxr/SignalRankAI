
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
		self.DATABASE_URL = self._first_env("DATABASE_PUBLIC_URL", "DATABASE_URL")
		self.REDIS_URL = self._first_env(
			"REDIS_URL",
			"REDIS_PRIVATE_URL",
			"REDIS_PUBLIC_URL",
			"REDIS_INTERNAL_URL",
			"REDIS_TLS_URL",
		)

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
		self.BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
		self.BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
		self.BYBIT_TESTNET = self._env_bool("BYBIT_TESTNET", False)

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
		self.MARKET_MONITOR_ENABLED = True
		self.CRYPTO_WS_ENABLED = True
		self.ML_TRAIN_ENABLED = True
		self.ML_TRAIN_INTERVAL_SECONDS = self._env_int("ML_TRAIN_INTERVAL_SECONDS", 86400)

		# Exchange scope (native execution and market connectors)
		self.EXECUTION_EXCHANGES = ["binance", "bybit"]
		self.CRYPTO_DATA_EXCHANGES = ["binance", "bybit"]

		# Smart DCA profiles
		self.DCA_PROFILE_DEFAULT = os.getenv("DCA_PROFILE_DEFAULT", "conservative_swing").strip().lower() or "conservative_swing"
		self.DCA_CONSERVATIVE_BASE_ORDER_USD = self._env_float("DCA_CONSERVATIVE_BASE_ORDER_USD", 100.0)
		self.DCA_CONSERVATIVE_MAX_LEGS = self._env_int("DCA_CONSERVATIVE_MAX_LEGS", 4)
		self.DCA_CONSERVATIVE_INITIAL_SPACING_PCT = self._env_float("DCA_CONSERVATIVE_INITIAL_SPACING_PCT", 2.0)
		self.DCA_CONSERVATIVE_VOLUME_SCALE = self._env_float("DCA_CONSERVATIVE_VOLUME_SCALE", 1.5)
		self.DCA_CONSERVATIVE_STEP_SCALE = self._env_float("DCA_CONSERVATIVE_STEP_SCALE", 1.2)

		self.DCA_AGGRESSIVE_BASE_ORDER_USD = self._env_float("DCA_AGGRESSIVE_BASE_ORDER_USD", 50.0)
		self.DCA_AGGRESSIVE_MAX_LEGS = self._env_int("DCA_AGGRESSIVE_MAX_LEGS", 6)
		self.DCA_AGGRESSIVE_INITIAL_SPACING_PCT = self._env_float("DCA_AGGRESSIVE_INITIAL_SPACING_PCT", 1.5)
		self.DCA_AGGRESSIVE_VOLUME_SCALE = self._env_float("DCA_AGGRESSIVE_VOLUME_SCALE", 2.0)
		self.DCA_AGGRESSIVE_STEP_SCALE = self._env_float("DCA_AGGRESSIVE_STEP_SCALE", 1.5)

		# ML-adaptive DCA spacing
		self.DCA_ML_ADAPTIVE_ENABLED = self._env_bool("DCA_ML_ADAPTIVE_ENABLED", True)
		self.DCA_LOW_VOL_INITIAL_SPACING_PCT = self._env_float("DCA_LOW_VOL_INITIAL_SPACING_PCT", 1.0)
		self.DCA_LOW_VOL_MAX_LEGS = self._env_int("DCA_LOW_VOL_MAX_LEGS", 3)
		self.DCA_HIGH_VOL_INITIAL_SPACING_PCT = self._env_float("DCA_HIGH_VOL_INITIAL_SPACING_PCT", 3.5)
		self.DCA_HIGH_VOL_STEP_SCALE = self._env_float("DCA_HIGH_VOL_STEP_SCALE", 1.4)

		# Trailing behaviour
		self.TRAILING_ACTIVATION_MODE = os.getenv("TRAILING_ACTIVATION_MODE", "on_favorable_move").strip().lower() or "on_favorable_move"

		# Simulation and user experience defaults
		self.PAPER_TRADING_SIMULATE_ALL = self._env_bool("PAPER_TRADING_SIMULATE_ALL", True)
		self.PAPER_TRADING_SIMULATE_FEES = self._env_bool("PAPER_TRADING_SIMULATE_FEES", True)
		self.PAPER_TRADING_SIMULATE_SLIPPAGE = self._env_bool("PAPER_TRADING_SIMULATE_SLIPPAGE", True)
		self.PAPER_TRADING_START_BALANCE_USD = self._env_float("PAPER_TRADING_START_BALANCE_USD", 1000.0)
		self.CHART_STYLE_DEFAULT = os.getenv("CHART_STYLE_DEFAULT", "tradingview").strip().lower() or "tradingview"
		self.POSITION_RISK_DEFAULT_PCT = self._env_float("POSITION_RISK_DEFAULT_PCT", 1.0)
		self.POSITION_RISK_USER_SELECTABLE = self._env_bool("POSITION_RISK_USER_SELECTABLE", True)

		# Data ingestion choices
		self.SENTIMENT_ROLLOUT_PHASE = os.getenv("SENTIMENT_ROLLOUT_PHASE", "rss_fear_greed_first").strip().lower() or "rss_fear_greed_first"
		self.ONCHAIN_ALERT_INCLUDE_EXCHANGE_FLOWS = self._env_bool("ONCHAIN_ALERT_INCLUDE_EXCHANGE_FLOWS", True)
		self.ONCHAIN_ALERT_INCLUDE_DORMANT_MOVES = self._env_bool("ONCHAIN_ALERT_INCLUDE_DORMANT_MOVES", True)

		# AI journal and correlation governance
		self.AI_JOURNAL_AUTO_SEND = self._env_bool("AI_JOURNAL_AUTO_SEND", True)
		self.AI_JOURNAL_WEEKLY_DAY = os.getenv("AI_JOURNAL_WEEKLY_DAY", "sunday").strip().lower() or "sunday"
		self.CORRELATION_FILTER_MODE = os.getenv("CORRELATION_FILTER_MODE", "best_per_cluster").strip().lower() or "best_per_cluster"

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

	def _first_env(self, *names: str) -> str:
		for name in names:
			raw = os.getenv(str(name), "")
			if raw and raw.strip():
				return raw.strip()
		return ""

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

	def _env_csv(self, name: str, default: list[str] | None = None) -> list[str]:
		raw = (os.getenv(name) or "").strip()
		if not raw:
			return [str(v).strip().lower() for v in (default or []) if str(v).strip()]
		return [p.strip().lower() for p in raw.split(",") if p.strip()]

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
