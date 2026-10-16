# Prospective engine universe observations

This R1 increment captures the universe actually seen by the main engine cycle.
It preserves ordered managed, pinned and discovered candidates, the results of
profile filtering, market-open filtering, runtime eligibility, the scheduling
cap and the final batch after class-coverage anchors. An anchor can come from
an eligible instrument outside the cap; the observation preserves that fact.
The discovery path, profile-filter application, cap, batch size and UTC
observation time are bound to the content hash. The database-registry discovery
path can include per-class provider fallback; it does not prove that every
candidate came from the database or was broker-executable.

The round-robin queue now applies removals on every refresh call, including
calls inside the hourly addition interval. Both pending work and the refill
universe are pruned. This prevents an instrument disabled by a runtime gate,
market closure, changed demand or blacklist from returning in a later batch.
New additions retain the existing refresh interval and round-order behavior.

Before strategy evaluation, the engine supplies its frozen cycle observation
with the actual market data. Adaptive input capture validates membership and
chronology and embeds the detached observation in the existing immutable
`research_market_inputs` payload. This additive optional field retains format
1 and the original identities of legacy captures that lack it. No migration or
new mutable universe authority is introduced. Each timeframe input embeds the
observation, so storage repeats the bounded selection record across timeframes;
representative capacity and retention acceptance remain required.

Signal sequence metadata binds the universe hash to the corresponding captured
input. Both actual signal writers validate the binding within the existing
optional-evidence savepoint. A mismatch rolls back optional evidence without
losing the canonical signal. Dataset snapshots retain the reference; research
reads the stored bytes, validates scope, selected membership and the as-of
cutoff, and reports `observed_universe` separately. Operator research results
expose the same scoped receipt. Mixed legacy datasets remain UNVERIFIED for
universe observations. They cannot obtain a partial PASS by dropping references.

Each observation allows at most 2,000 unique candidates per stage and 256 KiB;
the enclosing input's existing 512 KiB limit, eight-input batch limit and audit
count/byte budgets also apply. Unknown fields, duplicate/invalid symbols,
noncanonical timestamps, unsupported provenance, stage/selection mismatches,
future observations and altered hashes fail validation. Capture failure stays
explicitly UNAVAILABLE, with no truncation or fabricated membership evidence.

PASS covers identity of prospective engine selection only. It does not recover
prior universes, delisted securities, listing dates, corporate actions, provider
publication/revision histories, exact eligibility reasons, historical calendars,
execution eligibility, feature/repainting validation or strategy profitability.
The existing survivorship and other scientific qualification checks remain
UNVERIFIED. R1/specification section 22 remains PARTIAL. Separate legacy
generators without this main-engine observation remain unqualified.

This change does not certify production, actual provider/broker behavior,
installed native devices, the required soak or the two final full audits.
Release acceptance still requires all gates for one immutable candidate; financial
execution remains disabled. PR #189 remains draft while required gates fail.
