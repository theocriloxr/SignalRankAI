# Engine Pulse Metrics Stabilization Report - 2026-07-02

## Scope

This pass addressed frozen or misleading Engine Pulse totals where scans were
still running, but cumulative pulse values appeared unchanged for hours.

## Root Cause

- `stats.scanned` was incremented only after an asset passed the market-data
  gate. Provider timeouts, stale candles, and no-candle assets were counted in
  per-cycle logs, but not in global pulse counters.
- The admin pulse preferred cumulative global counters over fresh window/cycle
  evidence, which could make an old all-time snapshot look like current hourly
  activity.
- Early pipeline exits such as no candles, stale data, no strategy signals,
  consensus blocks, validation failures, and scoring exceptions were not always
  reflected in rejection buckets.

## Changes

- Added `engine:last_cycle` heartbeat state with cycle status, attempted assets,
  market-data fetch status, duration, generated signal count, max score, and
  pipeline counters.
- Moved scan counting to the attempted-asset level so failed/no-candle cycles are
  still counted as work attempted.
- Added rejection accounting for early pipeline exits and exception paths.
- Updated admin pulse aggregation to prefer fresh DB window evidence, then latest
  cycle evidence, then cumulative global counters as a fallback.
- Added `Accounted` and `Unaccounted` counts to the admin pulse so metric gaps
  are visible.
- Added latest cycle details to the pulse message for faster production triage.

## Verification

- Added regression coverage for latest-cycle pulse fallback when DB window
  evidence is empty but the engine has attempted a cycle.
- Added static coverage ensuring scan attempts are counted before the market-data
  gate and `engine:last_cycle` remains published.

