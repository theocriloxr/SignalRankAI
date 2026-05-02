# Environment Variables Index

> Auto-generated from `core/settings.py` by `scripts/gen_env_index.py`.

| Variable | Type | Default | Example present in `.env.example` | Used in files (sample) |
|---|---|---|---|---|
| `DATABASE_URL` | `str` | `PydanticUndefined` | yes | config.py, test_core.py, test_all_functions.py |
| `ENABLE_ML` | `bool` | `True` | yes | ml/inference.py, core/settings.py |
| `ENABLE_NEWS` | `bool` | `True` | yes | core/settings.py |
| `LOG_JSON` | `bool` | `False` | yes | main.py, core/settings.py |
| `ML_MODEL_PATH` | `Optional` | `` | yes | tests/test_ml_schema_evolution.py, ml/retrain.py, ml/inference.py |
| `NEWS_API_KEY` | `Optional` | `` | yes | verify_system.py, core/settings.py |
| `PAPER_MODE` | `bool` | `False` | yes | core/settings.py |
| `REDIS_URL` | `Optional` | `` | yes | config.py, verify_system.py, railway_main.py |
| `RUN_MODE` | `str` | `engine` | yes | main.py, telegram/bot.py, scripts/generate_railway_prefill_sheet.py |
| `SENTRY_DSN` | `Optional` | `` | yes | utils/logging_config.py, core/settings.py |
| `SENTRY_TRACES_SAMPLE_RATE` | `float` | `0.0` | yes | utils/logging_config.py, core/settings.py |
| `TELEGRAM_BOT_TOKEN` | `Optional` | `` | yes | config.py, verify_system.py, railway_main.py |
| `TELEGRAM_CONNECT_TIMEOUT` | `int` | `30` | yes | core/settings.py, signalrank_telegram/bot.py |
| `TELEGRAM_POOL_TIMEOUT` | `int` | `30` | yes | core/settings.py, signalrank_telegram/bot.py |
| `TELEGRAM_READ_TIMEOUT` | `int` | `30` | yes | core/settings.py, signalrank_telegram/bot.py |
| `TELEGRAM_WRITE_TIMEOUT` | `int` | `30` | yes | core/settings.py, signalrank_telegram/bot.py |
| `XGBOOST_MODEL_PATH` | `Optional` | `` | yes | ml/inference.py, core/settings.py |
