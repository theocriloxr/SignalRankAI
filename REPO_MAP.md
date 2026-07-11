<!-- Aider Studio repo map — auto-generated. Do not edit by hand. -->
# Repository Map

_400 files indexed · 0 summarized. Summaries, outlines (with line numbers) and metadata only — NOT file contents. To work on a file's actual code, `/read` or `/add` it by the path shown._

## .dockerignore
- # .dockerignore

## .env
- ADMIN_API_TOKEN="Theophilus123/admin"

## .env.complete
- # ═══════════════════════════════════════════════════════════════════════════════════════════════…

## .env.example
- DATABASE_URL=postgresql://postgres:postgres@localhost:5432/signalrank_test

## .env.local
- # Local overrides for development

## .env.production.template
- # Error monitoring (optional)

## .github/workflows/ci.yml
- name: CI

## .gitignore
- .venv/

## .python-version
- 3.12.9

## add_signal_id_to_ml_rejected_signals.sql
- -- Add signal_id column to ml_rejected_signals table

## admin/auto_kill.py
- def daily_loss(session: Session) -> float:  ·L36
- def monthly_drawdown(session: Session) -> float:  ·L48
- def notify_owner(msg: str) -> None:  ·L69
- def evaluate_system_health() -> bool:  ·L82
- async def check():  ·L86
- def halt_system(reason: str) -> None:  ·L105
- def is_system_halted() -> bool:  ·L114

## admin/kill_switch.py
- def check_system():  ·L3

## alembic.ini
- [alembic]

## alembic/migrations/versions/0009_bonus_days_archived.py
- def upgrade() -> None:  ·L18
- def downgrade() -> None:  ·L26

## alembic/migrations/versions/0010_referral_enhancements.py
- def upgrade() -> None:  ·L18
- def downgrade() -> None:  ·L27

## alembic/migrations/versions/0011_add_ml_probability.py
- def upgrade() -> None:  ·L19
- def downgrade() -> None:  ·L24

## alembic/migrations/versions/0011_signal_corrections.py
- def upgrade():  ·L18
- def downgrade():  ·L39

## alembic/migrations/versions/0012_merge_0011_heads.py
- def upgrade() -> None:  ·L17
- def downgrade() -> None:  ·L22

## alembic/migrations/versions/0012_ml_rejection_and_referrals.py
- def upgrade() -> None:  ·L20
- def downgrade() -> None:  ·L52

## alembic/migrations/versions/0013_add_premium_until_column.py
- def upgrade() -> None:  ·L18
- def downgrade() -> None:  ·L23

## alembic/migrations/versions/0014_create_decision_log_table.py
- def upgrade() -> None:  ·L20
- def downgrade() -> None:  ·L39

## alembic/migrations/versions/0015_managed_assets.py
- def upgrade() -> None:  ·L19
- def downgrade() -> None:  ·L48

## alembic/migrations/versions/0016_managed_asset_last_analyzed.py
- def upgrade() -> None:  ·L17
- def downgrade() -> None:  ·L31

## alembic/migrations/versions/0017_accepted_terms.py
- def upgrade() -> None:  ·L16
- def downgrade() -> None:  ·L30

## alembic/migrations/versions/0018_ml_past_training_data.py
- def upgrade() -> None:  ·L19
- def downgrade() -> None:  ·L52

## alembic/migrations/versions/0019_user_execution_mode_and_auto_limit.py
- def upgrade() -> None:  ·L18
- def downgrade() -> None:  ·L29

## alembic/migrations/versions/0020_user_daily_drawdown_guard.py
- def upgrade() -> None:  ·L18
- def downgrade() -> None:  ·L25

## alembic/migrations/versions/0021_auto_cap_default_unlimited.py
- def upgrade() -> None:  ·L18
- def downgrade() -> None:  ·L28

## alembic/migrations/versions/0022_timeseries_partition_tables.py
- def upgrade() -> None:  ·L17
- def downgrade() -> None:  ·L93

## alembic/migrations/versions/0023_outcome_truth_and_delivery_state.py
- def upgrade() -> None:  ·L17
- def downgrade() -> None:  ·L34

## alembic/migrations/versions/0024_add_signal_status.py
- def upgrade() -> None:  ·L17
- def downgrade() -> None:  ·L23

## alembic/migrations/versions/0025_unique_outcome_signal_id.py
- def upgrade() -> None:  ·L16
- def downgrade() -> None:  ·L20

## alembic/versions/0015_add_users_timezone.py
- def upgrade() -> None:  ·L19
- def downgrade() -> None:  ·L32

## analysis.md
- # SignalRankAI - Comprehensive System Analysis & Fixes  ·L1
- ## Executive Summary  ·L3
- ## System Architecture Overview  ·L9
- ### Signal Generation Pipeline  ·L21
- ## Issues Identified from Logs  ·L28
- ### 1. CRITICAL: Zero Final Signals Despite 120 Strategy Signals  ·L30
- # Consensus filter - NO FALLBACK IN PROD  ·L52
- # Final gates: score + expectancy  ·L70
- # Expectancy gate (Phase 3 full impl)  ·L76
- ### 2. CRITICAL: Provider Rate Limits  ·L95

## apply_fix.py
- def apply_fix():  ·L12

## APPLY_ML_COLUMN_IMMEDIATELY.sql
- -- Immediate SQL fix for Railway PostgreSQL

## audit.log
- 2025-12-30 21:28:08,287 - WARNING - KILL SWITCH ENABLED by 1: test

## bot_stderr.log
- (empty)

## bot_stdout.log
- (empty)

## BRAINSTORM_FIX_PLAN.md
- # SignalRankAI Stabilization & Enhancement Plan  ·L1
- ## Executive Summary  ·L3
- ## PHASE 1 — STABILIZATION (Critical Priority)  ·L8
- ### Issue 1.1: Score Normalization Transparency  ·L10
- # Example logging output per asset:  ·L20
- # BTCUSDT  ·L21
- #   EMA Score: 18  ·L22
- #   RSI Score: 12  ·L23
- #   Volume Score: 15  ·L24
- #   Market Structure: 20  ·L25

## BRAINTORM_PLAN.md
- # SignalRankAI Comprehensive Fix Plan  ·L1
- ## Executive Summary  ·L3
- ## Issue 1: Binance Geo-Blocking  ·L13
- ### Root Cause  ·L15
- ### Current Mitigation in Place  ·L18
- ### Proposed Solutions  ·L24
- # In data/fetcher.py - crypto provider priority  ·L36
- ### Files to Modify  ·L40
- ## Issue 2: Rate Limiting (429 Errors) - Polygon & TwelveData for BRENT  ·L46
- ### Root Cause  ·L48

## check_command_access.py
- #!/usr/bin/env python

## CODEBASE_FULL_DOCUMENTATION.md
- # SignalRankAI Full Codebase Documentation  ·L1
- ## Table of Contents  ·L7
- ## 1. Root files  ·L32
- ## 2. core/  ·L38
- ### core/circuit_breaker.py  ·L40
- ### core/command_limits.py  ·L55
- ### core/performance.py  ·L62
- ### core/redis_cache.py  ·L75
- ### core/redis_state.py  ·L90
- ### core/settings.py  ·L115

## COMPREHENSIVE_IMPROVEMENT_PLAN.md
- # SignalRankAI Platform - Comprehensive Improvement Plan  ·L1
- ## Executive Summary  ·L3
- ## 1. UI/UX Enhancement Strategy  ·L6
- ### Telegram Bot Interface Improvements  ·L8
- ### Dashboard Enhancements  ·L14
- ## 2. ML/Gemini Integration Optimization  ·L20
- ### Model Performance Improvements  ·L22
- ### Signal Quality Scoring  ·L28
- ## 3. Signal Generation & Delivery System  ·L33
- ### Signal Generation Enhancement  ·L35

## config.py
- class Config:  ·L4
- def __init__(self):  ·L21
- def _env_int(self, name: str, default: int = 0) -> int:  ·L151
- def _first_env(self, *names: str) -> str:  ·L163
- def _env_int_set(self, name: str) -> set[int]:  ·L170
- def _env_csv(self, name: str, default: list[str] | None = None) -> list[str]:  ·L185
- def _env_bool(self, name: str, default: bool = False) -> bool:  ·L191
- def _env_float(self, name: str, default: float = 0.0) -> float:  ·L197
- def _normalize_database_url(raw: str, *, async_driver: bool) -> str:  ·L210
- def _build_pg_dsn_from_parts(*, async_driver: bool) -> str | None:  ·L223

## conftest.py
- async def _inline_to_thread(func, /, *args, **kwargs):  ·L10

## core/circuit_breaker.py
- class CircuitConfig:  ·L9
- class CircuitBreaker:  ·L15
- def __init__(self, config: CircuitConfig | None = None) -> None:  ·L16
- def _now(self) -> float:  ·L21
- def _prune(self, now_ts: float) -> None:  ·L24
- def allow(self) -> bool:  ·L29
- def record_success(self) -> None:  ·L36
- def record_failure(self) -> bool:  ·L40
- def provider_breaker(name: str) -> CircuitBreaker:  ·L53
- def get_provider_breaker_snapshot() -> dict[str, dict[str, float | int | bool]]:  ·L60

## core/command_limits.py
- """Canonical limits for command throttling and free-tier signal exposure."""

## core/evolution_agent.py
- class EvolutionAgent:  ·L53
- def __init__(self, model_name: str = "gemini-1.5-pro"):  ·L54
- def _get_tail_logs(self, filepath: str, lines: int = 50) -> str:  ·L58
- async def _get_shadow_summary(self, days: int = 7) -> Dict[str, Any]:  ·L67
- async def trigger_system_audit(self, error_log_path: str = "app.log", days: int = 7) -> Optional[Dict[str, Any]]:  ·L123
- async def send_improvement_proposal(self, bot, proposal: Dict[str, Any], admin_id: int) -> bool:  ·L199

## core/patch_manager.py
- class PatchManager:  ·L22
- def __init__(self, repo_path: str = "./"):  ·L23
- def create_backup(self, file_path: str) -> Path:  ·L28
- def list_backups(self, filename: Optional[str] = None) -> list[Path]:  ·L37
- def restore_backup(self, backup_path: Path, target_file: str) -> bool:  ·L45
- async def apply_gemini_patch(self, target_file: str, patch_content: str) -> Tuple[bool, Optional[Path]]:  ·L55
- async def apply_inline_patch(self, target_file: str, new_content: str) -> Tuple[bool, Optional[Path]]:  ·L109

## core/performance.py
- def avg_reward_risk(trades):  ·L1
- def strategy_stats(strategy_name):  ·L5
- async def _fetch():  ·L18
- def dynamic_weight(strategy_name):  ·L36
- class PerformanceTracker:  ·L48
- def __init__(self):  ·L49
- def reset(self):  ·L52
- def log_trade(self, strategy, result, ret, user_ids=None):  ·L62
- def get_stats(self, strategy=None):  ·L85
- def report(self):  ·L100

## core/redis_cache.py
- async def cache_get(key: str) -> Optional[Dict[str, Any]]:  ·L25
- async def cache_set(key: str, value: Any, ttl_category: str = 'default') -> None:  ·L38
- def cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:  ·L52
- async def cached_market_data(symbol: str, timeframe: str, category: str = 'market_data_crypto') -> Optional[Dict]:  ·L62
- async def cache_market_data(symbol: str, timeframe: str, data: Dict, category: str = 'market_data_crypto') -> None:  ·L71
- async def cached_signal(signal_id: str) -> Optional[Dict]:  ·L76
- async def cache_signal(signal: Dict) -> None:  ·L81
- async def cached_user_prefs(user_id: int) -> Dict[str, Any]:  ·L86
- async def cache_user_prefs(user_id: int, prefs: Dict[str, Any]) -> None:  ·L92
- async def cached_news_sentiment(symbol: str) -> Optional[float]:  ·L97

## core/redis_state.py
- def _webhook_queue_key() -> str:  ·L36
- def _redis_max_connections() -> int:  ·L40
- def _resolve_redis_url() -> Optional[str]:  ·L45
- def mark_signal_delivered_sync(user_id: int, signal_id: str) -> None:  ·L51
- def was_signal_delivered_sync(user_id: int, signal_id: str) -> bool:  ·L79
- def get_delivered_signals_sync(user_id: int) -> set:  ·L107
- class KillSwitchState:  ·L137
- class RedisState:  ·L143
- def __init__(self) -> None:  ·L154
- def _redis_url(self) -> Optional[str]:  ·L170

## core/settings.py
- class Settings(BaseSettings):  ·L18
- class Config:  ·L45
- def get_settings() -> Settings:  ·L60
- def validate_required_settings() -> None:  ·L75

## core/signal_governor.py
- def can_send_signal(tier):  ·L11
- def record_signal_sent(tier):  ·L16

## core/telemetry.py
- def prometheus_metrics_text() -> str:  ·L85
- def prometheus_content_type() -> str:  ·L89
- def observe_engine_cycle(seconds: float) -> None:  ·L93
- def observe_engine_task(asset: str, timeframe: str, seconds: float, outcome: str = "ok") -> None:  ·L100
- def observe_signal_dispatch(seconds: float, tier: str, regime: str | None = None, status: str = "ok") -> None:  ·L107
- def observe_signal_generated(asset: str, timeframe: str) -> None:  ·L118
- def observe_ml_confidence(value: float | None) -> None:  ·L125
- def observe_http_request(method: str, route: str, status: int | str, seconds: float) -> None:  ·L134
- def set_exchange_api_health(provider: str, healthy: bool = True) -> None:  ·L141
- def set_exchange_rate_limit(provider: str, remaining: float | None = None, limit: float | None = None) -> None:  ·L148

## core/tier_constants.py
- """Shared tier constants and limits for signal delivery.

## core/trade_tracker.py
- def _set_price_cache(symbol: str, price: float):  ·L18
- def _get_price_cache(symbol: str, max_age_s: float = 120.0):  ·L25
- def _get_backoff_base_seconds() -> float:  ·L37
- def _get_backoff_max_seconds() -> float:  ·L44
- def _backoff_key(symbol: str) -> str:  ·L51
- def _get_backoff_state(symbol: str):  ·L55
- def _next_backoff_delay(failure_count: int) -> float:  ·L59
- def _record_price_failure(symbol: str) -> float:  ·L66
- def _record_price_success(symbol: str):  ·L82
- def _market_closed_reason(symbol: str) -> str | None:  ·L86

## core/validators.py
- def validate_candles(candles: Sequence[Dict[str, Any]]) -> bool:  ·L11

## core/version.py
- def get_version_banner() -> str:  ·L11

## data/alternative_providers.py
- def _env_bool(name: str, default: bool = False) -> bool:  ·L9
- def _env_str(name: str, default: str = "") -> str:  ·L16
- def _numeric_from_payload(payload: Any, *keys: str, default: float = 0.0) -> float:  ·L20
- async def _fetch_json(url: str, *, headers: Dict[str, str] | None = None, params: Dict[str, Any] | None = None, timeout: float = 3.0) -> Dict[str, Any]:  ·L43
- def _context_from_payload(payload: Dict[str, Any], source: str) -> Dict[str, float | str]:  ·L51
- async def fetch_glassnode_context(symbol: str) -> Dict[str, float | str]:  ·L67
- async def fetch_cryptoquant_context(symbol: str) -> Dict[str, float | str]:  ·L81
- async def fetch_onchain_context(symbol: str) -> Dict[str, float | str]:  ·L95

## data/binance_ws.py
- def _env_int(name: str, default: int) -> int:  ·L15
- def _tf_to_binance_interval(tf: str) -> str | None:  ·L22
- def build_streams(symbols: Iterable[str], *, intervals: Iterable[str]) -> list[str]:  ·L29
- async def iter_events(  ·L46

## data/connector_registry.py
- def _wrap_callable(fn: Callable, /) -> Callable:  ·L17
- def _call(symbol: str, tf: str, timeout: int = 10):  ·L19
- def _wrap_to_async(fn: Callable) -> Callable:  ·L36
- async def _call_async(symbol: str, tf: str, timeout: int = 10):  ·L45
- def get_providers_for_asset(asset_type: str) -> List[Tuple[str, Callable]]:  ·L51
- def get_async_providers_for_asset(asset_type: str) -> List[Tuple[str, Callable]]:  ·L139

## data/connectors/__init__.py
- from .base import Connector

## data/connectors/base.py
- class Connector(Protocol):  ·L4
- def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:  # pragma: no cover - interface  ·L5

## data/connectors/binance_adapter.py
- async def _async_get_candles(  ·L24
- def get_candles(  ·L109

## data/connectors/bybit_adapter.py
- def _normalize_symbol(symbol: str) -> str:  ·L13
- def _map_timeframe(timeframe: str) -> str:  ·L20
- async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:  ·L30
- async def _do():  ·L44
- def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:  ·L87

## data/connectors/cryptocompare_adapter.py
- def _map_tf(tf: str):  ·L14
- async def _fetch_for_quote(client, base_raw: str, tsym: str, endpoint: str, aggregate: int, timeout: int):  ·L23
- async def call():  ·L36
- async def cryptocompare_get_candles(symbol: str, timeframe: str, timeout: int = 10) -> List[dict]:  ·L77
- def cryptocompare_get_candles_sync(symbol: str, timeframe: str, timeout: int = 10):  ·L151

## data/connectors/polygon_adapter.py
- async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:  ·L20
- async def _do():  ·L43
- def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:  ·L83

## data/connectors/twelvedata_adapter.py
- async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:  ·L19
- async def _do():  ·L37
- def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:  ·L74

## data/connectors/yfinance_adapter.py
- def _normalize_symbol(symbol: str) -> str:  ·L14
- def _sync_get_candles_impl(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:  ·L47
- async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:  ·L81
- def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:  ·L86

## data/cryptocompare_ws.py
- def _env_int(name: str, default: int) -> int:  ·L15
- def _parse_symbol(symbol: str) -> tuple[str, str] | None:  ·L22
- def build_subs(symbols: Iterable[str]) -> list[str]:  ·L33
- async def iter_events(*, symbols: list[str]) -> AsyncIterator[dict[str, Any]]:  ·L58

## data/fetcher_router.py
- def _mark_provider_result(provider_name: str, ok: bool) -> None:  ·L30
- def _is_provider_healthy(provider_name: str) -> bool:  ·L41
- class DataRouter:  ·L53
- def __init__(self):  ·L56
- def _init_providers(self) -> None:  ·L60
- def _get_bybit_candles(self, symbol: str, timeframe: str) -> List[Dict]:  ·L114
- def _get_cryptocompare_candles(self, symbol: str, timeframe: str) -> List[Dict]:  ·L130
- def _get_coingecko_candles(self, symbol: str, timeframe: str) -> List[Dict]:  ·L139
- def _get_polygon_candles(self, symbol: str, timeframe: str) -> List[Dict]:  ·L148
- def _get_twelvedata_candles(self, symbol: str, timeframe: str) -> List[Dict]:  ·L157

## data/fetcher.py
- def _get_cached_macro_value(symbol: str) -> tuple[float, float, str] | None:  ·L20
- def _set_cached_macro_value(symbol: str, value: float, source: str = "cached") -> None:  ·L33
- def mark_provider_result(provider_name, ok):  ·L50
- def provider_is_healthy(provider_name):  ·L65
- def _get_candle_key_lock(key: tuple[str, str]) -> threading.Lock:  ·L78
- def _read_cached_candles(key: tuple[str, str], ttl_seconds: float, *, allow_stale: bool = False) -> list | None:  ·L87
- def _read_stale_cached_candles(key: tuple[str, str], max_age_seconds: float) -> list | None:  ·L101
- def _prune_candle_cache(max_age_seconds: float) -> None:  ·L105
- def _write_cached_candles(key: tuple[str, str], candles: list) -> None:  ·L113
- def _get_forward_fill_ttl_seconds() -> float:  ·L122

## data/get_live_price.py
- class PriceCircuitConfig:  ·L28
- class PriceCircuitBreaker:  ·L35
- def __init__(self, config: Optional[PriceCircuitConfig] = None):  ·L38
- def _now(self) -> float:  ·L43
- def _prune(self, now_ts: float) -> None:  ·L46
- def allow(self) -> bool:  ·L51
- def record_success(self) -> None:  ·L58
- def record_failure(self) -> bool:  ·L62
- def _get_breaker(provider: str) -> PriceCircuitBreaker:  ·L77
- def _is_crypto(asset: str) -> bool:  ·L88

## data/indicators.py
- def calculate_indicators(candles):  ·L5
- def RSI(series, period):  ·L113
- def MACD(series, fast=12, slow=26, signal=9):  ·L121
- def STOCH_RSI(series, period):  ·L129
- def ATR(df, period):  ·L135
- def BOLLINGER_BANDS(series, period=20, num_std=2):  ·L148
- def ADX(df, period):  ·L156
- def ADX_with_DI(df, period):  ·L176
- def determine_trend_ema(closes: np.ndarray) -> int:  ·L205
- def determine_trend_sma(closes: np.ndarray) -> int:  ·L225

## data/market_data.py
- def _yf_timeout_seconds() -> float:  ·L26
- def _yf_cooldown_seconds() -> float:  ·L33
- def _yf_available() -> bool:  ·L40
- def _set_yf_cooldown(reason: str) -> None:  ·L44
- async def _fetch_yfinance_with_timeout(asset: str, tf: str, limit: int) -> list:  ·L50
- async def _tradingview_indicators(asset: str, tf: str) -> dict:  ·L64
- def format_ticker(symbol: str, provider: str = "yfinance") -> str:  ·L153
- async def fetch_candles_with_circuit_breaker(  ·L222
- async def _try_binance() -> list:  ·L239
- async def _try_yfinance() -> list:  ·L262

## data/market_hours.py
- def get_asset_class(asset: str) -> str:  ·L17
- def is_market_open(asset_class: str) -> Tuple[bool, str]:  ·L71
- def is_fx_holiday(now_utc: Optional[datetime] = None) -> Optional[str]:  ·L184
- def is_stock_holiday(now_utc: Optional[datetime] = None) -> Optional[str]:  ·L192
- def is_commodity_holiday(now_utc: Optional[datetime] = None) -> Optional[str]:  ·L200
- def is_fx_low_liquidity(now_utc: Optional[datetime] = None) -> bool:  ·L208

## data/news.py
- def _safe_text(value) -> str:  ·L14
- def fetch_news_headlines(asset: str, lookback_minutes: int = 120) -> List[Tuple[str, str, int]]:  ·L28
- def _asset_to_x_query(asset: str) -> str:  ·L111
- def _fetch_x_headlines(asset: str, lookback_minutes: int, bearer_token: str) -> List[Tuple[str, str, int]]:  ·L130
- def _asset_to_news_query(asset: str) -> str:  ·L166
- def _is_crypto_asset(asset: str) -> bool:  ·L184
- def simple_sentiment_score(text: str) -> int:  ·L188
- def get_news_sentiment(asset: str, lookback_minutes: int = 120) -> float:  ·L212

## data/pair_discovery.py
- def get_trending_commodity_tickers(top_n=10):  ·L3
- def _refresh_asset_universe():  ·L33
- def get_latest_asset_universe(force_refresh=False):  ·L39
- def _asset_universe_auto_refresh_thread():  ·L45
- def _load_crypto_blacklist() -> set[str]:  ·L85
- def _normalize_legacy_symbol(symbol: str) -> str:  ·L94
- def _filter_blacklisted(pairs: list[str]) -> list[str]:  ·L102
- def _dedupe_limit(items: list[str], limit: int) -> list[str]:  ·L119
- def _is_true(raw: str | None, default: bool = False) -> bool:  ·L134
- def _merge_provider_results(provider_results: list[list[str]], limit: int) -> list[str]:  ·L140

## data/providers.py
- def _env_float(name: str, default: float) -> float:  ·L40
- def _set_cooldown(provider: str, seconds: float) -> None:  ·L47
- def _is_cooldown_active(provider: str) -> bool:  ·L54
- def _rate_limit(provider: str, wait: float) -> None:  ·L62
- def _cache_key(symbol: str, timeframe: str) -> str:  ·L75
- def _set_candles_cache(symbol: str, timeframe: str, candles: list) -> None:  ·L79
- def get_candles(symbol: str, timeframe: str, limit: int = 200):  ·L86
- def _get_candles_cache(symbol: str, timeframe: str, max_age_s: float = 300.0):  ·L103
- def _rate_limit_cooldown_seconds(provider: str, *, status_code: int | None = None, message: str = "") -> float | None:  ·L105
- def _jitter_sleep(base_seconds: float = 1.0, jitter_factor: float = 0.5) -> float:  ·L118

## data/startup_selfcheck.py
- def _env_bool(name: str, default: bool = False) -> bool:  ·L22
- def _log(msg: str) -> None:  ·L32
- def _warn(msg: str) -> None:  ·L36
- def _info(msg: str) -> None:  ·L40
- def _binance_symbol_rest(asset: str) -> str:  ·L44
- def _first_crypto_symbol() -> str:  ·L52
- def check_binance(timeout_seconds: float = 6.0) -> bool:  ·L62
- def check_alphavantage(timeout_seconds: float = 8.0) -> Optional[bool]:  ·L119
- def run_startup_data_selfcheck() -> None:  ·L174

## data/ws_ingest.py
- def _env_bool(name: str, default: bool = False) -> bool:  ·L21
- def _env_int(name: str, default: int) -> int:  ·L28
- def _crypto_timeframes() -> list[str]:  ·L35
- def _crypto_symbols() -> list[str]:  ·L43
- def _tf_seconds(tf: str) -> int:  ·L56
- class _CandleState:  ·L76
- class _CryptoCompareCandleBuilder:  ·L86
- def __init__(self, *, intervals: list[str]) -> None:  ·L87
- def update(self, *, symbol: str, price: float, volume: float, event_time_ms: int) -> list[dict]:  ·L92
- def _choose_ws_provider() -> str:  ·L165

## db/access.py
- def owner_id() -> int:  ·L13
- def is_owner(telegram_user_id: int) -> bool:  ·L18
- async def resolve_user_tier(telegram_user_id: int) -> str:  ·L23
- async def has_full_access(telegram_user_id: int) -> bool:  ·L91

## db/auto_ops.py
- def _env_bool(name: str, default: bool = False) -> bool:  ·L14
- def _sync_database_url() -> Optional[str]:  ·L21
- def _advisory_lock_id() -> int:  ·L38
- def run_startup_ops(run_mode: str) -> None:  ·L43
- def _fresh_start_if_needed(conn: "psycopg2.extensions.connection") -> None:  ·L299

## db/database.py
- """Database connection layer for SignalRankAI.

## db/market_cache.py
- async def upsert_market_tick(  ·L13
- async def upsert_market_candle(  ·L41
- async def get_recent_candles(  ·L89
- async def prune_old_candles(  ·L127

## db/migrations/env.py
- def get_url() -> str:  ·L30
- def run_migrations_offline() -> None:  ·L43
- def run_migrations_online() -> None:  ·L56

## db/migrations/README
- Alembic migrations live here.

## db/migrations/script.py.mako
- """${message}

## db/migrations/versions/0001_init.py
- def upgrade() -> None:  ·L19
- def downgrade() -> None:  ·L107

## db/migrations/versions/0002_features.py
- def upgrade() -> None:  ·L22
- def downgrade() -> None:  ·L123

## db/migrations/versions/0003_runtime_state.py
- def upgrade() -> None:  ·L22
- def downgrade() -> None:  ·L33

## db/migrations/versions/0004_payment_events.py
- def upgrade() -> None:  ·L21
- def downgrade() -> None:  ·L41

## db/migrations/versions/0005_bot_events.py
- def upgrade() -> None:  ·L21
- def downgrade() -> None:  ·L34

## db/migrations/versions/0006_bigint_telegram_ids.py
- def upgrade() -> None:  ·L19
- def downgrade() -> None:  ·L37

## db/migrations/versions/0007_market_data_cache.py
- def upgrade() -> None:  ·L19
- def downgrade() -> None:  ·L49

## db/migrations/versions/0008_user_tier_column.py
- def upgrade() -> None:  ·L21
- def downgrade() -> None:  ·L29

## db/migrations/versions/0009_archived_column.py
- def upgrade() -> None:  ·L21
- def downgrade() -> None:  ·L29

## db/migrations/versions/0010_consolidate_full_schema.py
- def _exec(sql: str) -> None:  ·L31
- def upgrade() -> None:  ·L39
- def downgrade() -> None:  ·L330

## db/migrations/versions/0011_platform_hardening_security_scaling.py
- def _exec(sql: str) -> None:  ·L19
- def upgrade() -> None:  ·L23
- def downgrade() -> None:  ·L110

## db/migrations/versions/0012_outcome_notify_state.py
- def _exec(sql: str) -> None:  ·L19
- def upgrade() -> None:  ·L23
- def downgrade() -> None:  ·L96

## db/migrations/versions/0013_proxy_nodes.py
- def _exec(sql: str) -> None:  ·L19
- def upgrade() -> None:  ·L23
- def downgrade() -> None:  ·L41

## db/migrations/versions/0014_add_outcome_pnl_pct.py
- def upgrade() -> None:  ·L24
- def downgrade() -> None:  ·L34

## db/models.py
- class Base(DeclarativeBase):  ·L32
- def utcnow() -> datetime:  ·L36
- class User(Base):  ·L40
- class Subscription(Base):  ·L67
- class Signal(Base):  ·L86
- class Outcome(Base):  ·L121
- class StrategyStat(Base):  ·L144
- class AdminEvent(Base):  ·L157
- class AlertPreference(Base):  ·L167
- class ReferralCode(Base):  ·L178

## db/pg_compat.py
- def _run(coro):  ·L11
- def postgres_enabled() -> bool:  ·L18
- def get_all_user_ids_compat() -> list[int]:  ·L25
- async def _impl() -> list[int]:  ·L30
- def store_signal_compat(signal: Dict[str, Any]) -> str:  ·L40
- async def _impl() -> str:  ·L45

## db/pg_features.py
- def to_naive_utc(dt: datetime) -> datetime:  ·L7
- async def ensure_alert_prefs(session: AsyncSession, telegram_user_id: int) -> None:  ·L38
- async def _touch_strategy_stat(session: AsyncSession, *, strategy_name: str, strategy_group: str) -> None:  ·L49
- async def record_bot_event(  ·L63
- def _env_int(name: str, default: int) -> int:  ·L82
- def _utcnow() -> datetime:  ·L89
- class SignalDedupBlocked(RuntimeError):  ·L94
- def __init__(self, reason: str, signal_id: str | None = None):  ·L95
- def _env_float(name: str, default: float) -> float:  ·L101
- def _parse_interval_hours(*, default: float, env_names: tuple[str, ...]) -> float:  ·L108

## db/repository.py
- def _env_int(name: str, default: int) -> int:  ·L21
- async def count_active_subscriptions(  ·L28
- async def get_active_subscription(  ·L45
- async def count_active_vip_users(  ·L67
- def normalize_tier(tier: str) -> str:  ·L91
- async def get_or_create_user(  ·L100
- async def activate_subscription(  ·L138
- async def expire_subscriptions(session: AsyncSession) -> int:  ·L187
- async def persist_decision_log(  ·L206
- async def persist_signal(signal_data: Dict[str, Any]) -> Optional[Signal]:  ·L246

## db/session.py
- def _engine_connect_args() -> dict[str, Any]:  ·L22
- def _prefer_ipv4_url(url: str) -> str:  ·L39
- def get_database_url() -> Optional[str]:  ·L43
- def get_database_url_or_none() -> Optional[str]:  ·L53
- def _pool_int(name: str, default: int, minimum: int = 0) -> int:  ·L60
- def _pool_bool(name: str, default: bool = False) -> bool:  ·L67
- def _is_railway_runtime() -> bool:  ·L74
- def _effective_pool_settings() -> tuple[int, int]:  ·L78
- def create_engine() -> Optional[AsyncEngine]:  ·L105
- def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:  ·L130

## deploy_checklist.txt
- SignalRankAI Deployment & Automation Checklist

## DEPLOY_DIAGNOSTIC_ENV.md
- # Diagnostic Deployment Env Vars  ·L1
- ## Safe diagnostic profile  ·L5
- ## Why these matter  ·L23
- ## What to look for after redeploy  ·L32
- ## Optional next step  ·L38

## deploy.bat
- @echo off

## deploy.sh
- #!/bin/bash

## Dockerfile
- FROM python:3.11-slim

## Dockerfile.prod
- # Multi-stage production Dockerfile for smaller runtime image

## docs/FULL_SYSTEM_DOCUMENTATION.md
- # run targeted tests  ·L253
- # run the engine loop once (local dev helper)  ·L256
- # run post-deploy smoke checks  ·L259

## engine_stderr.log
- (empty)

## engine_stdout.log
- [WARN] Could not fetch Binance pairs: HTTPSConnectionPool(host='api.binance.com', port=443): Max …

## engine/admin_pulse.py
- async def compute_engine_health(window_hours: int = 1) -> dict[str, Any]:  ·L18
- async def send_admin_pulse_via_telegram(window_hours: int = 1) -> bool:  ·L138
- async def send_weekly_filter_efficacy_via_telegram(window_days: int = 7) -> bool:  ·L185
- async def start_pulse_loop(interval_seconds: int = None) -> None:  ·L278

## engine/advanced_exit_manager.py
- class ExitStrategy(Enum):  ·L24
- class AdvancedExitManager:  ·L34
- def __init__(self):  ·L37
- def calculate_smart_stops(  ·L47
- def update_to_break_even(  ·L109
- def initialize_trailing_stop(  ·L134
- def update_trailing_stop(  ·L167
- def check_time_based_exit(  ·L209
- def check_invalidation_exit(  ·L236
- def calculate_partial_exit_targets(  ·L278

## engine/advanced_filters.py
- class NewsFilter:  ·L20
- def __init__(self):  ·L23
- def is_news_time(  ·L27
- def load_news_calendar(self, events: List[Dict]):  ·L61
- class OverextendedFilter:  ·L73
- def is_overextended(  ·L76
- class ChopFilter:  ·L108
- def is_choppy(  ·L111
- class CorrelationClusterFilter:  ·L156
- def __init__(self):  ·L159

## engine/analytics.py
- class ExcursionCalculator:  ·L36
- def calculate_mfe_mae(  ·L43
- def calculate_excursion_from_candles(  ·L132
- class AnalyticsTracker:  ·L179
- def __init__(self):  ·L189
- def record_trade(  ·L193
- def get_average_mfe(self, direction: Optional[str] = None) -> float:  ·L228
- def get_average_mae(self, direction: Optional[str] = None) -> float:  ·L250
- def get_optimal_sl(self, direction: str, percentile: float = 95.0) -> float:  ·L272
- def get_optimal_tp(self, direction: str, percentile: float = 50.0) -> float:  ·L302

## engine/auto_optimizer.py
- class OptimizationResult:  ·L36
- class AutoOptimizerRunner:  ·L45
- def __init__(  ·L53
- async def run_optimization(self) -> Optional[OptimizationResult]:  ·L59
- async def _fetch_closed_trades(self) -> list:  ·L96
- def _is_winning_trade(self, trade) -> bool:  ·L118
- def _has_mae_data(self, trade) -> bool:  ·L126
- async def _analyze_mae(  ·L134
- async def apply_recommended_sl(self, result: OptimizationResult) -> bool:  ·L193
- def get_runner() -> AutoOptimizerRunner:  ·L225

## engine/backtest.py
- class BacktestRunner:  ·L12
- def __init__(self, data_frames: Optional[Dict[str, pd.DataFrame]] = None):  ·L17
- def normalize_df(df: pd.DataFrame) -> pd.DataFrame:  ·L24
- def load_from_parquet(self, path: str) -> pd.DataFrame:  ·L31
- def _key(self, asset: str, tf: str) -> str:  ·L35
- def register_dataframe(self, asset: str, tf: str, df: pd.DataFrame) -> None:  ·L38
- def register_tick_dataframe(self, asset: str, tf: str, df: pd.DataFrame) -> None:  ·L41
- def get_tick_df(self, asset: str, tf: str) -> Optional[pd.DataFrame]:  ·L50
- def register_orderbook_dataframe(self, asset: str, tf: str, df: pd.DataFrame) -> None:  ·L53
- def get_orderbook_df(self, asset: str, tf: str) -> Optional[pd.DataFrame]:  ·L67

## engine/confluence_engine.py
- def _env_int(name: str, default: int) -> int:  ·L37
- def _candles_to_df(candles: list) -> Optional[pd.DataFrame]:  ·L44
- def _vote_ema_stack(df: pd.DataFrame) -> Tuple[int, str]:  ·L67
- def _vote_ema_cross(df: pd.DataFrame) -> Tuple[int, str]:  ·L80
- def _vote_sma_cross(df: pd.DataFrame) -> Tuple[int, str]:  ·L98
- def _vote_macd_cross(df: pd.DataFrame) -> Tuple[int, str]:  ·L111
- def _vote_rsi_trend(df: pd.DataFrame) -> Tuple[int, str]:  ·L132
- def _vote_rsi_extreme(df: pd.DataFrame) -> Tuple[int, str]:  ·L149
- def _vote_bollinger(df: pd.DataFrame) -> Tuple[int, str]:  ·L166
- def _vote_bb_squeeze(df: pd.DataFrame) -> Tuple[int, str]:  ·L187

## engine/consensus.py
- def _env_float(name: str, default: float) -> float:  ·L11
- def _env_bool(name: str, default: bool = False) -> bool:  ·L18
- def consensus_filter(signals, min_score=None):  ·L25
- def group_by_asset_and_direction(signals):  ·L139
- def unique_strategy_groups(group):  ·L150
- def contains_required_groups(strategies_used):  ·L163
- def best_signal_in_group(group):  ·L176
- def _rank(sig):  ·L181

## engine/core.py
- def is_commodity(asset: Any) -> bool:  # type: ignore  ·L43
- class _DummyExposureManager:  ·L66
- async def is_trade_allowed(self, session, asset_class, direction):  ·L67
- def _detect_order_blocks(candles, lookback=100) -> bool:  # type: ignore  ·L82
- class SqueezeDetector:  ·L89
- async def get_squeeze_bias(self, asset: str) -> str:  ·L90
- async def get_squeeze_bias(asset: str) -> str:  ·L92
- class MarketCircuitBreaker:  ·L99
- async def check_market_health(self) -> bool:  ·L100
- async def check_market_health() -> bool:  ·L102

## engine/correlation_filter.py
- def _env_int(name: str, default: int) -> int:  ·L10
- def _env_float(name: str, default: float) -> float:  ·L23
- def _signal_asset(signal: Dict[str, Any]) -> str:  ·L42
- def _signal_timeframe(signal: Dict[str, Any]) -> str:  ·L46
- def _signal_score(signal: Dict[str, Any]) -> float:  ·L50
- def _cluster_for_symbol(symbol: str) -> str:  ·L57
- def cluster_key(signal: Dict[str, Any]) -> Tuple[str, str]:  ·L81
- def select_best_per_cluster(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:  ·L87
- class PortfolioExposureManager:  ·L117
- def __init__(  ·L120

## engine/correlation_guard.py
- class CorrelationManager:  ·L53
- def __init__(  ·L63
- async def check_and_veto(  ·L71
- async def _get_same_direction_count(self, direction: str) -> int:  ·L108
- async def _check_correlation(  ·L128
- def _get_correlation_group(self, asset: str) -> Optional[str]:  ·L161
- def _symbols_correlated(self, asset1: str, asset2: str) -> bool:  ·L171
- async def _get_open_assets(self, direction: str) -> List[str]:  ·L186
- class PortfolioCorrelationGuard:  ·L207
- def __init__(self):  ·L214

## engine/cycle_queue.py
- class AssetCycleQueue:  ·L36
- def __init__(self) -> None:  ·L54
- def refresh_universe(self, assets: List[str], *, force: bool = False) -> None:  ·L71
- def pop_batch(self, size: int = 10) -> List[str]:  ·L108
- def mark_done(self, assets: List[str], signals_generated: int = 0) -> None:  ·L125
- def remove_from_queue(self, assets: List[str]) -> int:  ·L133
- def round_no(self) -> int:  ·L151
- def queue_remaining(self) -> int:  ·L155
- def universe_size(self) -> int:  ·L160
- def round_progress(self) -> str:  ·L165

## engine/demo_runner.py
- def demo_run():  ·L6

## engine/derivatives.py
- class SqueezeDetector:  ·L29
- def __init__(  ·L42
- async def _get_session(self) -> aiohttp.ClientSession:  ·L57
- async def close(self):  ·L64
- async def get_squeeze_bias(self, asset: str) -> str:  ·L69
- async def get_funding_rate(self, asset: str) -> Optional[float]:  ·L138
- async def get_btc_price(self) -> Optional[float]:  ·L167
- async def check_veto(self, asset: str, signal_direction: str) -> tuple[bool, str]:  ·L206
- async def get_squeeze_bias(asset: str) -> str:  ·L235
- async def check_veto(asset: str, signal_direction: str) -> tuple[bool, str]:  ·L248

## engine/endgame_integration.py
- async def _auto_optimizer_loop(self) -> None:  ·L42
- def get_endgame_status() -> Dict[str, bool]:  ·L114
- async def enrich_signal_execution(signal: Dict[str, Any], adx: float = 30) -> Dict[str, Any]:  ·L124
- def format_execution_info(strategy: Dict[str, Any]) -> str:  ·L152

## engine/execution_router.py
- class SmartRouter:  ·L35
- def __init__(  ·L46
- async def get_execution_decision(  ·L52
- async def _estimate_spread_savings(self, asset: str) -> float:  ·L109
- def _default_strategy(self) -> Dict[str, Any]:  ·L122
- def format_execution_message(self, strategy: Dict[str, Any]) -> str:  ·L132
- def get_router() -> SmartRouter:  ·L159
- async def get_execution_strategy(  ·L167

## engine/exit_manager.py
- class ExitManager:  ·L19
- def __init__(self):  ·L22
- def check_stop_loss(  ·L25
- def check_take_profit(  ·L44
- def update_trailing_stop(  ·L62
- def calculate_breakeven_stop(  ·L103
- def get_partial_exit_target(  ·L124
- def time_based_exit(  ·L145
- def check_invalidation(  ·L161
- def calculate_exit_stats(  ·L187

## engine/expectancy_gate.py
- async def get_live_expectancy(  ·L22
- async def expectancy_gate(signal: Dict[str, Any]) -> bool:  ·L89
- async def global_expectancy_check(global_dd: float) -> bool:  ·L117
- async def validate_expectancy_pipeline(signal: Dict[str, Any]) -> Dict[str, Any]:  ·L124

## engine/filters.py
- class SignalFilter:  ·L19
- def __init__(self):  ·L22
- def apply_all_filters(  ·L26
- def check_volume(self, signal: Dict, market_data: Dict) -> bool:  ·L61
- def check_volume_spike(  ·L76
- def check_liquidity(self, signal: Dict, market_data: Dict) -> bool:  ·L89
- def check_spread(self, signal: Dict, market_data: Dict) -> bool:  ·L111
- def check_regime(self, signal: Dict) -> bool:  ·L127
- def check_correlation(  ·L148
- def _are_correlated(self, symbol1: str, symbol2: str, threshold: float = 0.7) -> bool:  ·L182

## engine/loop.py
- def _apply_drift_confidence_adjustment(confidence: float | None) -> tuple[float | None, dict]:  ·L27
- async def _process_asset_timeframe(asset: str, timeframe: str, include_ml: bool = False) -> list:  ·L50
- async def run_once(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, List]:  ·L204
- async def _run_task(asset: str, timeframe: str) -> list:  ·L212
- async def main_loop(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False, interval_seconds: int = 120):  ·L263
- def start_engine_loop(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False, interval_seconds: int = 120):  ·L296
- def demo_start():  ·L301

## engine/market_circuit_breaker.py
- class MarketCircuitBreaker:  ·L33
- def __init__(  ·L46
- async def _get_session(self) -> aiohttp.ClientSession:  ·L73
- async def close(self):  ·L80
- async def get_btc_price(self) -> Optional[float]:  ·L85
- async def get_btc_price_1h_ago(self) -> Optional[float]:  ·L122
- def _record_price(self, price: float) -> None:  ·L140
- async def check_market_health(self) -> bool:  ·L146
- def is_halted(self) -> bool:  ·L215
- def get_halt_remaining_seconds(self) -> float:  ·L224

## engine/market_state.py
- async def _get_market_state_async(asset: str, timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, Any]:  ·L23
- async def get_market_state_async(asset: str, timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, Any]:  ·L87
- def get_market_state_sync(asset: str, timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, Any]:  ·L92
- def get_market_state(asset: str, timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, Any]:  ·L99

## engine/microstructure.py
- class OrderBookAnalyzer:  ·L19
- def __init__(self, imbalance_threshold: float = 1.5):  ·L22
- async def _get_session(self) -> aiohttp.ClientSession:  ·L37
- async def close(self):  ·L44
- async def fetch_order_book(self, symbol: str) -> Optional[Dict[str, Any]]:  ·L49
- def calculate_volume(self, orders: list) -> float:  ·L78
- async def check_path_clear(  ·L99
- async def get_imbalance_ratio(self, symbol: str) -> Optional[float]:  ·L181
- async def check_order_book(  ·L215

## engine/ml_logger.py
- async def log_ml_prediction(  ·L14
- async def log_ml_training_data(  ·L86
- async def get_training_data_count(session) -> int:  ·L190
- async def get_pending_training_signals(  ·L204

## engine/ml.py
- def _asset_class_to_int(asset: str) -> float:  ·L36
- def _num(value: Any, default: float = 0.0) -> float:  ·L48
- def _model_path() -> Path:  ·L55
- def _load_model() -> None:  ·L62
- def _load_shadow_model() -> None:  ·L95
- def _persist_shadow_prediction(signal: Dict[str, Any], prob: float, schema_ok: bool, prob_source: str = "model") -> None:  ·L123
- async def _save():  ·L137
- def _feature_vector(signal: Dict[str, Any], feature_cols: Iterable[str]) -> Optional[np.ndarray]:  ·L168
- def _hash_bucket(val: str, buckets: int = 64) -> float:  ·L207
- def score_signal(signal: Dict[str, Any]) -> Optional[float]:  ·L277

## engine/mtf_analysis.py
- class MultiTimeframeAnalyzer:  ·L18
- def __init__(self):  ·L27
- def get_htf_bias(  ·L30
- def validate_against_htf(  ·L109
- def get_mtf_confluence(  ·L141
- def _detect_higher_highs(self, highs) -> bool:  ·L188
- def _detect_lower_lows(self, lows) -> bool:  ·L194
- def _trend_ratio(self, series, direction: str = "up") -> float:  ·L200
- def detect_htf_bias_flip(  ·L213

## engine/news_filter.py
- async def _gemini_sentiment(asset: str, headlines: list) -> str:  ·L29
- async def get_today_high_impact_news() -> List[Dict[str, Any]]:  ·L37
- async def gemini_get_sentiment(asset: str, headlines: list) -> str:  ·L46
- async def fetch_news_headlines(asset: str, lookback_minutes: int = 120) -> list:  ·L55
- class NewsKillswitch:  ·L60
- def __init__(self, block_window_minutes: int = 30):  ·L71
- async def is_market_volatile(self, asset: str, news_events: list) -> bool:  ·L84
- async def is_safe_to_trade(self, asset: str) -> bool:  ·L133
- async def get_trading_bias(self, asset: str, headlines: list) -> str:  ·L240
- def get_news_context(self, asset: str) -> Dict[str, Any]:  ·L254

## engine/onchain_alpha.py
- class OnChainAlpha:  ·L34
- def __init__(self):  ·L47
- async def check_veto(  ·L50
- async def _check_exchange_inflows(self, asset: str) -> Tuple[bool, str]:  ·L83
- async def check_whale_alert(  ·L103
- def get_alpha() -> OnChainAlpha:  ·L134
- async def check_veto(asset: str, direction: str = "long") -> Tuple[bool, str]:  ·L142

## engine/price_fetcher.py
- class PriceBreakerConfig:  ·L27
- class PriceCircuitBreaker:  ·L34
- def __init__(self, provider_name: str, config: Optional[PriceBreakerConfig] = None):  ·L37
- def _now(self) -> float:  ·L44
- def _prune(self, now_ts: float) -> None:  ·L47
- def allow(self) -> bool:  ·L52
- def record_success(self) -> None:  ·L59
- def record_failure(self) -> bool:  ·L64
- def is_open(self) -> bool:  ·L77
- def open_remaining(self) -> float:  ·L80

## engine/price_validator.py
- def _utcnow_naive() -> datetime:  ·L13
- def get_asset_type(asset: str) -> str:  ·L17
- def is_signal_fresh(signal: Dict, current_time: Optional[datetime] = None) -> Tuple[bool, str]:  ·L29
- def validate_price_drift(signal: Dict, current_price: float) -> Tuple[bool, str, Optional[Dict]]:  ·L69
- def check_sl_tp_hit(signal: Dict, current_price: float) -> Tuple[bool, Optional[str]]:  ·L140
- def get_current_price(asset: str) -> Optional[float]:  ·L182
- def enrich_signal_with_live_price(signal: Dict) -> Dict:  ·L251
- def is_signal_stale(signal: Dict) -> bool:  ·L307
- def filter_stale_signals(signals: list) -> list:  ·L368

## engine/ranking.py
- def _env_float(name: str, default: float) -> float:  ·L6
- def rank_signals(signals):  ·L13

## engine/realtime_outcome_tracker.py
- def _check_interval() -> int:  ·L31
- def _lookback_hours() -> int:  ·L38
- async def _fetch_active_signals() -> List[Dict[str, Any]]:  ·L45
- async def _fetch_delivered_untracked_signals(limit: int = 250) -> List[Dict[str, Any]]:  ·L90
- async def _get_live_price(symbol: str) -> Optional[float]:  ·L147
- def _parse_tp_levels(take_profit_raw: Any) -> List[float]:  ·L156
- def _check_hit(  ·L182
- def _halfway_to_tp1_reached(direction: str, entry: float, tp1: float, price: float) -> bool:  ·L212
- def _risk_free_cache_key(signal_id: str) -> str:  ·L224
- def _tp_progress_cache_key(signal_id: str) -> str:  ·L228

## engine/referral_manager.py
- class ReferralManager:  ·L13
- async def get_referral_count(self, user_id: int) -> int:  ·L19
- async def check_and_apply_reward(self, referrer_id: int) -> Tuple[bool, str]:  ·L33
- async def record_referral(self, referrer_id: int, referred_user_id: int, is_successful: bool = False) -> bool:  ·L99
- async def mark_referral_successful(self, referred_user_id: int) -> bool:  ·L119

## engine/regime_filter.py
- class MarketRegimeFilter:  ·L16
- def __init__(self, adx_threshold: float = 25.0):  ·L19
- def is_trending(self, adx_value: float) -> bool:  ·L29
- def should_filter(self, adx_value: Optional[float], strategy_type: str = "trend") -> bool:  ·L50
- def calculate_adx_from_candles(candles: list) -> Optional[float]:  ·L69
- async def check_regime_filter(candles: list, strategy_type: str = "trend") -> tuple[bool, Optional[float]]:  ·L163

## engine/regime.py
- def detect_market_regime(market_data):  ·L1

## engine/risk_analytics.py
- def sharpe_ratio(returns: list[float], risk_free_rate: float = 0.0) -> float:  ·L8
- def sortino_ratio(returns: list[float], target_return: float = 0.0) -> float:  ·L20
- def monte_carlo_monthly_projection(  ·L33

## engine/risk_manager.py
- class RiskManager:  ·L27
- def __init__(self, account_equity: float):  ·L30
- def get_dynamic_risk_pct(self, signal: Dict, account_state: Optional[Any] = None) -> float:  ·L34
- def calculate_position_size(  ·L72
- def calculate_atr_stops(  ·L99
- def validate_rr_ratio(  ·L122
- def can_open_trade(  ·L136
- def calculate_trailing_stop(  ·L150
- def calculate_partial_exit_levels(  ·L171
- class SmartRiskSizer:  ·L193

## engine/risk_sizer.py
- class SmartRiskSizer:  ·L13
- def __init__(  ·L14
- def calculate_position_size(  ·L44
- def calculate_position_value(  ·L113
- def get_risk_config(self) -> Dict[str, Any]:  ·L137
- def update_account_balance(self, new_balance: float) -> None:  ·L157
- def get_risk_sizer(  ·L166
- def calculate_position_size(  ·L184

## engine/risk.py
- def _env_float(name: str, default: float) -> float:  ·L15
- def _env_bool(name: str, default: bool = False) -> bool:  ·L22
- def get_max_volatility(asset_type: str) -> float:  ·L33
- def soft_throttle_active(account_state: Any) -> bool:  ·L41
- def hard_stop_active(account_state: Any) -> bool:  ·L46
- def check_correlation_gate(  ·L51
- def calculate_dynamic_risk(signal: Dict[str, Any], regime: Optional[str] = None, news_sentiment: Optional[float] = None, gemini_score: Optional[float] = None, account_state: Optional[Any] = None) -> Dict[str, Any]:  ·L102
- def risk_check(signal: Dict[str, Any], account_state: Any) -> bool:  ·L157
- def calculate_position_size(signal: Dict[str, Any], account_balance: float, risk_pct: Optional[float] = None) -> Optional[float]:  ·L237

## engine/scoring.py
- def _direction_sign(direction_val) -> float:  ·L1
- def _env_float(name: str, default: float) -> float:  ·L24
- def score_signal(signal):  ·L31
- def calculate_signal_score(signal, risk_profile=None, regime=None):  ·L175
- def calculate_confluence(signal: dict) -> float | None:  ·L180
- def strategy_agreement_score(signal):  ·L259
- def rr_score(rr):  ·L263
- def htf_alignment_score(signal):  ·L292
- def regime_fit_score(signal, regime=None):  ·L296
- def volatility_quality_score(signal):  ·L300

## engine/shadow_outcome_worker.py
- class ShadowOutcomeWorker:  ·L20
- def __init__(self) -> None:  ·L21
- async def start(self) -> None:  ·L27
- async def stop(self) -> None:  ·L34
- async def _run_loop(self) -> None:  ·L44

## engine/signal_analytics.py
- class SignalAnalytics:  ·L10
- def __init__(self):  ·L11
- def log_delivery(self, symbol, delivered=True):  ·L18
- def log_fill(self, symbol, filled):  ·L23
- def log_user_engagement(self, user_id):  ·L27
- def get_stats(self):  ·L31
- def flush(self):  ·L39
- def calculate_volume_delta(candles: list[dict], window: int = 20) -> dict:  ·L53

## engine/signal_calculations.py
- def calculate_profit_loss_pct(entry: float, exit_price: float, direction: str) -> float:  ·L10
- def calculate_expected_profit(signal: Dict) -> Optional[float]:  ·L32
- def calculate_expected_loss(signal: Dict) -> Optional[float]:  ·L65
- def calculate_risk_reward(signal: Dict) -> Optional[float]:  ·L82
- def calculate_position_size(signal: Dict, account_balance: float = 10000, risk_pct: float = 1.0) -> Optional[float]:  ·L103
- def calculate_pips(asset: str, entry: float, exit_price: float) -> Optional[float]:  ·L141
- def calculate_signal_age_minutes(signal: Dict) -> Optional[int]:  ·L171
- def get_price_status_indicator(signal: Dict) -> str:  ·L194
- def format_enhanced_signal_data(signal: Dict) -> Dict:  ·L235

## engine/signal_context.py
- class SignalContext:  ·L18
- def __init__(self):  ·L21
- def calculate_entry_zone(  ·L25
- def _get_entry_status(  ·L53
- def wait_for_candle_close(  ·L72
- def calculate_signal_expiration(  ·L100
- def check_signal_invalidation(  ·L120
- def detect_trading_session(self) -> str:  ·L157
- def should_send_no_trade_alert(  ·L181
- def calculate_expected_holding_time(  ·L231

## engine/signal_controller.py
- class ControllerDecision:  ·L21
- class SignalController:  ·L26
- def __init__(self) -> None:  ·L43
- def enable_kill_switch(self, reason: str = "manual", admin_id: Optional[int] = None) -> None:  ·L67
- def disable_kill_switch(self, admin_id: Optional[int] = None) -> None:  ·L75
- def is_kill_switch_enabled(self) -> bool:  ·L83
- def log_audit_event(self, event: str, user_id: Optional[int] = None, details: Any = None) -> None:  ·L87
- def deduplicate_signals(self, signals: List[Signal]) -> List[Signal]:  ·L95
- def normalize_signals(self, signals: List[Signal]) -> List[Signal]:  ·L98
- def pick_best_direction_per_pair(self, signals: List[Signal]) -> List[Signal]:  ·L105

## engine/signal_dedup_strict.py
- class StrictSignalDedup:  ·L29
- def _normalize(value: Any, default: str = "") -> str:  ·L38
- def _make_key(asset: str, timeframe: str, direction: str) -> str:  ·L43
- async def is_duplicate_strict(  ·L54
- async def find_duplicates_strict(  ·L118
- async def dedupe_batch_strict(  ·L181
- def _rank(sig: Dict[str, Any]) -> Tuple[float, float]:  ·L222
- async def is_signal_duplicate_strict(  ·L244
- async def dedupe_signals_batch_strict(  ·L261

## engine/signal_deduplicator.py
- class SignalDeduplicator:  ·L18
- def __init__(self):  ·L21
- def make_fingerprint(self, asset: str, timeframe: str, direction: str, entry_price: float) -> str:  ·L29
- def _safe_float(value: Any, default: float = 0.0) -> float:  ·L34
- def _normalize_text(value: Any) -> str:  ·L41
- def _first_take_profit(value: Any) -> Any:  ·L45
- def _entry_distance_pct(self, left: float, right: float) -> float:  ·L53
- def _time_decay_threshold(self, age_hours: float) -> float:  ·L57
- def _signal_similarity(self, left: Signal, right: Signal) -> float:  ·L63
- def _decayed_duplicate_threshold(self, age_hours: float) -> float:  ·L107

## engine/signal_metrics.py
- def _safe_float(value: Any) -> Optional[float]:  ·L6
- def _clamp_ratio(value: Any) -> Optional[float]:  ·L15
- def resolve_confidence_ratio(signal: Mapping[str, Any]) -> Optional[float]:  ·L29
- def resolve_score_percent(signal: Mapping[str, Any]) -> Optional[float]:  ·L41
- def resolve_confluence_percent(signal: Mapping[str, Any]) -> Optional[float]:  ·L54
- def resolve_confluence_total(signal: Mapping[str, Any]) -> Optional[int]:  ·L85
- def resolve_ml_probability(signal: Mapping[str, Any]) -> Optional[float]:  ·L97

## engine/signal_monitor.py
- class SignalMonitor:  ·L14
- def __init__(self):  ·L17
- async def start(self):  ·L22
- async def stop(self):  ·L32
- async def _monitor_loop(self):  ·L43
- async def check_active_signals(self):  ·L66
- async def _get_active_signals(self) -> List[Dict]:  ·L87
- async def _check_signal(self, signal: Dict):  ·L124
- async def _notify_signal_outcome(self, signal: Dict, current_price: float, reason: str):  ·L143
- async def _get_signal_recipients(self, signal_id: str) -> List[int]:  ·L198

## engine/signal_validator.py
- def validate_signal(signal: dict) -> tuple[bool, Optional[str]]:  ·L10
- async def create_signal_correction(  ·L90
- async def notify_signal_correction(  ·L115

## engine/signal_validators.py
- def normalize_tp_structure(signal_dict: Dict[str, Any]) -> Dict[str, Any]:  ·L17
- def _auto_calculate_tp_levels(signal: Dict[str, Any]) -> Dict[str, Any]:  ·L107
- def validate_signal_structure(signal: Dict[str, Any]) -> Tuple[bool, Optional[str]]:  ·L175
- def normalize_signal_for_ml(signal: Dict[str, Any]) -> Dict[str, Any]:  ·L243

## engine/signal.py
- class Signal:  ·L8

## engine/similarity.py
- def _env_float(name: str, default: float) -> float:  ·L29
- def _env_bool(name: str, default: bool = False) -> bool:  ·L36
- def calculate_similarity_score(  ·L50
- async def check_historical_similarity(  ·L143
- def check_historical_similarity_sync(  ·L233
- def get_historical_winrate(  ·L245
- def get_historical_winrate_sync(  ·L316
- async def get_similar_signals(  ·L333
- def get_similar_signals_sync(  ·L420
- class SimilarityEngine:  ·L432

## engine/smart_dca.py
- class DCAProfile:  ·L25
- class SmartDCA:  ·L61
- def __init__(self, profile_name: str = "balanced"):  ·L64
- async def should_dca(self, signal_id: str, current_price: float, entry_price: float) -> Tuple[bool, str]:  ·L68
- async def execute_dca(  ·L100
- def should_breakeven(self, unrealized_pnl_pct: float) -> bool:  ·L154
- def get_trail_stop(self, high_watermark_pct: float) -> float:  ·L158
- def _calc_drawdown(self, entry: float, current: float, direction: str) -> float:  ·L162
- def _calc_position_size(self, balance: float, signal: Signal, risk_pct: float = 1.0) -> float:  ·L168
- def _calc_avg_entry(self, orig_entry: float, dca_price: float, weight: float) -> float:  ·L174

## engine/stale_signal_validator.py
- class StaleSignalValidator:  ·L31
- def __init__(self):  ·L44
- def get_threshold(self) -> float:  ·L71
- def validate(self, signal_price: float, live_price: float) -> bool:  ·L75
- def _env_float(name: str, default: float) -> float:  ·L113
- def _env_bool(name: str, default: bool = False) -> bool:  ·L120
- def _detect_asset_class(symbol: str) -> str:  ·L127
- def get_dynamic_threshold(symbol: str, atr_value: float = 0.0, price: float = 0.0) -> float:  ·L143
- def _threshold_pct(symbol: str = "") -> float:  ·L171
- def _fetch_timeout() -> float:  ·L200

## engine/stats_manager.py
- class GlobalStats:  ·L16
- def reset(cls) -> None:  ·L44
- def increment_scanned(cls, amount: int = 1) -> None:  ·L58
- def increment_delivered(cls, amount: int = 1) -> None:  ·L64
- def increment_vetoed(cls, reason: str, amount: int = 1) -> None:  ·L70
- def get_stats(cls) -> Dict[str, Any]:  ·L88
- def get_total_vetoed(cls) -> int:  ·L103

## engine/strategies/__init__.py
- from .base import Strategy

## engine/strategies/base.py
- class Strategy:  ·L8
- def generate(self, market_data: dict) -> List[Signal]:  # pragma: no cover - interface  ·L15

## engine/strategies/commodity.py
- class CommodityStrategy(Strategy):  ·L9
- def generate(self, market_data: dict) -> List[Signal]:  ·L12

## engine/strategies/runner.py
- def run_strategy_with_marketstate(strategy: Any, asset: str, timeframes: Iterable[str], include_ml: bool = False) -> List[Signal]:  ·L7
- async def run_strategy_with_marketstate_async(strategy: Any, asset: str, timeframes: Iterable[str], include_ml: bool = False) -> List[Signal]:  ·L45

## engine/strategies/signal_generator.py
- class StrategySignal:  ·L15
- class StrategySelector:  ·L29
- def select_strategy_for_asset(self, asset: str) -> str:  ·L39
- def _classify_asset(self, asset: str) -> str:  ·L45
- class SignalGenerator:  ·L57
- def __init__(self):  ·L60
- def generate_signals(self, asset: str, timeframe: str, market_data: Dict[str, Any]) -> List[StrategySignal]:  ·L63
- def _ema_crossover(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:  ·L106
- def _macd_histogram(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:  ·L148
- def _adx_directional(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:  ·L187

## engine/strategy_selector.py
- def get_best_strategies_for_asset(asset):  ·L7

## engine/threshold_optimizer.py
- class ThresholdConfig:  ·L45
- def to_dict(self) -> Dict[str, Any]:  ·L53
- class AdaptiveThresholdOptimizer:  ·L63
- def __init__(self):  ·L74
- def _load_from_env(self) -> None:  ·L81
- async def _load_from_db(self) -> bool:  ·L104
- async def _save_to_db(self) -> bool:  ·L136
- async def _analyze_performance(self) -> Dict[str, Any]:  ·L159
- def _calculate_new_threshold(  ·L278
- def _calculate_gate_thresholds(  ·L363

## engine/tier_notifications.py
- class TierNotificationManager:  ·L15
- def __init__(self):  ·L18
- def format_new_signal(  ·L44
- def format_tp_hit_notification(  ·L173
- def format_sl_hit_notification(  ·L231
- def format_signal_update(  ·L266
- def format_no_trade_alert(  ·L321
- def format_performance_update(  ·L343
- def _get_status_emoji(self, status: str) -> str:  ·L383
- def _format_time_remaining(self, expires_at: datetime) -> str:  ·L392

## engine/tiered_executor.py
- def calculate_lot_size_premium(user) -> float:  # type: ignore[valid-type]  ·L72
- def calculate_lot_size_vip(  ·L83
- def _is_new_day(user) -> bool:  # type: ignore[valid-type]  ·L140
- def reset_daily_counter_if_needed(user) -> bool:  # type: ignore[valid-type]  ·L151
- def can_execute_premium(user) -> Tuple[bool, str]:  # type: ignore[valid-type]  ·L163
- def can_execute_vip(user) -> Tuple[bool, str]:  # type: ignore[valid-type]  ·L180
- async def can_execute(user) -> Tuple[bool, str]:  # type: ignore[valid-type]  ·L188
- async def _record_execution(  ·L202
- async def execute_premium_signal(  ·L243
- async def execute_vip_signal(  ·L342

## engine/trade_manager.py
- class TradeManager:  ·L19
- def __init__(  ·L22
- def parse_tp_levels(self, take_profit: Any) -> List[float]:  ·L41
- def get_tp1(  ·L101
- def should_move_to_breakeven(  ·L133
- def calculate_new_sl(  ·L172
- async def process_active_trades(  ·L206
- async def check_and_move_sl(  ·L284

## engine/ultra_quality_filter.py
- def _env_float(name: str, default: float) -> float:  ·L27
- class UltraQualityFilter:  ·L38
- def __init__(self):  ·L41
- def apply_ultra_filter(self, signal: Dict) -> Tuple[bool, str, float]:  ·L60
- def _calculate_strict_confluence(self, signal: Dict) -> float:  ·L173
- def _check_entry_zone_natural(self, signal: Dict) -> bool:  ·L239
- def _is_overextended(self, signal: Dict) -> bool:  ·L255
- def calculate_dynamic_position_size(  ·L267
- def record_trade_result(  ·L317
- def get_stats(self) -> Dict:  ·L338

## engine/wfo.py
- def _month_ranges(start: datetime, end: datetime):  ·L22
- class WalkForwardOptimizer:  ·L30
- def __init__(self, runner: BacktestRunner):  ·L38
- def _timeframe_minutes(timeframe: str | None) -> int:  ·L42
- def _average_daily_volume_notional(df: pd.DataFrame | None, timeframe: str | None, price_fallback: float = 1.0) -> float:  ·L58
- def _market_impact_pct(  ·L72
- def _simulate_pnl(  ·L91
- def _label_signals(self, signals: Iterable[Dict[str, Any]], df_map: Dict[str, pd.DataFrame], lookahead_minutes: int = 1440) -> Dict[int, int]:  ·L301
- def default_train_xgb(self, train_signals: Iterable[Dict[str, Any]], df_map: Dict[str, pd.DataFrame]):  ·L340
- def _const(sig):  ·L346

## fix_bot_resend.py
- """One-shot fix: repair the corrupted format_signal call in bot.py resend path."""

## fix_commands.py
- #!/usr/bin/env python3

## fix_created_at_column.sql
- -- Fix for: WARNING engine.admin_pulse: created_at column missing in signal_deliveries

## fix_created_at.py
- async def check_and_add_column():  ·L7

## FIX_INTEGRATION_GUIDE.md
- # SignalRankAI Critical Fixes Integration Guide  ·L1
- ## Task 1: Fix Event Loop Blocking  ·L7
- ### Solution Applied in railway_main.py  ·L11
- ### Synchronous Request Fix in data/fetcher.py  ·L17
- # NEW: Use async price fetching  ·L22
- # In async contexts:  ·L25
- ## Task 2: Telegram Button Timeout Fix  ·L31
- ### Solution: Global CallbackQueryHandler  ·L35
- # Add after other handlers in run_bot()  ·L41
- ## Task 3: Invalid TP Structure Fix  ·L50

## FIX_INTEGRATION_GUIDE.py
- async def async_get_candles(asset, timeframe):  ·L17
- def validate_signal_for_ml_pipeline(signal):  ·L73
- async def check_duplicate_before_signal(asset, timeframe, direction):  ·L93
- async def process_signals_deduplicated(signals):  ·L114
- async def _fetch_live_price(symbol: str) -> Optional[float]:  ·L131

## FIX_MFE_MAE_COLUMNS.sql
- -- =====================================================

## fix_ml_column.py
- async def add_ml_probability_column():  ·L12

## FIX_ML_DRIFT_COMPLETE.sql
- -- Complete ML Drift Fix - Lower thresholds to allow 56% predictions through

## FIX_ML_DRIFT_THRESHOLD.sql
- -- Fix ML Drift: Lower the ML probability threshold to allow drifted model predictions through

## fix_ml_drift.py
- def fix_ml_threshold():  ·L16
- def get_clean_asset_list():  ·L30
- def check_shadow_predictions():  ·L47
- async def _check():  ·L55
- def main():  ·L71

## fix_outcomes_constraint.sql
- -- Fix: Add unique constraint to outcomes table to ensure each signal has only one outcome

## FIX_PLAN.md
- # SignalRankAI - Golden Loop Stabilization & Performance Fixes  ·L1
- ## Executive Summary  ·L3
- ## Issues Identified  ·L6
- ### 1. Macro Data API Rate Limits (HTTP 429)  ·L8
- ### 2. The "Over-Trading" Bug (Duplicate Trades)  ·L19
- ### 3. aiohttp Memory Leak (Unclosed Client Sessions)  ·L30
- ### 4. Missing created_at Column  ·L41
- ### 5. Database Connection Pooling (NullPool Issue)  ·L48
- ### 6. Graceful Shutdown  ·L57
- ## Implementation Plan  ·L68

## fix_require_tier.py
- #!/usr/bin/env python3

## fix_require_tier2.py
- #!/usr/bin/env python3

## fix_threshold.py
- #!/usr/bin/env python3

## FIX_THRESHOLDS_SQL.sql
- -- Fix ML threshold to allow 82.43 scores to pass through

## fix2.py
- #!/usr/bin/env python3

## fix3.py
- def get_threshold(self) -> float:  ·L10
- async def analyze_and_adjust(self, force: bool = False):  ·L13
- def get_config(self):  ·L16
- def get_threshold(self) -> float:  ·L28
- async def analyze_and_adjust(self, force: bool = False):  ·L31
- def get_config(self):  ·L34

## IMPLEMENTATION_PLAN.md
- # SignalRankAI Implementation Plan  ·L1
- ## Executive Summary  ·L3
- ## MANDATORY COMPREHENSION PHASE - COMPLETED  ·L11
- ### 1. Folder Structure Analysis ✅  ·L13
- ### 2. File Inventory ✅  ·L23
- ### 3. Function Inventory ✅  ·L28
- ### 4. Class Inventory ✅  ·L33
- ### 5. Dependency Graph ✅  ·L39
- ## IMPLEMENTATION TODO LIST  ·L46
- ### Phase 1: Critical Reliability Fixes  ·L48

## main.py
- def _infer_run_mode() -> str:  ·L12
- def _check_database_configured() -> bool:  ·L40
- def main() -> None:  ·L58

## manual_migration_0010.sql
- -- Manual Migration SQL for 0010_referral_enhancements

## manual_migration_0011_ml_probability.sql
- -- Manual SQL migration: Add ml_probability column to signals table

## manual_migration_0014_decision_log_and_ml_rejected.sql
- -- Manual migration: decision_log + ml_rejected_signals + missing columns

## ML_FIX_CHECKLIST.md
- # ✅ ML Performance Fix - Implementation Checklist  ·L1
- ## Code Status: COMPLETE ✅  ·L3
- ## Step 1: Run SQL on Railway PostgreSQL Console  ·L13
- ## Step 2: Update .env Configuration  ·L30
- # Optional: comment out or reduce Polygon usage  ·L38
- # POLYGON_API_KEY=${POLYGON_API_KEY}  # Only 5/min, use as last resort  ·L39
- ## Step 3: Restart Railway Services  ·L44
- ## Step 4: Verify in Railway Logs  ·L53
- ## Expected Results After Fix  ·L67
- ## Troubleshooting If Issues Persist  ·L76

## ML_SHADOW_FIX_PLAN.md
- # ML Shadow Tracker Fix Plan  ·L1
- ## Problem Analysis  ·L3
- ## Current Implementation Issues  ·L7
- ### 1. ml_rejected_signals - Issues Identified:  ·L9
- ### 2. ml_shadow_predictions - Issues Identified:  ·L28
- ## Implementation Plan  ·L37
- ### Step 1: Fix ml_rejected_signals population in engine/core.py  ·L39
- ### Step 2: Ensure ml_shadow_predictions is populated at rejection time  ·L46
- ### Step 3: Fix the shadow_outcome_worker.py to properly track all rejected signals  ·L52
- ## Required Changes  ·L59

## ml/drift_monitor.py
- def _safe_float(v: Any, d: float = 0.0) -> float:  ·L6
- def psi(expected: list[float], actual: list[float], bins: int = 10) -> float:  ·L13
- def _bucket(arr: list[float]) -> list[float]:  ·L24
- def detect_feature_drift(  ·L41

## ml/features.py
- def timeframe_to_int(tf):  ·L4
- def strategy_to_int(name):  ·L8
- def regime_to_int(regime):  ·L12
- def _safe_float(v, default=0.0):  ·L17
- def _pct_change(closes, n):  ·L24
- def _atr(highs, lows, closes, period=14):  ·L37
- def _mtf_trend(market_data, tf: str) -> float:  ·L53
- def _asset_class_to_int(asset: str) -> int:  ·L74
- def extract_features(signal, market_data):  ·L84

## ml/gen_model.py
- #!/usr/bin/env python

## ml/inference.py
- def _resolve_model_path() -> str:  ·L27
- def _env_bool(name: str, default: bool = False) -> bool:  ·L46
- def _ml_enabled() -> bool:  ·L53
- def _runtime_state_model_payload() -> dict | None:  ·L65
- class MLFilter:  ·L98
- def __init__(self):  ·L99
- def _apply_calibration(self, probability: float) -> float:  ·L168
- def ml_filter(self, features, threshold: float | None = None):  ·L178

## ml/ml_drift.json
- {

## ml/model_manifest.json
- {

## ml/model_registry.py
- class ModelEntry:  ·L11
- class ModelRegistry:  ·L20
- def _sha256_file(path: Path) -> str:  ·L26
- def load_registry(manifest_path: str | Path) -> ModelRegistry:  ·L37
- def compute_model_hash_from_b64(model_bytes_b64: str) -> str:  ·L80
- def validate_payload(payload: Dict[str, Any]) -> tuple[bool, str | None]:  ·L85
- def load_payload(path: Path) -> Dict[str, Any]:  ·L97
- def extract_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:  ·L103
- def verify_artifact_integrity(payload: Dict[str, Any]) -> tuple[bool, str | None]:  ·L112
- def load_model_with_metadata(path: Path, xgb_module: Any) -> tuple[Any, List[str], Dict[str, Any], str | None]:  ·L125

## ml/model.json
- {

## ml/optuna_tuner.py
- def tune_xgboost_params(train_func, n_trials: int = 50) -> dict[str, Any]:  ·L6
- def objective(trial):  ·L13

## ml/retrain.py
- async def collect_training_data() -> list:  ·L31
- async def retrain_model() -> bool:  ·L128

## ml/schema_version.py
- def get_current_schema_version() -> int:  ·L33
- def get_feature_columns() -> list[str]:  ·L37
- def normalize_feature_columns(cols: Any) -> list[str]:  ·L41
- def normalize_model_payload(payload: dict[str, Any]) -> dict[str, Any]:  ·L55
- def migrate_feature_payload(  ·L71

## ml/scorer.py
- def score_signal(probe: Dict[str, Any]) -> float | None:  ·L17

## ml/train_model.py
- def _env_bool(name: str, default: bool = False) -> bool:  ·L30
- def _safe_float(val):  ·L37
- def _generate_offline_bootstrap_data(num_samples: int = 1200) -> pd.DataFrame:  ·L64
- async def load_training_data(lookback_days: int = 90):  ·L214
- def _parse_tp(raw_tp):  ·L222
- async def _load_candles(symbol: str, timeframe: str, created_at: datetime, limit: int = 80):  ·L248
- def _atr(highs, lows, closes, period=14):  ·L268
- def _pct(closes, n):  ·L280
- def _trend_from_closes(closes):  ·L289
- def engineer_features(df):  ·L721

## nixpacks.toml
- # ──────────────────────────────────────────────────────────────────────────────

## parse_diagnostics.py
- def parse_heatmap_log(file_path: str = ".diagnostics/heatmap_log.jsonl"):  ·L12

## payments/models.py
- class Subscription:  ·L3
- def __init__(self, user_id, tier, expires_at):  ·L4
- def is_active(self):  ·L9

## payments/paystack.py
- def verify_signature(payload, signature):  ·L10
- def handle_webhook(request):  ·L18
- async def process_event(event):  ·L26
- def escape_md(text):  ·L85
- async def verify_payment(reference: str, amount_paid: float) -> bool:  ·L107

## payments/subscriptions.py
- """DEPRECATED: SQLite subscription storage removed.

## paystack/paystack.py
- def verify_payment(reference, user_id):  ·L38
- def match_amount_to_tier(amount) -> str | None:  ·L113
- def verify_webhook_signature(request_body, signature) -> bool:  ·L120
- def generate_paystack_link(  ·L128

## Procfile
- web: python main.py

## pytest.ini
- [pytest]

## QUICK_START.md
- # SignalRankAI - Quick Start Guide  ·L1
- ## 📋 Pre-Deployment Checklist  ·L3
- ### 1. ✅ Core Requirements  ·L7
- ### 2. ✅ API Keys (Free Tier Available)  ·L18
- ### 3. ✅ Database Schema  ·L24
- ### 4. ✅ System Configuration  ·L29
- ### 5. ✅ Verify Functionality  ·L35
- ## 🚀 Local Development Start  ·L53
- ### 1. Setup Environment  ·L55
- # Clone repository  ·L57

## railway_main.py
- def _resolve_redis_url() -> str:  ·L50
- def _percentile(values: Iterable[float], percentile: float) -> float | None:  ·L117
- def _emit_slo_alert(kind: str, message: str) -> None:  ·L131
- def _record_dispatch_latency(update_id: str, started_at: float | None) -> None:  ·L136
- def _extract_chat_id(payload: dict | None) -> int:  ·L144
- def _redis_queue_requested() -> bool:  ·L153
- def _log_task_failure(task: asyncio.Task, task_name: str) -> None:  ·L157
- async def _sample_outcome_latency_p95_seconds(hours: int = 24, limit: int = 500) -> float | None:  ·L174
- async def _safe_get_webhook_info() -> dict | None:  ·L211
- def _app_has_registered_handlers(app_obj: object) -> bool:  ·L230

## railway.json
- {

## README.md
- # SignalRankAI  ·L1
- ## Railway monolith production notes  ·L3
- ### Migrations  ·L5
- ### Monolith tuning defaults  ·L10
- ### DB hardening defaults (balanced mode)  ·L17
- ## Backtest and orderbook snapshot formats  ·L24
- ### Candle data  ·L26
- ### Tick data  ·L30
- ### Orderbook data  ·L34
- ### WFO CLI auto-detection  ·L46

## REPOSITORY_ANALYSIS.md
- # SignalRankAI Repository Analysis  ·L1
- ## MANDATORY REPOSITORY COMPREHENSION PHASE  ·L3
- ### 1. Folder Structure Analysis  ·L5
- ### 2. File Inventory Summary  ·L19
- ### 3. Key Integration Paths  ·L60
- ### 4. Identified Issues  ·L67
- ### 5. Dependency Graph  ·L94
- ## SIGNAL LIFECYCLE VALIDATION  ·L122
- ### Stage-by-Stage Flow  ·L124
- ## IMPLEMENTATION PLAN  ·L166

## requirements.txt
- python-telegram-bot>=21.0,<22

## run_ml_shadow_diagnostic.py
- async def run_diagnostic() -> None:  ·L29
- async def main() -> None:  ·L160

## run_server.py
- #!/usr/bin/env python

## scripts/ai_reviewer.py
- async def _fetch_completed_trades(limit: int = 200) -> List[Dict[str, Any]]:  ·L17
- async def _fetch_recent_logs(limit: int = 200) -> List[Dict[str, Any]]:  ·L42
- async def run_ai_review_audit() -> Dict[str, Any]:  ·L64
- async def main() -> None:  ·L94

## scripts/env_scan.py
- def collect_env_vars(root: Path):  ·L5

## scripts/gen_changelog.py
- def main() -> int:  ·L12

## scripts/gen_env_index.py
- def _read_env_example_vars() -> set[str]:  ·L18
- def _settings_fields() -> list[tuple[str, str, str]]:  ·L32
- def _scan_usage(var_name: str) -> str:  ·L45
- def generate() -> tuple[str, list[str]]:  ·L63
- def main() -> int:  ·L90

## scripts/generate_railway_prefill_sheet.py
- class VarSpec:  ·L15
- def _parse_env_file(path: Path) -> dict[str, str]:  ·L51
- def _mask_value(key: str, value: str) -> str:  ·L66
- def _present(value: str | None) -> bool:  ·L79
- def _resolve_value(env_file_values: dict[str, str], key: str) -> tuple[str, str]:  ·L83
- def main() -> int:  ·L93

## scripts/post_deploy_smoke.py
- class CheckResult:  ·L14
- def _derive_base_url(cli_base: str | None) -> str:  ·L22
- def _http_json(  ·L34
- def _check_health(base: str) -> CheckResult:  ·L69
- def _check_ready(base: str) -> CheckResult:  ·L78
- def _check_broker_permission_policy(base: str) -> CheckResult:  ·L87
- def _check_webhook_enqueue(base: str) -> CheckResult:  ·L105
- def main() -> int:  ·L119

## scripts/purge_excluded_signals.py
- async def purge_signals():  ·L10

## scripts/run_engine_brief.py
- def _run():  ·L17

## scripts/test_run_sync.py
- async def t():  ·L5

## scripts/wfo_run.py
- def _infer_asset_timeframe(stem: str) -> tuple[Optional[str], Optional[str]]:  ·L35
- def _maybe_json(value: Any) -> Any:  ·L42
- def _normalize_levels(value: Any) -> list[list[float]]:  ·L53
- def normalize_orderbook_frame(df: pd.DataFrame) -> pd.DataFrame:  ·L70
- def _row_levels(row, price_cols, size_cols):  ·L100
- def is_orderbook_frame(df: pd.DataFrame, path: Path | None = None) -> bool:  ·L121
- def is_tick_frame(df: pd.DataFrame, path: Path | None = None) -> bool:  ·L134
- def load_dataset_file(path: Path) -> pd.DataFrame:  ·L145
- def convert_orderbook_file(input_path: Path, output_path: Path) -> Path:  ·L159
- def discover_inputs(input_dir: Path):  ·L167

## services/__init__.py
- """services/__init__.py"""

## services/asset_mapper.py
- def classify_asset(symbol: str) -> str:  ·L204
- def map_symbol(symbol: str, provider: str) -> Optional[str]:  ·L220
- def get_all_providers_for_asset(symbol: str) -> Dict[str, Optional[str]]:  ·L270

## services/automated_analyst.py
- async def run_automated_audit(cycle_no: int, strict_candidates_count: int, final_signals_count: int) -> dict[str, Any]:  ·L14

## services/economic_calendar.py
- async def _fetch_finnhub(from_dt: datetime, to_dt: datetime) -> list[dict]:  ·L69
- async def fetch_economic_events(force_refresh: bool = False) -> list[dict]:  ·L117
- async def is_no_trade_zone(  ·L157
- async def get_macro_news_context(now: Optional[datetime] = None) -> dict[str, object]:  ·L201
- def is_no_trade_zone_sync(  ·L249
- async def get_upcoming_events_summary(hours_ahead: int = 24) -> str:  ·L271

## services/gemini_ml.py
- async def _fetch_news_sentiment(asset: str):  ·L54
- async def fetch_news_headlines(asset: str, limit: int = 5) -> List[Dict[str, Any]]:  ·L57
- async def get_news_sentiment(asset: str, headlines: list) -> str:  ·L61
- async def gemini_confluence_check_with_tech_context(  ·L115
- async def gemini_confluence_check(  ·L199
- async def gemini_risk_review(  ·L316
- async def run_gemini_review_pipeline(trigger: str, scope: str = "weekly") -> Dict[str, Any]:  ·L392
- async def quick_approve(signal: Dict[str, Any]) -> bool:  ·L570
- async def gemini_final_veto(signal_data: dict, market_context: str) -> bool:  ·L580
- async def test():  ·L675

## services/mt5_client.py
- def _client_base(account_id: str | None = None) -> str:  ·L34
- def _provisioning_base() -> str:  ·L42
- def _headers() -> Dict[str, str]:  ·L48
- def _slippage_tolerance() -> float:  ·L57
- def _check_token() -> bool:  ·L64
- async def _http_get(url: str, params: Dict | None = None) -> Optional[Dict]:  ·L75
- async def _http_post(url: str, payload: Dict) -> Optional[Dict]:  ·L97
- async def _http_put(url: str, payload: Dict) -> bool:  ·L122
- async def _deploy_account(account_id: str) -> None:  ·L144
- async def get_live_price(account_id: str, symbol: str) -> Optional[float]:  ·L157

## services/security.py
- def _get_fernet() -> Optional["Fernet"]:  ·L31
- def encrypt_secret(plaintext: str) -> Optional[str]:  ·L47
- def decrypt_secret(ciphertext: str) -> Optional[str]:  ·L64
- def is_encryption_available() -> bool:  ·L83

## SET_THRESHOLDS_FIX.py
- def main():  ·L16

## SIGNAL_BLOCKAGE_DIAGNOSIS.md
- # Signal Generation Blockage: Root Cause Analysis & Fixes  ·L1
- ## Problem Summary  ·L3
- ## Root Cause: Multiple Final Gate Rejections  ·L10
- ### Gate 1: TP/SL Structure Validation (CRITICAL)  ·L14
- # Patch to engine/core.py at line 1706 (before invalid_tp_structure check)  ·L29
- ### Gate 2: Advanced Filters Structure Check (HIGH PRIORITY)  ·L34
- ### Gate 3: Score Threshold Gate (CONFIRMED ISSUE)  ·L54
- ### Gate 4: Expectancy Hard Block (OPTIONAL)  ·L72
- ### Gate 5: Gemini LLM Review (OPTIONAL BUT LIKELY)  ·L83
- ## Immediate Action Plan (Temporary Diagnostic Mode)  ·L94

## signalrank_discord/__init__.py
- """Discord dispatch channel for SignalRankAI."""

## signalrank_discord/webhook_dispatcher.py
- def dispatch_signal_webhook(text: str, tier: str = "premium") -> bool:  ·L7

## signalrank_telegram/__init__.py
- # This file marks the signalrank_telegram directory as a Python package.

## signalrank_telegram/.gitkeep
- (empty)

## signalrank_telegram/access.py
- def _tier_cache_key(user_id: int) -> str:  ·L15
- def _tier_cache_ttl_seconds() -> int:  ·L19
- def resolve_user_tier(user_id):  ·L25

## signalrank_telegram/account_commands.py
- async def performance_command(update, context):  ·L11
- async def history_command(update, context):  ·L83
- async def apikey_command(update, context) -> None:  ·L169
- async def _rotate_api_token_for_user(user_id: int, ttl_days: int = 30) -> str:  ·L180
- async def _get_existing_api_token_meta(user_id: int):  ·L197

## signalrank_telegram/admin_commands.py
- def _effective_tier(user_id: int) -> str:  ·L19
- def _is_admin(user_id) -> bool:  ·L33
- async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L61
- async def force_market_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L95
- async def admin_top_assets_command(update, context) -> None:  ·L168
- async def admin_top_strategies_command(update, context) -> None:  ·L186
- async def admin_user_engagement_command(update, context) -> None:  ·L217
- async def selfcheck_command(update, context) -> None:  ·L231
- async def ops_health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L297

## signalrank_telegram/bot.py
- def resend_unsent_signals_job():  ·L7
- async def _resend_unsent_signals_async():  ·L66
- def _audit_handler(command_name: str, handler):  ·L396
- async def _inner(update, context):  ·L397
- class _DummyApp:  ·L478
- def add_handler(self, *a, **k):  ·L479
- def run(self, *a, **k):  ·L482
- def _log_once(key: str, message: str) -> None:  ·L611
- def _mask_db_url_host(url: str) -> str:  ·L622
- def _normalized_delivery_tier(tier: str | None) -> str:  ·L641

## signalrank_telegram/callback_handlers.py
- def _parse_callback_data(data: str) -> Dict[str, Any]:  ·L64
- async def _handle_mt5_trade(update: Update, context: ContextTypes.DEFAULT_TYPE, signal_id: str) -> None:  ·L88
- async def _handle_signal_reaction(  ·L132
- async def _handle_monitor_signal(  ·L209
- async def _handle_check_outcome(  ·L247
- async def _handle_default_callback(  ·L287
- async def _global_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L304
- def create_global_callback_handler() -> CallbackQueryHandler:  ·L367

## signalrank_telegram/command_access.py
- def _normalize_command_name(command: str) -> str:  ·L380
- def _help_tier_bucket(required_tier: str) -> str:  ·L384
- def sync_command_help() -> None:  ·L393
- def get_accessible_commands(tier: str) -> list[tuple[str, str]]:  ·L425
- def get_help_message(tier: str) -> str:  ·L441
- def _he(text: str) -> str:  ·L468
- def check_command_access(command: str, user_tier: str) -> tuple[bool, str]:  ·L545
- def tier_rank(tier: str) -> int:  ·L581

## signalrank_telegram/commands.py
- def _railway_env_hint(feature: str, missing: list[str]) -> str:  ·L37
- def require_tier(min_tier):  ·L49
- def wrapper(func):  ·L50
- async def inner(update, context):  ·L51
- def _chart_symbol_for_broker(signal: dict | None = None) -> tuple[str, str]:  ·L94
- def _build_dynamic_menu(user_id: int, tier: str):  ·L160
- def _build_signal_action_keyboard(signal: dict | None = None):  ·L194
- async def _get_live_vip_seat_state() -> tuple[int, int, bool]:  ·L227
- def _vip_plan_line(*, MarkdownV2: bool, seats_left: int, sold_out: bool) -> str:  ·L241
- async def _build_plan_keyboard(user_id: int, *, include_navigation: bool) -> object | None:  ·L249

## signalrank_telegram/feedback.py
- class FeedbackStore:  ·L11
- def __init__(self):  ·L12
- def add_feedback(self, user_id, signal_id, rating=None, issue=None, comment=None):  ·L17
- def get_feedback(self, signal_id=None):  ·L29
- def flush(self):  ·L35
- async def _write() -> None:  ·L49

## signalrank_telegram/formatter.py
- def _get_user_tier(user_tier: str | None) -> str:  ·L23
- def _should_send_signal_for_tier(user_tier: str, score: float) -> bool:  ·L36
- def _risk_suggestion(score: float | int | None) -> str:  ·L45
- def _confidence_tag(score: float | int | None) -> str:  ·L68
- def _confluence_display(confluence_count: int | None, confluence_total: int | None) -> str:  ·L89
- def _format_expiration(expires_at) -> str:  ·L102
- def _risk_guidance(tier: str, score: float | int | None) -> str:  ·L140
- def _star_rating(confluence_count: int | None, score: float | int | None) -> str:  ·L166
- def format_signal_free(signal) -> str:  ·L193
- def format_signal_premium(signal) -> str:  ·L223

## signalrank_telegram/free_signal_jobs.py
- def distribute_random_signals_to_free_users_job():  ·L18
- async def _do_distribute():  ·L33
- def free_distribution_job():  ·L50

## signalrank_telegram/httpx_config.py
- import httpx

## signalrank_telegram/mt5_commands.py
- async def mt5_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L4
- async def mt5_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L83

## signalrank_telegram/owner_commands.py
- async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L6
- async def add_vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L38
- async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L57
- async def pause_signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L76
- def _owner_id() -> int:  ·L95
- def _strict_owner_ids() -> set[int]:  ·L102
- def _bypass_key() -> Optional[str]:  ·L127
- async def _is_owner(user_id: int) -> bool:  ·L135
- async def _is_admin_or_owner(user_id: int) -> bool:  ·L150
- async def _is_strict_owner(user_id: int) -> bool:  ·L167

## signalrank_telegram/payment_handler.py
- async def verify_payment_and_upgrade_tier(  ·L8
- async def check_pending_payments(user_id: int) -> Optional[Dict]:  ·L85
- async def format_tier_upgrade_confirmation(  ·L104

## signalrank_telegram/rate_limit.py
- def rate_limited(user_id):  ·L7

## signalrank_telegram/signal_commands.py
- async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L23
- async def _filter_unvoted(signals_in: list[dict]) -> list[dict]:  ·L62
- async def proof_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L211

## signalrank_telegram/signal_distribution.py
- class SignalDistributor:  ·L42
- def __init__(self, session: Session):  ·L52
- def get_eligible_users_for_tier(  ·L55
- def count_delivered_signals_today(  ·L97
- def can_receive_signal(  ·L131
- def sample_users_for_signal(  ·L168
- def record_delivery_attempt(  ·L231
- def get_delivery_status(  ·L276
- def create_distributor(session: Session) -> SignalDistributor:  ·L299

## signalrank_telegram/tier_delivery.py
- class TierDeliveryManager:  ·L22
- def __init__(self):  ·L39
- def should_send_signal(self, user_tier: str, score: float, user_id: Optional[str | int] = None, session=None) -> bool:  ·L42
- async def should_send_signal_async(self, user_tier: str, score: float, user_id: Optional[str | int] = None, session=None) -> bool:  ·L62
- def format_for_delivery(self, signal: Dict, user_tier: str) -> Optional[str]:  ·L78
- def get_users_for_signal(self, signal: Dict, signal_id: str, session=None) -> Dict[str, List[int]]:  ·L96
- def create_update_alert(self, signal: Dict, tp_number: int, user_tier: str) -> Optional[str]:  ·L126
- def create_no_trade_alert(self, user_tier: str) -> Optional[str]:  ·L143
- def get_tier_features(self, tier: str) -> Dict:  ·L158
- def get_max_tp_level_for_tier(self, tier: str) -> int:  ·L234

## signalrank_telegram/tier_gated_formatter.py
- def _parse_tp_levels(tp_raw: Any) -> List[float]:  ·L35
- def _fmt_price_clean(price: Any, asset: str = "") -> str:  ·L67
- def format_tiered_signal(signal: Dict[str, Any], user_tier: str) -> Tuple[str, Optional[InlineKeyboardMarkup]]:  ·L89
- def should_user_receive_signal(signal_score: float, user_tier: str) -> bool:  ·L193
- def get_paywall_upsell_message() -> str:  ·L222
- def demo_format():  ·L241

## signalrank_telegram/tier_signal_formatter.py
- def _h(text: str) -> str:  ·L24
- def _asset_display(asset: str) -> str:  ·L59
- def _direction_display(direction: str) -> str:  ·L65
- def _volatility_label(signal: DictType[str, Any]) -> str:  ·L71
- def _order_block_text(signal: DictType[str, Any]) -> Optional[str]:  ·L92
- def _fmt_price_clean(price: Any, asset: str = "") -> str:  ·L103
- def _parse_tp_levels(tp_raw: Any) -> List[float]:  ·L125
- def _build_tp_fallbacks(  ·L156
- def _safe_float(value: Any) -> Optional[float]:  ·L228
- def _compute_rr(entry: Any, stop_loss: Any, take_profit: Any) -> Optional[float]:  ·L235

## signalrank_telegram/user_commands.py
- async def start_command(update, context):  ·L7
- async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L50
- async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L66
- async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L70
- async def about_command(update, context) -> None:  ·L77
- async def faq_command(update, context) -> None:  ·L101
- async def disclaimer_command(update, context) -> None:  ·L124
- async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L139

## signalrank_telegram/user_prefs.py
- class UserPrefsStore:  ·L9
- def __init__(self):  ·L10
- def set_prefs(self, user_id, assets=None, timeframes=None, strategies=None):  ·L14
- def get_prefs(self, user_id):  ·L23
- def clear_prefs(self, user_id):  ·L27

## signalrank_telegram/utils.py
- async def _public_guard(update) -> bool:  ·L24
- def _effective_tier(user_id: int) -> str:  ·L56
- def tier_rank(tier: str) -> int:  ·L72
- def require_tier(min_tier: str):  ·L77
- def decorator(func):  ·L81
- async def wrapper(update, context):  ·L82
- def _build_dynamic_menu(user_id: int, tier: str) -> Optional[InlineKeyboardMarkup]:  ·L102
- def _build_signal_action_keyboard(signal: Optional[Dict[str, Any]] = None) -> Optional[InlineKeyboardMarkup]:  ·L145
- def _chart_symbol_for_broker(signal: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:  ·L170
- def sanitize_input(text: str, max_len: int = 1000) -> str:  ·L193

## start.sh
- #!/bin/bash

## storage/.gitkeep
- (empty)

## storage/db.py
- # Placeholder for DB connection logic

## storage/schema.sql
- -- Example schema for subscriptions

## strategies/__init__.py
- def _env_bool(name: str, default: bool) -> bool:  ·L7
- def run_all_strategies(asset, market_data, regime, strategy_weights=None, regime_strategies=None):  ·L43
- def get_htf_bias(market_data):  ·L47
- def _add(sig):  ·L124

## strategies/base.py
- class BaseStrategy:  ·L1
- def evaluate(self, market_data):  ·L4

## strategies/commodity.py
- def best_commodity_strategies(asset, market_data, regime):  ·L5

## strategies/crypto.py
- def best_crypto_strategies(asset, market_data, regime):  ·L5

## strategies/dynamic_targets.py
- class DynamicTargets:  ·L15
- def calculate_dynamic_targets(  ·L22
- def get_tp_ladders_for_tier(targets: DynamicTargets, tier: str) -> List[float]:  ·L118
- def enhance_signal_targets(signal: Dict) -> Dict:  ·L128

## strategies/fallback.py
- def fallback_strategies(asset, timeframe, market_data):  ·L18
- class SimplePriceActionStrategy(BaseStrategy):  ·L58
- def evaluate(self, market_data):  ·L65
- class SimpleVolumeConfirmationStrategy(BaseStrategy):  ·L132
- def evaluate(self, market_data):  ·L139
- class SimpleTrendContinuationStrategy(BaseStrategy):  ·L208
- def evaluate(self, market_data):  ·L215
- class SimpleRangeBreakStrategy(BaseStrategy):  ·L285
- def evaluate(self, market_data):  ·L292

## strategies/fibonacci_confluence.py
- class _FibConfig:  ·L15
- def _to_arrays(candles: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:  ·L23
- def _ema(values: np.ndarray, period: int) -> float:  ·L32
- def _rsi_series(closes: np.ndarray, period: int = 14) -> np.ndarray:  ·L42
- def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:  ·L55
- def _pivot_mask(values: np.ndarray, window: int = 2, mode: str = "low") -> np.ndarray:  ·L64
- def _last_two_indices(mask: np.ndarray) -> list[int]:  ·L81
- def _nearest_zone(price: float, level: float, atr: float, is_long: bool) -> bool:  ·L88
- def _bias_from_htf(market_data: dict[str, Any]) -> tuple[str | None, float, float]:  ·L93
- def _find_exec_tf(market_data: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:  ·L114

## strategies/fibonacci_helpers.py
- def is_price_in_golden_pocket(price: float, swing_high: float, swing_low: float, tol_pct: float = 0.0001) -> bool:  ·L4

## strategies/fx.py
- def best_fx_strategies(asset, market_data, regime):  ·L5

## strategies/imp.py
- def _env_bool(name: str, default: bool) -> bool:  ·L8
- def _safe_float(value: Any, default: float = 0.0) -> float:  ·L16
- def _is_fx(symbol: str) -> bool:  ·L23
- def _is_crypto(symbol: str) -> bool:  ·L28
- def _is_commodity(symbol: str) -> bool:  ·L33
- def _is_stock(symbol: str) -> bool:  ·L38
- def _utc_hour_now() -> int:  ·L42
- def _is_london_ny_overlap() -> bool:  ·L46
- def _is_london_session() -> bool:  ·L51
- def _is_new_york_session() -> bool:  ·L56

## strategies/liquidity_sweep.py
- class _SweepConfig:  ·L14
- def _env_bool(name: str, default: bool = False) -> bool:  ·L22
- def _is_fx(symbol: str) -> bool:  ·L31
- def _is_crypto(symbol: str) -> bool:  ·L36
- def _is_commodity(symbol: str) -> bool:  ·L41
- def _session_allowed_for_fx() -> bool:  ·L46
- def _to_arrays(candles: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:  ·L61
- def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:  ·L70
- def _select_htf_candles(market_data: dict[str, Any]) -> list[dict[str, Any]]:  ·L79
- def _select_exec_timeframe(market_data: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:  ·L89

## strategies/momentum.py
- def momentum_strategies(asset, timeframe, market_data):  ·L5
- class RSIMomentumStrategy(BaseStrategy):  ·L49
- def evaluate(self, market_data):  ·L53
- class MACDMomentumStrategy(BaseStrategy):  ·L123
- def evaluate(self, market_data):  ·L127
- class StochRSIMomentumStrategy(BaseStrategy):  ·L195
- def evaluate(self, market_data):  ·L199

## strategies/stock.py
- def stock_trend_strategy(asset, timeframe, market_data):  ·L1
- def stock_strategies(asset, timeframe, market_data):  ·L36
- def best_stock_strategies(asset, market_data, regime):  ·L52

## strategies/structure.py
- def structure_strategy(asset, timeframe, market_data):  ·L1
- class StructureBiasStrategy(BaseStrategy):  ·L10
- def evaluate(self, market_data):  ·L13
- class SRBreakRetestStrategy(BaseStrategy):  ·L47
- def evaluate(self, market_data):  ·L49
- class LiquiditySweepStrategy(BaseStrategy):  ·L81
- def evaluate(self, market_data):  ·L83
- def structure_strategy(asset, timeframe, market_data):  ·L115

## strategies/tradingview.py
- def _env_bool(name: str, default: bool = False) -> bool:  ·L28
- def _env_float(name: str, default: float) -> float:  ·L36
- def _respect_global_cooldown():  ·L44
- def _env_int(name: str, default: int) -> int:  ·L55
- def get_tradingview_signals(asset: str, timeframe: str) -> list[dict]:  ·L63
- def _create_signal(direction: str, asset: str, timeframe: str, confidence: float,  ·L277
- def tradingview_strategies(asset: str, timeframe: str, market_data: dict) -> list[dict]:  ·L375

## strategies/trend.py
- class EMATrendStrategy(BaseStrategy):  ·L5
- def evaluate(self, market_data):  ·L7
- class SupertrendStrategy(BaseStrategy):  ·L66
- def evaluate(self, market_data):  ·L68
- class ADXTrendStrategy(BaseStrategy):  ·L124
- def evaluate(self, market_data):  ·L126
- def trend_strategies(asset, timeframe, market_data):  ·L184

## strategies/volatility.py
- def volatility_strategies(asset, timeframe, market_data):  ·L1
- class ATRBreakoutStrategy(BaseStrategy):  ·L10
- def evaluate(self, market_data):  ·L12
- class BBWidthVolatilityStrategy(BaseStrategy):  ·L29
- def evaluate(self, market_data):  ·L31
- class KeltnerVolatilityStrategy(BaseStrategy):  ·L48
- def evaluate(self, market_data):  ·L50
- def volatility_strategies(asset, timeframe, market_data):  ·L67

## TABLE_ACTIVATION_FIX_PLAN.md
- # SignalRankAI Table Activation Fix Plan - IMPLEMENTATION  ·L1
- ## Status Summary  ·L3
- ### ✅ ALREADY WORKING  ·L5
- ### ❌ NEEDS IMPLEMENTATION (Critical First)  ·L16
- ## IMPLEMENTATION: Step 1 - CRITICAL  ·L34
- ### 1.1 Add free_signal_queue Distribution Job  ·L36
- ### 1.2 Add User Commands (for mt5_credentials, api_tokens, user_webhooks)  ·L54
- ### 1.3 Add Managed Assets Seeding  ·L62
- ## CURRENT IMPLEMENTATION STATUS  ·L69
- ### ✅ IN PROGRESS  ·L71

## TABLE_ACTIVATION_IMPLEMENTATION_PLAN.md
- # SignalRankAI Implementation Plan: Missing Features  ·L1
- ## Executive Summary  ·L3
- ## Priority Implementation Plan  ·L26
- ### STEP 1 (CRITICAL): Add Free Signal Queue Distribution Job  ·L28
- # In the BackgroundScheduler setup section, add:  ·L76
- ### STEP 2: Add Missing Telegram Commands  ·L88
- ### STEP 3: Add Missing Scheduled Jobs  ·L236
- ## File Modification Summary  ·L337
- ## Testing Checklist  ·L349
- ## Implementation Notes  ·L360

## TABLE_ACTIVATION_STATUS.md
- # SignalRankAI Table Activation Status Report  ·L1
- ## Executive Summary  ·L3
- ## ✅ FULLY IMPLEMENTED (12/14)  ·L9
- ### 1. free_signal_queue Distribution Job  ·L11
- ### 2. api_tokens (ApiToken)  ·L18
- ### 3. user_webhooks (UserWebhook)  ·L23
- ### 4. mt5_credentials  ·L28
- ### 5. mt5_executions (MT5Execution)  ·L34
- ### 6. trades (Trade)  ·L39
- ### 7. managed_assets (ManagedAsset)  ·L43

## telegram/access.py
- (empty)

## telegram/bot.py
- def main() -> None:  ·L18

## telegram/commands.py
- async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L9
- async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L19
- async def pricing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L33
- async def upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L45
- async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L55
- async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  ·L65
- def public_commands() -> List[BotCommand]:  ·L75

## telegram/formatter.py
- def format_signal(signal):  ·L1

## test_all_features.py
- """

## test_all_functions.py
- class TestAllFunctions(unittest.TestCase):  ·L19
- def test_signal_controller_functions(self):  ·L20
- def test_scoring_functions(self):  ·L36
- def test_risk_functions(self):  ·L47
- def test_regime_function(self):  ·L53
- def test_ranking_function(self):  ·L57
- def test_ml_functions(self):  ·L60
- def test_core_functions(self):  ·L65
- def test_consensus_functions(self):  ·L70
- def test_database_functions(self):  ·L78

## test_asset_routing.py
- def test_asset_type_detection():  ·L8
- def test_ticker_namespacing():  ·L41
- def test_provider_routing():  ·L89
- def test_market_hours():  ·L125
- def test_strict_provider():  ·L147
- def main():  ·L176

## test_core.py
- class TestSignalController(unittest.TestCase):  ·L7
- def setUp(self):  ·L8
- def test_kill_switch(self):  ·L11
- def test_approve_signals_empty(self):  ·L17
- def test_deduplicate_signals(self):  ·L24
- class TestUserTier(unittest.TestCase):  ·L33
- def test_set_and_get_tier(self):  ·L34

## test_diag.py
- #!/usr/bin/env python

## test_exact_healthz.py
- #!/usr/bin/env python

## test_final.py
- #!/usr/bin/env python

## test_freshness_manual.py
- def _utcnow_naive() -> datetime:  ·L23
- def test_freshness_validation():  ·L27

## test_health_http.py
- #!/usr/bin/env python

## test_mount_debug.py
- #!/usr/bin/env python

## test_mounted.py
- #!/usr/bin/env python

## test_near_zero_loss.py
- def test_ultra_quality_filter():  ·L17
- def test_position_sizing():  ·L108
- def test_smart_exits():  ·L153
- def test_trailing_stop():  ·L230
- def test_trade_tracking():  ·L283

## test_scoring_validation.py
- def test_component_scoring():  ·L13
- def test_quality_gates():  ·L31
- def test_winning_signals():  ·L52
- def test_ml_boost():  ·L77
- def test_regime_bonus():  ·L93

## test_startup.py
- #!/usr/bin/env python

## test_tier_formatter.py
- #!/usr/bin/env python3

## test_tier_gated.py
- """Quick test for tier_gated_formatter module."""

## test_tradingview_integration.py
- def test_signals_no_limit():  ·L12
- def test_tradingview_fx_crypto():  ·L41
- def test_strategy_pipeline():  ·L77
- def test_environment_variables():  ·L106
- def test_asset_examples():  ·L134
- def main():  ·L146

## test_uvicorn.py
- #!/usr/bin/env python

## tests/test_access_tier_cache.py
- def test_resolve_user_tier_uses_cache(monkeypatch):  ·L6
- async def fake_resolve_user_tier_pg(user_id: int):  ·L10
- def _cache_set(k, v, ex=None):  ·L22

## tests/test_access.py
- def test_access_control():  ·L1

## tests/test_backtest_wfo.py
- def make_synthetic_df(start: datetime, periods: int, freq: str = '5T') -> pd.DataFrame:  ·L8
- def test_backtest_and_wfo_basic():  ·L22
- def test_wfo_with_dummy_train_callback():  ·L39
- def dummy_trainer(signals, df_map):  ·L46
- def predict(sig):  ·L48

## tests/test_broker_permission_validation.py
- def test_broker_permission_validation_rejects_withdrawal_enabled_key() -> None:  ·L9
- def test_broker_permission_validation_accepts_trade_only_key() -> None:  ·L26
- def test_broker_permission_validation_rejects_transfer_permission_string() -> None:  ·L43

## tests/test_bypass_rotation.py
- def test_unlock_invalidates_when_bypass_key_rotates(monkeypatch):  ·L6

## tests/test_command_contracts.py
- def test_upgrade_message_escapes_markdown_pipe() -> None:  ·L7
- def test_tiers_command_uses_live_pricing_envs() -> None:  ·L13
- def test_buy_extra_signals_removed_from_command_access() -> None:  ·L19

## tests/test_command_tier_contract.py
- class TestTierHelpContract(unittest.TestCase):  ·L7
- def test_help_surface_commands_exist_in_command_tiers(self):  ·L8
- def test_help_required_tier_can_access_all_commands_on_page(self):  ·L15
- def test_hidden_commands_are_not_in_paginated_help_surface(self):  ·L27

## tests/test_connectors_providers.py
- class _DummyResp:  ·L6
- def __init__(self, payload, status=200):  ·L7
- def json(self):  ·L11
- class _DummyClient:  ·L15
- def __init__(self, payload):  ·L16
- async def get(self, *args, **kwargs):  ·L19
- class TestProviderAdapters(unittest.TestCase):  ·L23
- def test_polygon_adapter_parses_results(self):  ·L24
- async def run_test():  ·L27
- async def wrapper(fn, **k):  ·L31

## tests/test_connectors.py
- class TestConnectorsAndValidators(unittest.TestCase):  ·L7
- def test_validate_candles(self):  ·L8
- def test_yfinance_adapter_with_mocked_history(self):  ·L16
- class DummyTicker:  ·L32
- def history(self, period, interval):  ·L33
- def test_binance_adapter_with_mocked_requests(self):  ·L45

## tests/test_container_startup_cmd.py
- def _has_leading_assignment(cmd: str) -> bool:  ·L28
- def test_railway_json_startCommand_not_leading_assignment() -> None:  ·L33
- def test_nixpacks_toml_start_cmd_not_leading_assignment() -> None:  ·L50

## tests/test_dispatch_update_smoke.py
- def test_dispatch_update_smoke_placeholder() -> None:  ·L4

## tests/test_drift_adjustment.py
- def test_drift_confidence_adjustment_reduces_score():  ·L4
- def test_drift_confidence_adjustment_ignored_when_normal():  ·L15

## tests/test_engine_loop.py
- class EngineLoopTests(unittest.IsolatedAsyncioTestCase):  ·L5
- async def test_run_once_collects_signals(self):  ·L6

## tests/test_engine_reconciliation.py
- def test_counts_from_active_trades_uses_live_redis_payloads():  ·L4
- def test_counts_from_active_trades_ignores_bad_payloads():  ·L22

## tests/test_enterprise_features.py
- def _sign_paystack(body: bytes, secret: str) -> str:  ·L35
- def _make_paystack_event(tier: str = "premium", uid: int = 100, ref: str = "REF001",  ·L39
- class TestPaystackWebhookFlow:  ·L59
- def test_missing_signature_returns_400(self):  ·L62
- def test_bad_signature_returns_401(self, monkeypatch: MonkeyPatch):  ·L71
- def test_valid_signature_passes(self, monkeypatch: MonkeyPatch):  ·L81
- def test_missing_secret_returns_500(self, monkeypatch: MonkeyPatch):  ·L92
- class TestPaystackCheckoutLink:  ·L108
- async def test_returns_url_on_success(self, monkeypatch: MonkeyPatch):  ·L112
- async def test_missing_secret_returns_error(self, monkeypatch: MonkeyPatch):  ·L135

## tests/test_expectancy_gate.py
- def good_signal():  ·L12
- def bad_signal():  ·L16
- async def test_get_live_expectancy_good(good_signal):  ·L20
- async def test_get_live_expectancy_bad(bad_signal):  ·L31
- async def test_expectancy_gate_pass(good_signal):  ·L42
- async def test_expectancy_gate_block(bad_signal):  ·L47

## tests/test_fetcher_async.py
- def make_dummy_candles(n=30):  ·L7
- class TestAsyncFetcher(unittest.TestCase):  ·L22
- def test_async_get_candles_success(self):  ·L23
- async def provider(symbol, tf, timeout=10):  ·L24
- async def run_test():  ·L27
- def test_async_get_candles_all_providers_empty(self):  ·L36
- async def provider_empty(symbol, tf, timeout=10):  ·L37
- async def run_test():  ·L40
- def test_async_get_candles_crypto_fallback_chain_binance_403_bybit_timeout_cryptocompare_success(self):  ·L48
- async def binance_403(symbol, tf, timeout=10):  ·L51

## tests/test_fetcher.py
- def make_candles(n=200):  ·L7
- class FetcherTest(unittest.TestCase):  ·L22
- def test_get_candles_crypto_single_provider(self, mock_get_crypto):  ·L24
- def test_get_candles_handles_exception(self, mock_asset_type):  ·L33

## tests/test_fibonacci_helpers.py
- def test_golden_pocket_inside_and_tolerance():  ·L4

## tests/test_help_menu_cache.py
- def test_get_help_message_uses_cache(monkeypatch):  ·L5
- def _cache_set(k, v, ex=None):  ·L13

## tests/test_imp_strategy.py
- def _candle(ts: datetime, o: float, h: float, l: float, c: float, v: float = 1000.0) -> dict:  ·L8
- def _build_h4_uptrend() -> list[dict]:  ·L19
- def _build_h1_imp_long_setup() -> list[dict]:  ·L34
- def test_imp_generates_long_signal_on_valid_setup(monkeypatch):  ·L58
- def test_imp_blocks_fx_outside_overlap(monkeypatch):  ·L89
- def test_imp_allows_london_session_when_configured(monkeypatch):  ·L108

## tests/test_macro_flow.py
- def test_macro_flow_into_extract_features():  ·L4

## tests/test_market_state.py
- class MarketStateTests(unittest.TestCase):  ·L5
- def test_get_market_state_basic(self):  ·L6
- def test_get_market_state_with_ml(self):  ·L34

## tests/test_migration_revision_ids.py
- def test_db_migration_revision_ids_fit_alembic_version_column() -> None:  ·L7

## tests/test_ml_registry.py
- class TestModelRegistry(unittest.TestCase):  ·L7
- def _load_payload(self):  ·L8
- def test_integrity_passes_for_repo_model(self):  ·L13
- def test_integrity_detects_hash_mismatch(self):  ·L21
- def test_load_model_with_metadata(self):  ·L31

## tests/test_ml_schema_evolution.py
- class TestMLSchemaVersioning(unittest.TestCase):  ·L9
- def test_normalize_model_payload_adds_defaults(self):  ·L10
- def test_legacy_model_b64_field_is_supported(self):  ·L18
- def test_migrate_feature_payload_fills_missing_with_zero(self):  ·L24
- def test_inference_reads_schema_version_without_crashing(self):  ·L31

## tests/test_monolith_hardening_defaults.py
- class TestMonolithHardeningDefaults(unittest.TestCase):  ·L7
- def test_signal_dedup_window_is_one_hour(self):  ·L8
- def test_outcome_tracker_default_interval_is_20s(self):  ·L14
- def test_run_startup_ops_auto_migrate_default_is_disabled(self):  ·L21
- def test_db_engine_singleton_per_process(self):  ·L32
- def test_db_pool_defaults_are_hardened(self):  ·L44
- def test_db_pool_is_capped_on_railway(self):  ·L64

## tests/test_news_x_sentiment.py
- class _MockResp:  ·L7
- def __init__(self, ok=True, payload=None):  ·L8
- def json(self):  ·L12
- class TestNewsXSentiment(unittest.TestCase):  ·L16
- def setUp(self):  ·L17
- def test_fetch_news_headlines_uses_x_bearer(self, mock_get):  ·L21
- def test_fetch_news_headlines_without_x_token_skips_x_for_non_crypto(self, mock_get):  ·L46
- def test_x_failure_falls_back_to_cryptocompare(self, mock_get):  ·L55
- def side_effect(url, *args, **kwargs):  ·L56

## tests/test_onchain_providers.py
- def test_onchain_payload_normalization():  ·L5
- def test_fetch_onchain_context_fails_open_without_endpoints():  ·L22
- def test_extract_features_includes_onchain_fields():  ·L29

## tests/test_orderbook_fills.py
- def make_candle_df(start: datetime, periods: int):  ·L8
- def make_orderbook_snapshots(start: datetime):  ·L15
- def test_orderbook_partial_consumption():  ·L27

## tests/test_orderbook_loader.py
- def _levels_to_lists(levels):  ·L8
- def test_normalize_top_of_book_and_convert(tmp_path: Path):  ·L12

## tests/test_outcome_delivery_contract.py
- def test_expire_job_excludes_unresolved_tracked_states() -> None:  ·L7
- def test_outcome_notification_idempotency_wired_in_pg_features() -> None:  ·L14
- def test_realtime_tracker_queues_and_delivers_from_db_state() -> None:  ·L22
- def test_signal_delivery_contract_requires_successful_delivery_rows() -> None:  ·L30

## tests/test_outcome_integration_multi_tp.py
- def test_long_signal_progresses_to_tp3_with_synthetic_candles():  ·L4
- def test_long_signal_hits_sl_after_entry_with_synthetic_candles():  ·L28

## tests/test_payments.py
- def test_payments():  ·L1

## tests/test_paystack_webhook.py
- class TestPaystackWebhook(unittest.IsolatedAsyncioTestCase):  ·L15
- async def asyncSetUp(self):  ·L16
- async def test_rejects_missing_signature(self):  ·L20
- async def test_accepts_valid_signature_payments_disabled(self):  ·L28
- async def test_idempotent_replay_returns_idempotent_flag(self):  ·L47

## tests/test_pipeline.py
- def test_signal_pipeline():  ·L1

## tests/test_price_validator.py
- def _utcnow_naive() -> datetime:  ·L21
- class TestPriceValidator(unittest.TestCase):  ·L25
- def test_get_asset_type(self):  ·L28
- def test_is_signal_fresh_with_fresh_signal(self):  ·L36
- def test_is_signal_fresh_with_stale_signal(self):  ·L47
- def test_is_signal_fresh_with_string_timestamp(self):  ·L58
- def test_is_signal_fresh_without_timestamp(self):  ·L68
- def test_enrich_signal_with_live_price(self, mock_price):  ·L79
- def test_check_sl_tp_hit_long_sl_hit(self):  ·L99
- def test_check_sl_tp_hit_long_tp_hit(self):  ·L112

## tests/test_providers_proxy.py
- def test_binance_ccxt_uses_http_proxy(monkeypatch):  ·L5
- class DummyExchange:  ·L10
- def __init__(self, config):  ·L11
- def fetch_ohlcv(self, *args, **kwargs):  ·L14

## tests/test_proxy_manager.py
- def test_proxy_manager_round_robin_async(monkeypatch):  ·L4
- async def _run():  ·L10

## tests/test_railway_lifecycle.py
- class TestRailwayLifecycle(unittest.IsolatedAsyncioTestCase):  ·L6
- async def test_webhook_route_queues_when_bot_not_ready(self):  ·L7
- class _Req:  ·L14
- async def json(self):  ·L17
- async def test_webhook_route_returns_queue_full(self):  ·L25
- class _Req:  ·L34
- async def json(self):  ·L37
- async def test_build_scheduler_registers_expected_jobs(self):  ·L46
- async def test_stop_telegram_bot_deletes_webhook_when_enabled(self):  ·L55
- def _fake_getenv(key, default=None):  ·L70

## tests/test_railway_monolith_contract.py
- class RailwayMonolithContractTests(unittest.IsolatedAsyncioTestCase):  ·L12
- async def test_health_and_ready_endpoints(self):  ·L13

## tests/test_railway_no_redis.py
- class TestNoRedisRuntimeState(unittest.TestCase):  ·L6
- def test_rate_limit_fallback_works_without_pg_or_redis(self):  ·L7
- def test_killswitch_fallback_memory_roundtrip(self):  ·L18
- class TestRailwayWebhookNoRedis(unittest.IsolatedAsyncioTestCase):  ·L30
- async def test_webhook_queues_updates_while_bot_initializes(self):  ·L31

## tests/test_railway_redis_queue.py
- class TestRailwayRedisQueue:  ·L6
- async def _run(self):  ·L7
- async def _enqueue(payload, max_depth=None):  ·L15
- async def _depth():  ·L18
- def test_telegram_webhook_route_uses_redis_backend(self):  ·L33

## tests/test_ranking_weights.py
- class TestRankingWeights(unittest.TestCase):  ·L8
- def setUp(self):  ·L9
- def test_rank_signals_uses_live_strategy_weight(self):  ·L13

## tests/test_realtime_outcome_delivery_tier_gates.py
- def test_realtime_outcome_delivery_has_tp_tier_gate_rules() -> None:  ·L7

## tests/test_realtime_outcome_tp_tiers.py
- def test_free_tp_message_contains_suggested_sl_guidance() -> None:  ·L11
- def test_premium_tp2_message_contains_lock_gains_suggestion() -> None:  ·L27
- def test_vip_tp3_message_contains_trail_tight_suggestion() -> None:  ·L43

## tests/test_realtime_outcome_tracker_user_perf_ids.py
- class _Rows:  ·L5
- def __init__(self, rows):  ·L6
- def all(self):  ·L9
- class _Session:  ·L13
- def __init__(self, rows):  ·L14
- async def execute(self, _stmt):  ·L17
- class _SessionCM:  ·L21
- def __init__(self, rows):  ·L22
- async def __aenter__(self):  ·L25
- async def __aexit__(self, exc_type, exc, tb):  ·L28

## tests/test_redis_webhook_queue.py
- class _FakeRedis:  ·L4
- def __init__(self):  ·L5
- def llen(self, _key):  ·L8
- def rpush(self, _key, raw):  ·L11
- def blpop(self, _key, timeout=0):  ·L15
- def test_webhook_queue_roundtrip_with_redis_client_stub():  ·L21

## tests/test_risk_dynamic.py
- def sample_signal():  ·L19
- def account_state_normal():  ·L34
- def account_state_soft():  ·L38
- def account_state_hard():  ·L42
- def test_calculate_position_size(sample_signal):  ·L45
- def test_soft_throttle_active(account_state_soft):  ·L54
- def test_hard_stop_active(account_state_hard):  ·L57
- def test_get_max_volatility():  ·L60
- def test_risk_check_good(sample_signal, account_state_normal):  ·L63
- def test_risk_check_low_expectancy(sample_signal, account_state_normal):  ·L67

## tests/test_signal_dedup_rules.py
- class _FakeResult:  ·L12
- def __init__(self, rows: list[Signal] | None = None):  ·L13
- def scalar_one_or_none(self):  ·L16
- def scalars(self):  ·L19
- def first(self):  ·L22
- def all(self):  ·L25
- class _FakeSession:  ·L29
- def __init__(self, rows: list[Signal] | None = None):  ·L30
- async def execute(self, _statement):  ·L35
- def add(self, obj):  ·L38

## tests/test_signal_deduplicator.py
- class TestSignalDeduplicator(unittest.TestCase):  ·L7
- def setUp(self):  ·L8
- def test_semantic_similarity_matches_nearby_entry_same_direction(self):  ·L11
- def test_semantic_similarity_rejects_opposite_direction(self):  ·L33
- def test_dedupe_batch_keeps_best_representative(self):  ·L41

## tests/test_signal_fingerprint.py
- def test_signal_fingerprint_includes_candle_timestamp() -> None:  ·L4

## tests/test_single_service_defaults.py
- def _env(**overrides):  ·L25
- def _getenv(key, default=None):  ·L30
- class TestLoopDefaults(unittest.TestCase):  ·L42
- def _run_worker_is_enabled(self, env_overrides: dict) -> bool:  ·L45
- def _run_engine_is_enabled(self, env_overrides: dict) -> bool:  ·L51
- def test_worker_default_is_on_without_railway_env(self):  ·L57
- def test_worker_default_is_off_with_railway_service_name(self):  ·L61
- def test_worker_explicit_zero_disables_worker(self):  ·L65
- def test_worker_explicit_one_enables_worker(self):  ·L69
- def test_engine_default_is_on_without_railway_env(self):  ·L73

## tests/test_strategies.py
- class TestCommodityStrategy(unittest.TestCase):  ·L6
- def test_generate_no_data(self):  ·L7
- def test_generate_simple_long(self):  ·L12

## tests/test_strategy_runner_async.py
- class AsyncRunnerTests(unittest.IsolatedAsyncioTestCase):  ·L6
- async def test_async_runner_calls_strategy(self):  ·L7
- class FakeAsyncStrategy:  ·L8
- def __init__(self):  ·L9
- async def generate(self, market_data):  ·L12

## tests/test_strategy_runner.py
- class StrategyRunnerTests(unittest.TestCase):  ·L5
- def test_runner_invokes_strategy(self):  ·L6
- class FakeStrategy:  ·L8
- def __init__(self):  ·L9
- def generate(self, market_data):  ·L12

## tests/test_telemetry.py
- def test_prometheus_metrics_text_contains_observations():  ·L12
- def test_prometheus_endpoint_exposes_text_metrics():  ·L26

## tests/test_tick_liquidity.py
- def make_candle_df(start: datetime, periods: int):  ·L8
- def make_tick_df(start: datetime):  ·L15
- def test_tick_partial_fill_simulation():  ·L24

## tests/test_time_stop_outcome_persistence.py
- async def test_persist_outcome_maps_time_stop_channels(monkeypatch):  ·L9
- class _DummyOutcome:  ·L12
- class _DummySession:  ·L15
- async def execute(self, _stmt):  ·L16
- async def commit(self):  ·L19
- async def _fake_get_session():  ·L23
- async def _fake_upsert_outcome(session, signal_id, status, **kwargs):  ·L26
- async def _fake_queue_outcome_notifications_for_outcome(session, outcome_id, signal_id, status):  ·L32

## tests/test_timeutils.py
- class TimeutilsTest(unittest.TestCase):  ·L7
- def test_to_naive_aware(self):  ·L8
- def test_now_utc_naive(self):  ·L18

## tests/test_trade_tracker.py
- def _utcnow_naive_iso() -> str:  ·L18
- class TestTradeTracker(unittest.TestCase):  ·L22
- def setUp(self):  ·L23
- def test_trade_record_creation_basic(self):  ·L28
- def test_trade_record_creation_multiple_targets(self):  ·L48
- def test_add_trade(self):  ·L67
- def test_add_trade_deduplicates_signal_id(self):  ·L84
- def test_open_trades_clears_stale_cache_when_state_empty(self, mock_state):  ·L104
- def test_price_hit_tp_long(self, mock_price):  ·L121
- def test_price_hit_tp_short(self, mock_price):  ·L144

## tests/test_volume_delta.py
- def _make_candle(open, high, low, close, vol):  ·L4
- def test_calculate_volume_delta_simple():  ·L8

## tests/test_web_api_tokens.py
- class TestWebApiTokens(unittest.IsolatedAsyncioTestCase):  ·L12
- async def test_rotate_and_revoke_token(self):  ·L13

## tests/test_wfo_train.py
- def make_synthetic_df(start: datetime, periods: int, freq: str = '5T') -> pd.DataFrame:  ·L8
- def test_wfo_train_and_predict():  ·L22
- def trainer(signals, df_map):  ·L29

## tests/test_yfinance_integration.py
- class TestYfinanceIntegration(unittest.TestCase):  ·L13
- def test_convert_to_yfinance_symbol_crypto(self):  ·L14
- def test_convert_to_yfinance_symbol_fx(self):  ·L20
- def test_convert_to_yfinance_symbol_commodity(self):  ·L26
- def test_convert_to_yfinance_symbol_stock(self):  ·L34
- def test_fetch_via_yfinance_success(self, mock_ticker_class):  ·L41
- def test_fetch_via_yfinance_empty_response(self, mock_ticker_class):  ·L71
- def test_fetch_via_yfinance_exception(self, mock_ticker_class):  ·L81
- def test_get_realtime_price_success(self, mock_ticker_class):  ·L89
- def test_get_realtime_price_fallback_to_binance(self, mock_requests, mock_ticker_class):  ·L101

## THRESHOLD_FIX_GUIDE.md
- # ML Threshold Fix - Complete Guide  ·L1
- ## Problem Summary  ·L3
- ## Root Cause Analysis  ·L6
- ## Solution - Set These Railway Environment Variables  ·L11
- ### Step 1: Environment Variables (Railway Dashboard)  ·L13
- ### Step 2: Run SQL Fix  ·L23
- ### Step 3: Remove USDTARS (Fix Polygon 429 Errors)  ·L33
- ## Expected Results After Fix  ·L36
- ## Verification Commands  ·L41

## tmp_test_market_state.py
- from unittest.mock import patch
