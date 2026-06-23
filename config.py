import os
from typing import Optional, Set
from urllib.parse import quote_plus


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

    def __init__(self) -> None:
        # Database and cache
        self.DATABASE_URL: str = self._first_env(
            "DATABASE_URL",
            "DATABASE_PRIVATE_URL",
            "DATABASE_PUBLIC_URL",
        )
        self.REDIS_URL: str = self._first_env(
            "REDIS_URL",
            "REDIS_PRIVATE_URL",
            "REDIS_PUBLIC_URL",
            "REDIS_INTERNAL_URL",
            "REDIS_TLS_URL",
        )

        # Telegram bot and owner(s)
        self.TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        owner_telegram_id: int = self._env_int("TELEGRAM_OWNER_ID", 0)
        if not owner_telegram_id:
            owner_telegram_id = self._env_int("OWNER_TELEGRAM_ID", 0)
        self.OWNER_TELEGRAM_ID: int = owner_telegram_id
        self.OWNER_TELEGRAM_IDS: set[int] = self._env_int_set("OWNER_TELEGRAM_IDS")
        self.OWNER_IDS: set[int] = self._env_int_set("OWNER_IDS")

        # Backward-compatible owner union behavior:
        # owner_ids now includes OWNER_IDS + OWNER_TELEGRAM_ID + OWNER_TELEGRAM_IDS.
        self.owner_ids: set[int] = set()
        self.owner_ids |= self.OWNER_IDS
        if self.OWNER_TELEGRAM_ID:
            self.owner_ids.add(self.OWNER_TELEGRAM_ID)
        self.owner_ids |= self.OWNER_TELEGRAM_IDS

        # Admin IDs — separate from owner; set via ADMIN_IDS (CSV) or ADMIN_ID (single)
        # These users get admin-tier access without being full owners.
        self.ADMIN_IDS: set[int] = self._env_int_set("ADMIN_IDS")
        _single_admin: int = self._env_int("ADMIN_ID", 0)
        if _single_admin:
            self.ADMIN_IDS.add(_single_admin)

        # Payments and API keys
        self.PAYMENTS_ENABLED: bool = os.getenv("PAYMENTS_ENABLED", "true").lower() == "true"
        self.PAYSTACK_SECRET_KEY: str = os.getenv("PAYSTACK_SECRET_KEY", "")
        self.PAYSTACK_WEBHOOK_SECRET: str = os.getenv("PAYSTACK_WEBHOOK_SECRET", "")
        self.ALPHAVANTAGE_API_KEY: str = os.getenv("ALPHAVANTAGE_API_KEY", "")
        self.BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
        self.BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
        self.BYBIT_API_KEY: str = os.getenv("BYBIT_API_KEY", "")
        self.BYBIT_API_SECRET: str = os.getenv("BYBIT_API_SECRET", "")
        self.BYBIT_TESTNET: bool = self._env_bool("BYBIT_TESTNET", False)

        # Multi-asset provider API keys
        self.POLYGON_API_KEY: str = os.getenv("POLYGON_API_KEY", "")
        self.TWELVEDATA_API_KEY: str = os.getenv("TWELVEDATA_API_KEY", "")
        self.OANDA_API_KEY: str = os.getenv("OANDA_API_KEY", "")
        self.OANDA_ACCOUNT_ID: str = os.getenv("OANDA_ACCOUNT_ID", "")

        # CryptoCompare API key - Required for Nigeria deployment (Binance geo-blocked)
        # Get free key from https://www.cryptocompare.com/cryptoapi/
        self.CRYPTOCOMPARE_API_KEY: str = os.getenv("CRYPTOCOMPARE_API_KEY", "").strip()

        # TradingView webhook security
        self.TV_WEBHOOK_SECRET: str = os.getenv("TV_WEBHOOK_SECRET", "")

        # Trading and risk management
        self.FX_PAIRS: list[str] = [p.strip() for p in os.getenv("FX_PAIRS", "").split(",") if p.strip()]
        self.FX_MAX_PAIRS_PER_CYCLE: int = self._env_int("FX_MAX_PAIRS_PER_CYCLE", 3)
        self.DRY_RUN: bool = self._env_bool("DRY_RUN", False)
        self.MIN_TRADE_SIZE: float = self._env_float("MIN_TRADE_SIZE", 0.001)
        self.MAX_ACTIVE_TRADES: int = self._env_int("MAX_ACTIVE_TRADES", 5)
        self.RISK_PER_TRADE_PCT: float = self._env_float("RISK_PER_TRADE_PCT", 1.0)

        # Railway/infra metadata
        self.RAILWAY_SERVICE_NAME: str = os.getenv("RAILWAY_SERVICE_NAME", "")
        self.RAILWAY_ENVIRONMENT: str = os.getenv("RAILWAY_ENVIRONMENT", "")
        self.RAILWAY_DEPLOYMENT_ID: str = os.getenv("RAILWAY_DEPLOYMENT_ID", "")
        self.GIT_COMMIT_SHA: str = os.getenv("RAILWAY_GIT_COMMIT_SHA", "")

        # Feature toggles (add more as needed)
        self.MARKET_MONITOR_ENABLED: bool = True
        self.CRYPTO_WS_ENABLED: bool = True

        # Asset class enablement toggles - Enable/disable asset classes globally
        # Set to 'true' or 'false' via environment variables
        self.FX_ENABLED: bool = self._env_bool("FX_ENABLED", True)
        self.STOCKS_ENABLED: bool = self._env_bool("STOCKS_ENABLED", True)
        self.CRYPTO_ENABLED: bool = self._env_bool("CRYPTO_ENABLED", True)
        self.COMMODITY_ENABLED: bool = self._env_bool("COMMODITY_ENABLED", True)

        # Disable ML training on Railway Hobby tier to avoid DB connection exhaustion
        is_railway: bool = bool(self.RAILWAY_SERVICE_NAME or self.RAILWAY_ENVIRONMENT)
        ml_train_default: bool = not is_railway  # Default False on Railway (Hobby plan constraint)
        self.ML_TRAIN_ENABLED: bool = self._env_bool("ML_TRAIN_ENABLED", ml_train_default)
        self.ML_TRAIN_INTERVAL_SECONDS: int = self._env_int("ML_TRAIN_INTERVAL_SECONDS", 86400)

        # ML probability threshold
        self.ML_PROB_THRESHOLD: float = self._env_float("ML_PROB_THRESHOLD", 0.15)

        # Score threshold for signal storage
        self.PREMIUM_SCORE_THRESHOLD: float = self._env_float("PREMIUM_SCORE_THRESHOLD", 25.0)

        # MARKET DATA: Minimum candles required
        self.MARKET_CACHE_MIN_CANDLES: int = self._env_int("MARKET_CACHE_MIN_CANDLES", 20)

        # Exchange scope (native execution and market connectors)
        self.EXECUTION_EXCHANGES: list[str] = ["binance", "bybit"]
        self.CRYPTO_DATA_EXCHANGES: list[str] = ["binance", "bybit"]

        # Smart DCA profiles
        self.DCA_PROFILE_DEFAULT: str = (
            os.getenv("DCA_PROFILE_DEFAULT", "conservative_swing").strip().lower() or "conservative_swing"
        )
        self.DCA_CONSERVATIVE_BASE_ORDER_USD: float = self._env_float("DCA_CONSERVATIVE_BASE_ORDER_USD", 100.0)
        self.DCA_CONSERVATIVE_MAX_LEGS: int = self._env_int("DCA_CONSERVATIVE_MAX_LEGS", 4)
        self.DCA_CONSERVATIVE_INITIAL_SPACING_PCT: float = self._env_float(
            "DCA_CONSERVATIVE_INITIAL_SPACING_PCT", 2.0
        )
        self.DCA_CONSERVATIVE_VOLUME_SCALE: float = self._env_float("DCA_CONSERVATIVE_VOLUME_SCALE", 1.5)
        self.DCA_CONSERVATIVE_STEP_SCALE: float = self._env_float("DCA_CONSERVATIVE_STEP_SCALE", 1.2)

        self.DCA_AGGRESSIVE_BASE_ORDER_USD: float = self._env_float("DCA_AGGRESSIVE_BASE_ORDER_USD", 50.0)
        self.DCA_AGGRESSIVE_MAX_LEGS: int = self._env_int("DCA_AGGRESSIVE_MAX_LEGS", 6)
        self.DCA_AGGRESSIVE_INITIAL_SPACING_PCT: float = self._env_float("DCA_AGGRESSIVE_INITIAL_SPACING_PCT", 1.5)
        self.DCA_AGGRESSIVE_VOLUME_SCALE: float = self._env_float("DCA_AGGRESSIVE_VOLUME_SCALE", 2.0)
        self.DCA_AGGRESSIVE_STEP_SCALE: float = self._env_float("DCA_AGGRESSIVE_STEP_SCALE", 1.5)

        # ML-adaptive DCA spacing
        self.DCA_ML_ADAPTIVE_ENABLED: bool = self._env_bool("DCA_ML_ADAPTIVE_ENABLED", True)
        self.DCA_LOW_VOL_INITIAL_SPACING_PCT: float = self._env_float("DCA_LOW_VOL_INITIAL_SPACING_PCT", 1.0)
        self.DCA_LOW_VOL_MAX_LEGS: int = self._env_int("DCA_LOW_VOL_MAX_LEGS", 3)
        self.DCA_HIGH_VOL_INITIAL_SPACING_PCT: float = self._env_float("DCA_HIGH_VOL_INITIAL_SPACING_PCT", 3.5)
        self.DCA_HIGH_VOL_STEP_SCALE: float = self._env_float("DCA_HIGH_VOL_STEP_SCALE", 1.4)

        # Trailing behaviour
        self.TRAILING_ACTIVATION_MODE: str = (
            os.getenv("TRAILING_ACTIVATION_MODE", "on_favorable_move").strip().lower() or "on_favorable_move"
        )

        # Simulation and user experience defaults
        self.PAPER_TRADING_SIMULATE_ALL: bool = self._env_bool("PAPER_TRADING_SIMULATE_ALL", True)
        self.PAPER_TRADING_SIMULATE_FEES: bool = self._env_bool("PAPER_TRADING_SIMULATE_FEES", True)
        self.PAPER_TRADING_SIMULATE_SLIPPAGE: bool = self._env_bool("PAPER_TRADING_SIMULATE_SLIPPAGE", True)
        self.PAPER_TRADING_START_BALANCE_USD: float = self._env_float("PAPER_TRADING_START_BALANCE_USD", 1000.0)
        self.CHART_STYLE_DEFAULT: str = os.getenv("CHART_STYLE_DEFAULT", "tradingview").strip().lower() or "tradingview"
        self.POSITION_RISK_DEFAULT_PCT: float = self._env_float("POSITION_RISK_DEFAULT_PCT", 1.0)
        self.POSITION_RISK_USER_SELECTABLE: bool = self._env_bool("POSITION_RISK_USER_SELECTABLE", True)

        # Data ingestion choices
        self.SENTIMENT_ROLLOUT_PHASE: str = (
            os.getenv("SENTIMENT_ROLLOUT_PHASE", "rss_fear_greed_first").strip().lower() or "rss_fear_greed_first"
        )
        self.ONCHAIN_ALERT_INCLUDE_EXCHANGE_FLOWS: bool = self._env_bool("ONCHAIN_ALERT_INCLUDE_EXCHANGE_FLOWS", True)
        self.ONCHAIN_ALERT_INCLUDE_DORMANT_MOVES: bool = self._env_bool("ONCHAIN_ALERT_INCLUDE_DORMANT_MOVES", True)

        # AI journal and correlation governance
        self.AI_JOURNAL_AUTO_SEND: bool = self._env_bool("AI_JOURNAL_AUTO_SEND", True)
        self.AI_JOURNAL_WEEKLY_DAY: str = os.getenv("AI_JOURNAL_WEEKLY_DAY", "sunday").strip().lower() or "sunday"
        self.CORRELATION_FILTER_MODE: str = (
            os.getenv("CORRELATION_FILTER_MODE", "best_per_cluster").strip().lower() or "best_per_cluster"
        )

        # Signal Orchestrator / Spam Prevention
        # Cooldown between signal updates for the same signal_id (seconds)
        self.SIGNAL_NOTIFY_COOLDOWN_SECONDS: int = self._env_int("SIGNAL_NOTIFY_COOLDOWN_SECONDS", 900)

        # FIX: Disabled assets
        self.DISABLED_ASSETS: set[str] = {"BRENT"}
        _disabled_raw: str = os.getenv("DISABLED_ASSETS", "").strip().upper()
        if _disabled_raw:
            for asset in _disabled_raw.split(","):
                normalized_asset = asset.strip()
                if normalized_asset:
                    self.DISABLED_ASSETS.add(normalized_asset)

        # Minimum % price change to warrant an edit notification
        self.SIGNAL_UPDATE_THRESHOLD_PCT: float = self._env_float("SIGNAL_UPDATE_THRESHOLD_PCT", 0.1)

        # Enable signal orchestrator for editMessageText support
        self.SIGNAL_ORCHESTRATOR_ENABLED: bool = self._env_bool("SIGNAL_ORCHESTRATOR_ENABLED", True)

        # Database pool settings
        self.DB_POOL_SIZE: int = self._env_int("DB_POOL_SIZE", 8)
        self.DB_MAX_OVERFLOW: int = self._env_int("DB_MAX_OVERFLOW", 3)
        self.DB_SYNC_POOL_SIZE: int = self._env_int("DB_SYNC_POOL_SIZE", 3)
        self.DB_SYNC_MAX_OVERFLOW: int = self._env_int("DB_SYNC_MAX_OVERFLOW", 2)

        # PgBouncer connection pooling support
        self.PGBOUNCER_URL: str = os.getenv("PGBOUNCER_URL", "").strip()

        # Data provider cache TTL
        self.YFINANCE_CACHE_TTL: int = self._env_int("YFINANCE_CACHE_TTL", 60)

        # Score threshold force mode
        self.PREMIUM_SCORE_THRESHOLD_FORCE: bool = self._env_bool("PREMIUM_SCORE_THRESHOLD_FORCE", False)

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


# Database URL helpers (shared across runtime modules).
def _normalize_database_url(raw: str, *, async_driver: bool) -> str:
    raw = str(raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("postgresql+asyncpg://"):
        return raw if async_driver else raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://" if async_driver else "postgresql://", 1)
    if raw.startswith("postgresql://"):
        return raw if not async_driver else raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw


def _build_pg_dsn_from_parts(*, async_driver: bool) -> Optional[str]:
    host = (os.getenv("PGHOST") or os.getenv("POSTGRES_HOST") or os.getenv("DATABASE_HOST") or "").strip()
    user = (os.getenv("PGUSER") or os.getenv("POSTGRES_USER") or os.getenv("DATABASE_USER") or "").strip()
    password = (os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD") or os.getenv("DATABASE_PASSWORD") or "").strip()
    database = (os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB") or os.getenv("DATABASE_NAME") or "").strip()
    port = (os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or os.getenv("DATABASE_PORT") or "").strip()

    if not host or not user or not database:
        return None

    scheme = "postgresql+asyncpg" if async_driver else "postgresql"
    user_enc = quote_plus(user)
    auth = user_enc
    if password:
        auth = f"{user_enc}:{quote_plus(password)}"

    netloc = f"{auth}@{host}"
    if port:
        netloc = f"{netloc}:{port}"

    dsn = f"{scheme}://{netloc}/{database}"

    sslmode = (os.getenv("PGSSLMODE") or os.getenv("DATABASE_SSLMODE") or os.getenv("DB_SSLMODE") or "").strip()
    if sslmode:
        separator = "&" if "?" in dsn else "?"
        try:
            sslmode = quote_plus(sslmode)
        except Exception:
            sslmode = str(sslmode)
        dsn = f"{dsn}{separator}sslmode={sslmode}"

    return dsn


def database_url_candidates(*, async_driver: bool = True) -> list[str]:
    candidates: list[str] = []

    # User-requested preference: PgBouncer URL first when present
    pgbouncer_url = (config.PGBOUNCER_URL or "").strip()
    if pgbouncer_url:
        candidates.append(pgbouncer_url)

    for key in (
        "DATABASE_URL",
        "DATABASE_PRIVATE_URL",
        "DATABASE_PUBLIC_URL",
        "POSTGRES_URL",
        "POSTGRESQL_URL",
    ):
        raw = (os.getenv(key) or "").strip()
        if raw:
            candidates.append(raw)

    if config.DATABASE_URL:
        candidates.append(config.DATABASE_URL)

    built = _build_pg_dsn_from_parts(async_driver=async_driver)
    if built:
        candidates.append(built)

    normalized: list[str] = []
    for raw in candidates:
        url = _normalize_database_url(raw, async_driver=async_driver)
        if url and url not in normalized:
            normalized.append(url)

    return normalized


def prefer_ipv4_database_url(url: str) -> str:
    try:
        import socket as _socket
        from sqlalchemy.engine.url import make_url  # type: ignore

        sa_url = make_url(url)
        host = sa_url.host
        if not host:
            return url
        host = str(host)

        # If already IPv6 or IPv4 literal, keep as is
        if ":" in host or all(c in "0123456789." for c in host):
            return url

        port = int(sa_url.port or 5432)
        infos = _socket.getaddrinfo(host, port, _socket.AF_INET, _socket.SOCK_STREAM)
        if not infos:
            return url

        ipv4 = str(infos[0][4][0])
        return sa_url.set(host=ipv4).render_as_string(hide_password=False)
    except Exception:
        return url


def resolve_database_url(*, async_driver: bool = True) -> Optional[str]:
    candidates = database_url_candidates(async_driver=async_driver)
    if not candidates:
        return None
    return prefer_ipv4_database_url(candidates[0])


# Backwards-compatible top-level exports for modules that import names directly from `config`
OWNER_IDS: Set[int] = set(config.owner_ids)
OWNER_TELEGRAM_ID: int = config.OWNER_TELEGRAM_ID
OWNER_TELEGRAM_IDS: Set[int] = set(config.OWNER_TELEGRAM_IDS)
ADMIN_IDS: Set[int] = set(config.ADMIN_IDS)
TELEGRAM_BOT_TOKEN: str = config.TELEGRAM_BOT_TOKEN
DATABASE_URL: str = config.DATABASE_URL
REDIS_URL: str = config.REDIS_URL
