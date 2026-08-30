#!/usr/bin/env bash
# SignalRankAI v1.4.2 one-owner staging migration/bootstrap entrypoint.
# Configure this on exactly ONE Railway service (or a dedicated migration job).
set -euo pipefail

export ENVIRONMENT="${ENVIRONMENT:-staging}"
if [[ "${ENVIRONMENT,,}" == "production" && "${ALLOW_PRODUCTION_PREDEPLOY:-0}" != "1" ]]; then
  echo "Refusing production predeploy without ALLOW_PRODUCTION_PREDEPLOY=1" >&2
  exit 64
fi

if [[ -z "${DATABASE_MIGRATION_URL:-}" ]]; then
  echo "DATABASE_MIGRATION_URL is required and must be the direct PostgreSQL URL" >&2
  exit 65
fi

python -m alembic upgrade head
python -m alembic current
python -m tools.bootstrap_ecosystem ${BOOTSTRAP_DISCOVER:+--discover} --top "${BOOTSTRAP_DISCOVERY_TOP:-100}"
python -m tools.staging_certification
