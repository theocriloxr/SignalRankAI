#!/bin/bash
# Deployment script for SignalRankAI

# Activate virtual environment (if any)
# source venv/bin/activate

# Emit version/build metadata at boot.
python -c "from core.version import get_version_banner; print('[boot] ' + get_version_banner())" || true

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

# Optional pre-boot migration step.
# Default is OFF to keep Railway healthcheck startup fast.
# The app also runs startup DB ops internally.
if [ "${RUN_DB_MIGRATIONS_AT_BOOT:-false}" = "true" ] && [ -n "${DATABASE_URL}" ]; then
	echo "[boot] Running database migrations..."
	python -m alembic upgrade head || echo "[WARN] Migration failed, continuing anyway..."
fi

# Railway-safe default:
# - On Railway, default to the monolith web entrypoint (railway_main) even when
#   RUN_MODE is set, unless explicitly overridden.
# - This prevents accidental RUN_MODE=engine/worker/bot deployments from failing
#   platform HTTP healthchecks.
# - Outside Railway, RUN_MODE is still honored via main.py.

_on_railway="false"
if [ -n "${RAILWAY_SERVICE_NAME:-}" ] || [ -n "${RAILWAY_ENVIRONMENT:-}" ]; then
	_on_railway="true"
fi

_honor_run_mode_on_railway="false"
if [ "${HONOR_RUN_MODE_ON_RAILWAY:-false}" = "true" ]; then
	_honor_run_mode_on_railway="true"
fi

if [ -n "${RUN_MODE:-}" ] && { [ "${_on_railway}" != "true" ] || [ "${_honor_run_mode_on_railway}" = "true" ]; }; then
	case "${RUN_MODE}" in
		web|worker|engine|bot)
			python main.py
			exit $?
			;;
		all)
			# Legacy env often left behind on Railway. For this service we want
			# railway_main webhook stack (with /telegram/webhook route).
			exec uvicorn railway_main:app --host 0.0.0.0 --port "${PORT:-8000}"
			;;
		*)
			# Unknown RUN_MODE => safe default to web monolith
			exec uvicorn railway_main:app --host 0.0.0.0 --port "${PORT:-8000}"
			;;
	esac
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
