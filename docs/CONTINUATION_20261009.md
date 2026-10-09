# SignalRankAI continuation — 9 October 2026

The continuation starts from published `a50ccf4cc87aa7c36b52cf57bd60fe073a067c60`
in draft PR [189](https://github.com/theocriloxr/SignalRankAI/pull/189), on the
actual release base `fix/provider-discovery-readiness-20260923`.

Hosted run `37781419109` passed manifest, frontend, static quality and the
research browser. Both backend versions failed batch 17: the recovered tracker
fixture always returned an empty shared store. When `REDIS_URL` is set, the
tracker correctly clears local trades if shared state is empty. This made four
outcome unit tests fail; the earlier local run lacked that environment setting.

The fixture now uses isolated persistent records for reads, writes and removals.
All four outcome tests explicitly enable the Redis-configured behavior, while
their store and prices remain synthetic. The original test of stale-cache
clearing still deliberately returns an empty store. The hosted 106-test batch
passes locally after this repair. No runtime fallback or CI gate was weakened.
Hosted verification on the successor commit remains required.

Mobile installation, type checking and 44 tests passed in the same hosted run.
Its unchanged audit gate failed on four high rows from node-forge and the
inheriting Expo code-signing/CLI graph. Production approval was skipped.

Continue the ordered directives in `docs/completion-order-20261006.md`.
The research source Google Doc, instrument/account evidence, complete customer
and native acceptance, and a fresh clean release observation remain open.

## Execution-cost continuation

The legacy WFO simulator sized for entry slippage and commissions but omitted
stop-exit slippage from the loss denominator. With a tight stop, its own modeled
stop loss could exceed the configured budget. It also used an independent 20%
notional ceiling rather than the bounded adviser's 10% ceiling.

Replay now reuses the bounded spot-unit adviser and includes slippage and fees
at both ends when limiting the filled quantity. The versioned v3 records expose
the configured budget, modeled stop risk and observed breaches; calendar-fold
reports preserve breach counts. Gap losses remain uncapped and visible.
Malformed costs/equity and arithmetic overflow reject the run rather than
publishing nonfinite evidence.

The 92-test research/execution/adviser selection passes, including long/short
stop budgets, long/short gaps, invalid cost policies, overflow and calendar WFO
reporting. Critical Pyright and targeted Ruff pass. A focused OpenGrep scan of
the two runtime files passed with no findings or errors. Hosted verification on
the successor remains required. Portfolio aggregation, instrument-specific costs,
native and broker acceptance, source-document review and new release observation
are not certified by these synthetic tests.

Hosted run `37888251253` on published `fc3d0a1` passed both backend Python
versions, frontend, static quality, manifest and research browser. Mobile again
failed its dependency audit with the four known high rows after 44 tests passed.
Release certification failed and production source approval was skipped.

## Missing health-evidence continuation

The health query previously used an inner lateral join, silently dropping active
profiles with no eligible signal-delivery outcomes. It now retains those profiles
and reports UNAVAILABLE/INSUFFICIENT/OBSERVED/INVALID evidence explicitly. Empty
and undersized windows retain null metrics. Missing observations do not fabricate
losses or trigger a synthetic suspension. Existing invalid/degraded observations
still suspend, including profiles beyond the first 20 displayed diagnostics.

Coverage counts include every queried current CANARY/LIMITED_LIVE/APPROVED
profile. The operator view exposes per-profile samples, evidence reasons and
staleness, and explains that a completed monitor iteration is not certified health
or broker/baseline evidence. Unit checks pass locally; actual PostgreSQL coverage
and desktop/mobile light/dark display checks remain required on the successor
hosted commit. This closes a surveillance visibility bug, not approved baseline,
decay-analysis, alert-retention or complete strategy-health acceptance.

Hosted run `37889078327` on `d978f52d` passed both backend versions, manifest,
frontend and static quality. Its research gate passed all 297 tests, including
the real PostgreSQL coverage case with 23 profiles and suspension beyond the
display limit. The browser job failed because the test demanded an exact text
match on a paragraph that also contained the stale-monitor warning. The
successor preserves the warning and checks the coverage text within that
paragraph. Mobile retains the four high audit rows; production approval remains
blocked. The failed browser evidence is retained.

## Closed-bar replay continuation

A reproduced hourly candle opened at 00:05 and became available at 01:05, but
the legacy replay previously used its target/high/volume to report a closed
winner in a window ending at 00:10. Version v4 excludes those unavailable OHLC
bars and exposes their exclusion plus the last observed availability timestamp.
Timestamped quote snapshots retain their instantaneous availability. Training
labels likewise exclude bars closing beyond the label horizon. Unknown/monthly,
zero and overflowing durations cannot become a default one-minute bar.

The 198-test local research, risk, health, browser-safety, authorization and
governance selection passes. Critical typing and targeted Ruff pass. Boundary
tests cover minute through weekly bars, exact cutoffs, future-bar mutation and
tick/orderbook availability. Hosted checks on the successor remain required.
This is a deterministic replay boundary repair; venue calendars, publication
delays, instrument capacity/cost stress and portfolio qualification remain open.
