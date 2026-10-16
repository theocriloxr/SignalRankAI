# Captured research inputs - 11 October 2026

Continue on `fix/release-recovery-20261008`, draft PR #189. The preceding SDK
checkpoint `d8e4a842ff18d0a04db33fef0dc7dca4a4acab67` passed both hosted backend
runtimes (3,487 tests each), static, frontend, research browser and installed SDK
checks. Its mobile security failure and unperformed external acceptance remain.

The next R1 increment preserves the normalized `MarketContext` supplied to
adaptive components: all captured candles, including genuine order-flow fields,
indicators, regime/session/bias, quality and available news/macro context.
Canonical JSON binds values, scope, observation time and explicit unknown source
history. Captures reject nonfinite/unsupported values, sensitive field names and
excessive size/depth/count instead of silently truncating data. When capture
succeeds, components receive detached read-only values. Failed capture remains
explicitly UNAVAILABLE and does not become historical proof.

The actual pandas indicator output includes NumPy scalar numbers and booleans.
Capture normalizes NumPy integers, float16/32/64 and booleans to equivalent
Python JSON primitives before validation. This preserves the same identity as
native scalar inputs. Nonfinite values, arrays, complex numbers and extended
precision remain unsupported; they cannot silently lose precision or become
scientific evidence. Regression coverage uses the real indicator calculator,
not only manually supplied Python floats.

Migration `0053_research_market_inputs` adds an immutable content-addressed
relation. Multiple signals from one assessment reuse a capture. Persistence
orders hashes deterministically; identical concurrent retries preserve one row.
The signal transaction contains an evidence savepoint: a failed optional research
write rolls back captures, references and evidence without aborting the canonical
signal commit. The main engine's `store_signal_compat` / `get_or_create_signal`
path and the legacy repository share this savepoint implementation. Error logs
expose the exception type rather than raw statements.
This does not waive any signal or order admission check.
The serving writer also isolates its optional strategy-statistics write, which
previously could leave the transaction aborted after a caught SQL error. Actual
PostgreSQL failure tests cover both writers and both optional write failures.

Dataset fingerprints retain new capture references without rewriting legacy
snapshot identities. Research reads the immutable bytes in bounded chunks and
validates their digest, headers, instrument, timeframe, provider, capture cutoff
and linked sequence hash. Missing old captures stay UNVERIFIED. Tampered bytes,
future inputs, scope/lineage mismatches and audit budget exhaustion reject the
evaluation rather than yielding a partial success. The result and existing
operator API distinguish captured-input identity from full point-in-time replay.
Startup/runtime admission requires both enabled mutation guards on the new table.
Signals refreshed before first delivery retain their original decision timestamp;
later captures cannot certify that earlier decision and fail the chronology check.
Their complete decision-revision history remains a separate acceptance gap.

The capture limit is 2,000 candles and 512 KiB per context; one persistence batch
has at most eight captures. A research audit accepts at most 2,048 unique inputs
and 64 MiB, using chunks of sixteen. These are hard resource bounds, not sampling
or retention policies. Evidence is append-only; archive/retention, capacity and
representative staging load acceptance remain required before rollout. Database
administrators can disable guards; replay still rejects changed content under
its original hash. The existing mutable candle table is not replay authority.

This increment does not recover past provider revisions, listings/delistings,
corporate actions, historical universe membership, calendar/DST truth, missing
old inputs or every feature's look-ahead/repainting behavior. R1 and specification
section 22 remain PARTIAL. No strategy edge, broker fills, device behavior,
production deployment, live activation, completed audit or soak is certified.

Focused SQL/failure, complete immutable-source and hosted receipts are recorded
in PR #189 and the local continuation artifacts after verification. Historical
SDK receipts do not certify this successor. The same source must still pass all
required release gates and isolated staging migration/restore before deployment.
