# Certification evidence and production observation

Additional audit repairs require actual boolean positive evidence. The asset
certification framework no longer treats strings such as `"false"`, nonzero
numbers or a status label as a successful step. Fresh quotes cannot replace
missing symbol discovery, canonical mapping or historical candles. Missing
steps prevent testnet and guarded-live readiness labels.

Market-class certification rejects an empty or duplicate selection and invalid
timeouts. A selected subset's success is explicitly distinguished from success
across all supported classes. The direct-provider runner rejects unknown
provider names, invalid timeouts and inadequate sample limits. Future data is
not clamped into a fresh certification.

Positive infinity in a provider timestamp previously could keep unit conversion
loops running forever. Market-data and certification normalizers now reject
nonfinite values before conversion. A subprocess regression test includes an
actual deadline to prevent this defect from hanging the full suite.

## Read-only observation monitor

`scripts/production_soak_monitor.py` samples a fixed release's public readiness,
active Railway deployment identities, approval pins, configuration consistency,
kill switches and financial feature flags. It never sends orders, messages or
payments. Railway variable values remain in memory and only their aggregate
configuration hash enters evidence. Failed candidate deployments do not replace
an active approved deployment in the monitor's interpretation.

Every observed timestamp is recorded when sampling actually completes. Missing
samples remain gaps. A gap above five minutes, changed deployment, changed
configuration, failed observation or unsafe execution setting prevents the
availability claim. The target period must be 24-72 hours and the completed
availability verdict requires real observed time.

This monitor does not collect deployed source-byte hashes or authoritative
duplicate-delivery, duplicate-order and runtime-error interval counters. These
fields are explicitly unverified; release-soak and financial-readiness
certification always remain false. Those release gates require richer runtime,
broker and database evidence plus independent review.

A 72-hour local observation process was started on 4 October for the currently
approved production release `8f8583933a853a54ba1b3585610ee466903c08fc`, schema
0045. It samples every three minutes. It measures the current production
baseline; promotion of a new candidate requires its own unchanged observation
window. Local observation requires the host PC and network to remain running.
No 24-hour or 72-hour pass is claimed at startup.

Production remains constrained by database capacity and a verified backup
restore, provider access and freshness, security audit failures, hosted CI,
overall coverage and typing debt, each funded tester's firm policy, actual
broker fills and reconciled exits, native devices and complete audits. A
successful HTTP response or observational availability window cannot satisfy
those separate requirements.
