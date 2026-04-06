# Environment Variables Index

> Auto-generated from `core/settings.py` by `scripts/gen_env_index.py`.

| Variable | Type | Default | Example present in `.env.example` | Used in files (sample) |
|---|---|---|---|---|
| `DATABASE_URL` | `str` | `PydanticUndefined` | no | test_core.py, test_all_functions.py, config.py |
| `ENABLE_ML` | `bool` | `False` | no | core/settings.py |
| `ENABLE_NEWS` | `bool` | `True` | no | core/settings.py |
| `LOG_JSON` | `bool` | `False` | no | main.py, core/settings.py |
| `ML_MODEL_PATH` | `Optional` | `` | no | engine/ml.py, core/settings.py, ml/inference.py |
| `NEWS_API_KEY` | `Optional` | `` | no | core/settings.py |
| `PAPER_MODE` | `bool` | `False` | no | core/settings.py |
| `REDIS_URL` | `Optional` | `` | no | config.py, core/settings.py, core/redis_state.py |
| `RUN_MODE` | `str` | `engine` | no | main.py, worker/worker.py, core/settings.py |
| `SENTRY_DSN` | `Optional` | `` | no | core/settings.py, utils/logging_config.py |
| `SENTRY_TRACES_SAMPLE_RATE` | `float` | `0.0` | no | core/settings.py, utils/logging_config.py |
| `TELEGRAM_BOT_TOKEN` | `Optional` | `` | no | railway_main.py, config.py, worker/market_monitor.py |
| `TELEGRAM_CONNECT_TIMEOUT` | `int` | `30` | no | core/settings.py, signalrank_telegram/bot.py |
| `TELEGRAM_POOL_TIMEOUT` | `int` | `30` | no | core/settings.py, signalrank_telegram/bot.py |
| `TELEGRAM_READ_TIMEOUT` | `int` | `30` | no | core/settings.py, signalrank_telegram/bot.py |
| `TELEGRAM_WRITE_TIMEOUT` | `int` | `30` | no | core/settings.py, signalrank_telegram/bot.py |
| `XGBOOST_MODEL_PATH` | `Optional` | `` | no | core/settings.py |

## Missing in `.env.example`

- `DATABASE_URL`
- `ENABLE_ML`
- `ENABLE_NEWS`
- `LOG_JSON`
- `ML_MODEL_PATH`
- `NEWS_API_KEY`
- `PAPER_MODE`
- `REDIS_URL`
- `RUN_MODE`
- `SENTRY_DSN`
- `SENTRY_TRACES_SAMPLE_RATE`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CONNECT_TIMEOUT`
- `TELEGRAM_POOL_TIMEOUT`
- `TELEGRAM_READ_TIMEOUT`
- `TELEGRAM_WRITE_TIMEOUT`
- `XGBOOST_MODEL_PATH`
