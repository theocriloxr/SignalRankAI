# SignalRankAI 1.0.5 Railway Readiness Timeout Hotfix

Railway staging proved that migrations through `0023_signal_runtime_schema`,
PostgreSQL, both Redis roles, Telegram webhook registration, the worker and live
Coinbase REST data were operational. The deployment remained unready because the
database readiness probe allowed only 1.5 seconds while startup maintenance and
Telegram initialization were warming a two-connection Railway pool.

Version 1.0.5 keeps readiness fail-closed while removing the false negative:

- `DB_READINESS_TIMEOUT_SECONDS` defaults to 8 seconds and is bounded to 2–30.
- readiness uses the reserved `DBPriority.CRITICAL` lane;
- migration head, required runtime columns and the active-thesis unique index
  are checked in one catalogue query instead of four database round trips;
- timeout responses retain a structured reason and the effective timeout.

Recommended Railway value:

```env
DB_READINESS_TIMEOUT_SECONDS=8
```
