# Research snapshot continuation, 10 October 2026

Continue PR #189 on `fix/release-recovery-20261008`, preserving published parent
`054e7eccd8368b2ecb64736fc065a516c60a0ecb`. This increment repairs one R1
reproducibility gap. It does not finish the complete requested programme or
authorize a production deployment or financial activation.

## Implemented behavior

The canonical adaptive worker now persists the complete outcome rows and
captured sequence metadata used by research, and consumes the saved snapshot.
The reader checks canonical encoding, hash, manifest, chronology and source
identity. Source corrections cannot rewrite older experiments. Missing legacy
snapshots remain unavailable. Concurrent retries preserve the first snapshot.
The bounded format rejects oversized evidence without truncation.

Migration `0052_research_dataset_snapshots` adds the append-only snapshot table.
Startup and runtime admission require both active mutation guards with the
correct events. Operator research diagnostics expose snapshot scope and
availability without claiming full market-input replay. Non-string or blank
provider identities no longer pass captured-sequence availability checks.

Current schema defaults, release metadata, example profiles and their head
contracts expect 0052. Historical migrations and specification sources are
preserved. Remote production configuration and schema remain unchanged.

## Verification and limits

The implementation's focused snapshot/availability run passed 46 tests. The
real PostgreSQL research-worker suite passed 42 tests, including correction
replay, concurrent retries and mutation rejection. A subsequent owned-database
admission/codec/guard run passed 93 tests. Critical typing passed with zero
errors and warnings using the locked runtime; Ruff F/E9, completion inventory,
44-gate manifest validation and complete offline migration rendering passed.
These overlapping checks are not summed. Successor immutable-source hosted/full
results belong in the PR and final handoff after publication.

An initial typing invocation used the wrong runtime, and a sandboxed invocation
could not resolve installed package sources. Both failures are retained; the
correct locked-runtime check with dependency-source access passed. No typing
rule or dependency source was weakened to hide them.

Snapshot tests use synthetic research observations and real local PostgreSQL.
They do not establish publication vintages, survivorship correctness, historical
session calendars, complete feature/OHLC replay, actual broker execution or edge.

## Release state and next work

The published parent still fails mobile security and aggregate certification.
The primary node-forge advisory still reports no patched version. No security
waiver, CI bypass, production merge, remote migration or money enablement was
performed. The inspected four production application services remain online
on the existing release; this does not certify all auxiliary services.

The matrix still has one PARTIAL research section and 990 AUDIT_PENDING entries,
not 991 independently verified requirements. Continue R1 historical universes,
provider/publication histories, full input replay and calendars, then R2-R17 and
the ordered customer, web/native, broker and resilience work. Mobile remediation,
isolated candidate migration/restore, actual provider/demo/native acceptance,
a fresh 24-72-hour staging soak and two full final audits remain mandatory.
The self-improving ecosystem follows those foundations. All financial flags
must remain disabled and the global execution kill switch enabled during work.
