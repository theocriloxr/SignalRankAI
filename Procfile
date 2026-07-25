web: uvicorn railway_main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: RUN_MODE=worker python main.py
engine: RUN_MODE=engine python main.py
bot: RUN_MODE=bot python main.py
