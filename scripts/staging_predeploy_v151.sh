#!/usr/bin/env bash
# SignalRankAI v1.5.1 one-owner staging migration/bootstrap entrypoint.
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
mapfile -t heads < <(python -m alembic heads | awk '{print $1}')
if [[ "${#heads[@]}" -ne 1 || "${heads[0]}" != "$expected_head" ]]; then
  printf 'Unexpected repository migration heads: %s (expected one head: %s)\n' "${heads[*]:-none}" "$expected_head" >&2
  exit 66
fi

python -m alembic upgrade head
if ! python -m alembic current | grep -q "$expected_head"; then
  echo "Database migration did not reach $expected_head" >&2
  exit 67
fi

python -m tools.bootstrap_ecosystem ${BOOTSTRAP_DISCOVER:+--discover} --top "${BOOTSTRAP_DISCOVERY_TOP:-100}"
python -m tools.staging_certification
