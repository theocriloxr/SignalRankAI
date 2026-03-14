#!/bin/bash
# Deployment script for SignalRankAI

# Activate virtual environment (if any)
# source venv/bin/activate

# Install dependencies at boot only when explicitly requested.
# (Image build already installs requirements in Dockerfile.)
if [ "${INSTALL_AT_BOOT:-false}" = "true" ] && [ -f requirements.txt ]; then
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

# Railway-safe default:
# - If RUN_MODE is explicitly set, honor it via main.py
# - Otherwise run the monolith web entrypoint (railway_main) so /healthz exists
#   and background services start in lifespan.

if [ -n "${RUN_MODE:-}" ]; then
	python main.py
	exit $?
fi

# Optional legacy mode: run separate processes in one container.
if [ "${RUN_ALL:-false}" = "true" ]; then
	RUN_MODE=web python main.py &
	RUN_MODE=engine python main.py &
	RUN_MODE=bot python main.py &
	wait
	exit $?
fi

exec uvicorn railway_main:app --host 0.0.0.0 --port "${PORT:-8000}"
