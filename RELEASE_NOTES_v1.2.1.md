# SignalRankAI v1.2.1 Runtime Import and Paper-Trading Hotfix

Release date: 29 July 2026
Baseline: SignalRankAI v1.2.0 Public Launch and Persistent Paper Trading
Migration head: `0027_launch_paper_trading` (no new migration)

## Railway incidents repaired

1. `No module named 'engine.adaptive.elliott'` prevented full bot setup and adaptive candle capture.
   - Added a backward-compatible `engine.adaptive.elliott` shim that re-exports the canonical component from `engine.adaptive.components.elliott`.
2. `get_session() got an unexpected keyword argument 'timeout'` crashed every paper-trading worker cycle.
   - Converted launch callsites to `timeout_seconds=`.
   - Added a deprecated, conflict-checked `timeout` compatibility alias to the DB session API so stale overlays fail safely rather than crash.
3. Railway staging inherited live-risk variables set to `1`.
   - The Railway entrypoint now forces real execution, automatic execution, auto-trading, copy trading, live MT5, Bybit execution, real payouts, public payments, and free/random distribution off outside production before configuration modules import.
4. Added separate safe staging and production environment templates.

## Required deployment posture

Use `SignalRankAI_v1.2.1_Railway_Staging_Safe.env.example` for the first Railway proof. Keep REST authoritative and leave WebSocket ingestion and proxy validation disabled until separately certified.

Expected startup evidence:

```text
[boot] SignalRankAI v1.2.1
[startup_safety] non-production environment forced live-risk flags off: ...   # only when stale variables were present
[worker] PaperTradingWorker started
[paper_worker] started
```

The following must not appear:

```text
No module named 'engine.adaptive.elliott'
get_session() got an unexpected keyword argument 'timeout'
```
