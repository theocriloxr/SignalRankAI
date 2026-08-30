#!/usr/bin/env bash
# SignalRankAI v1.5.1 one-owner staging migration/bootstrap entrypoint.
set -euo pipefail

export ENVIRONMENT="${ENVIRONMENT:-staging}"
if [[ "${ENVIRONMENT,,}" == "production" ]]; then
  echo "Refusing production execution; use scripts/controlled_migrate.py" >&2
  exit 64
fi
if [[ -z "${DATABASE_MIGRATION_URL:-}" && -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_MIGRATION_URL or DATABASE_URL is required" >&2
  exit 65
fi
if [[ "${STAGING_MIGRATION_ACKNOWLEDGED:-0}" != "1" ]]; then
  echo "STAGING_MIGRATION_ACKNOWLEDGED=1 is required" >&2
  exit 66
fi

args=(--top "${BOOTSTRAP_DISCOVERY_TOP:-100}")
if [[ "${BOOTSTRAP_DISCOVER:-1}" == "1" ]]; then
  args+=(--discover)
fi
if [[ "${SKIP_STAGING_CERTIFICATION:-0}" == "1" ]]; then
  args+=(--skip-certification)
fi
python scripts/staging_migrate_and_bootstrap.py "${args[@]}"
