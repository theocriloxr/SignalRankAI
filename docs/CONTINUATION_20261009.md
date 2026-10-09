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
