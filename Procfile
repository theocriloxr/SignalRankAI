web: uvicorn railway_main:app --host 0.0.0.0 --port ${PORT:-8000}
engine: HONOR_RUN_MODE_ON_RAILWAY=true RUN_MODE=engine python main.py
worker: HONOR_RUN_MODE_ON_RAILWAY=true RUN_MODE=worker python main.py
delivery: HONOR_RUN_MODE_ON_RAILWAY=true RUN_MODE=delivery python main.py
outcome: HONOR_RUN_MODE_ON_RAILWAY=true RUN_MODE=outcome python main.py
analytics: HONOR_RUN_MODE_ON_RAILWAY=true RUN_MODE=analytics python main.py
scheduler: HONOR_RUN_MODE_ON_RAILWAY=true RUN_MODE=scheduler python main.py
bot: HONOR_RUN_MODE_ON_RAILWAY=true RUN_MODE=bot python main.py
