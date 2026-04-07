# SignalRankAI

## Railway monolith production notes

### Migrations
- Runtime auto-migration is disabled by default (`AUTO_MIGRATE=false`).
- Run migrations in deploy/release step:
  - `python -m alembic upgrade head`

### Monolith tuning defaults
- Engine cadence: `ENGINE_CYCLE_SLEEP_SECONDS=30`
- Universe cap (mixed open-market assets): `ENGINE_UNIVERSE_CAP=20`
- Logging profile: essential (loop/webhook noise moved to debug-level)
- Telegram mode: webhook-only on Railway
- Outcome tracker ownership: worker-only

### DB hardening defaults (balanced mode)
- `DB_POOL_SIZE=5`
- `DB_MAX_OVERFLOW=3`
- `DB_POOL_TIMEOUT_SECONDS=30`
- `DB_POOL_RECYCLE_SECONDS=1800`
- `DB_RETRY_ATTEMPTS=3`

