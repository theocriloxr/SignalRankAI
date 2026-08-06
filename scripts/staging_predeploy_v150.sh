#!/usr/bin/env bash
# SignalRankAI v1.5.0 one-owner staging migration/bootstrap entrypoint.
# Configure this on exactly ONE Railway service or a dedicated migration job.
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

expected_head="0038_account_security_product"
actual_head="$(python -m alembic heads | awk '{print $1}' | tail -1)"
if [[ "$actual_head" != "$expected_head" ]]; then
  echo "Unexpected repository migration head: $actual_head (expected $expected_head)" >&2
  exit 66
fi

python -m alembic upgrade head
current_head="$(python -m alembic current | awk '/0038_account_security_product/{print $1}' | tail -1)"
if [[ "$current_head" != "$expected_head" ]]; then
  echo "Database migration did not reach $expected_head" >&2
  exit 67
fi

python -m tools.bootstrap_ecosystem ${BOOTSTRAP_DISCOVER:+--discover} --top "${BOOTSTRAP_DISCOVERY_TOP:-100}"
python -m tools.staging_certification
