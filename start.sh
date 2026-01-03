#!/bin/bash
# Deployment script for SignalRankAI

# Activate virtual environment (if any)
# source venv/bin/activate

# Install dependencies (optional; Railway/Nixpacks usually handles this)
if [ -f requirements.txt ]; then
	pip install -r requirements.txt
fi

# Export environment variables from .env only when explicitly enabled.
# Railway/production should use injected environment variables.
if [ "${ALLOW_DOTENV:-false}" = "true" ] && [ -f .env ]; then
	export $(grep -v '^#' .env | xargs)
fi

# Run database migrations BEFORE starting services
# This ensures schema is up-to-date before any code tries to query it
if [ -n "${DATABASE_URL}" ]; then
	echo "[boot] Running database migrations..."
	python -m alembic upgrade head || echo "[WARN] Migration failed, continuing anyway..."
fi

# Default: run a single mode via RUN_MODE (engine/web/worker/bot)
# Optional: RUN_ALL=true to run web + engine + bot in one container.

if [ "${RUN_ALL:-false}" = "true" ]; then
	RUN_MODE=web python main.py &
	RUN_MODE=engine python main.py &
	RUN_MODE=bot python main.py &
	wait
else
	python main.py
fi
