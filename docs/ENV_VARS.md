# Environment Variables Index

> Auto-generated from `core/settings.py` by `scripts/gen_env_index.py`.

| Variable | Type | Default | Example present in `.env.example` | Used in files (sample) |
|---|---|---|---|---|
| `DATABASE_URL` | `str` | `PydanticUndefined` | yes | test_core.py, test_all_functions.py, config.py |
| `ENABLE_ML` | `bool` | `False` | yes | core/settings.py |
| `ENABLE_NEWS` | `bool` | `True` | yes | core/settings.py |
| `LOG_JSON` | `bool` | `False` | yes | main.py, core/settings.py |
| `ML_MODEL_PATH` | `Optional` | `` | yes | engine/ml.py, core/settings.py, ml/inference.py |
| `NEWS_API_KEY` | `Optional` | `` | yes | core/settings.py |
| `PAPER_MODE` | `bool` | `False` | yes | core/settings.py |
| `REDIS_URL` | `Optional` | `` | yes | config.py, core/settings.py, core/redis_state.py |
| `RUN_MODE` | `str` | `engine` | yes | main.py, worker/worker.py, core/settings.py |
| `SENTRY_DSN` | `Optional` | `` | yes | core/settings.py, utils/logging_config.py |
| `SENTRY_TRACES_SAMPLE_RATE` | `float` | `0.0` | yes | core/settings.py, utils/logging_config.py |
| `TELEGRAM_BOT_TOKEN` | `Optional` | `` | yes | railway_main.py, config.py, worker/market_monitor.py |
| `TELEGRAM_CONNECT_TIMEOUT` | `int` | `30` | yes | core/settings.py, signalrank_telegram/bot.py |
| `TELEGRAM_POOL_TIMEOUT` | `int` | `30` | yes | core/settings.py, signalrank_telegram/bot.py |
| `TELEGRAM_READ_TIMEOUT` | `int` | `30` | yes | core/settings.py, signalrank_telegram/bot.py |
| `TELEGRAM_WRITE_TIMEOUT` | `int` | `30` | yes | core/settings.py, signalrank_telegram/bot.py |
| `XGBOOST_MODEL_PATH` | `Optional` | `` | yes | core/settings.py |
