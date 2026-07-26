#!/bin/bash
# Canonical SignalRankAI deployment entrypoint.
set -euo pipefail

# Emit version/build metadata at boot without exposing secrets.
python -c "from core.version import get_version_banner; print('[boot] ' + get_version_banner())" || true

# Install dependencies at boot only when explicitly requested. Production image
# builds should install requirements before runtime.
if [ "${INSTALL_AT_BOOT:-false}" = "true" ] && [ -f requirements.txt ]; then
    python -m pip install --no-cache-dir -r requirements.txt
fi

# Load a local dotenv file only when explicitly enabled. Railway and production
# must use injected/sealed variables instead.
if [ "${ALLOW_DOTENV:-false}" = "true" ] && [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

# Run migrations only during a controlled deployment. A failed migration is a
# hard startup failure; the service must never run against an unknown schema.
if [ "${RUN_DB_MIGRATIONS_AT_BOOT:-false}" = "true" ] && [ -n "${DATABASE_URL:-}" ]; then
    echo "[boot] Running database migrations..."
    if ! python -m alembic upgrade head; then
        echo "[FATAL] Migration failed; refusing to start with an unknown schema state." >&2
        exit 1
    fi
fi

_start_monolith() {
    # SignalRankAI's Railway Hobby profile is a coordinated single-process
    # async monolith. Keep one Uvicorn worker so schedulers, queues, engines and
    # lifecycle workers cannot be duplicated by process-local ownership.
    exec uvicorn railway_main:app \
        --host 0.0.0.0 \
        --port "${PORT:-8000}" \
        --workers 1
}

_on_railway="false"
if [ -n "${RAILWAY_SERVICE_NAME:-}" ] || [ -n "${RAILWAY_ENVIRONMENT:-}" ]; then
    _on_railway="true"
fi

_honor_run_mode_on_railway="false"
if [ "${HONOR_RUN_MODE_ON_RAILWAY:-false}" = "true" ]; then
    _honor_run_mode_on_railway="true"
fi

# Optional decomposed roles remain available for future multi-service scaling.
# On Railway the safe default is always the HTTP monolith unless explicitly
# overridden, because the platform healthcheck and Telegram webhook require it.
if [ -n "${RUN_MODE:-}" ] && { [ "${_on_railway}" != "true" ] || [ "${_honor_run_mode_on_railway}" = "true" ]; }; then
    case "${RUN_MODE}" in
        web|worker|engine|bot|delivery|outcome|analytics|scheduler)
            exec python main.py
            ;;
        all)
            _start_monolith
            ;;
        *)
            echo "[boot] Unknown RUN_MODE=${RUN_MODE}; starting safe monolith" >&2
            _start_monolith
            ;;
    esac
fi

if [ "${RUN_ALL:-false}" = "true" ]; then
    _start_monolith
fi

_start_monolith
