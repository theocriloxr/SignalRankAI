# Readiness audit repairs and measured limitations

The requested scores are acceptance targets. This audit has not certified all
subsystems at 90 or higher, completeness at 100, enterprise readiness at 97,
institutional maturity at 100, or real-money operation.

## Verified baseline

Frozen candidate `0d641bc6fd217743f7347445887243ed34479e53` passed the full local
2440-test selection with no failures, errors or skips, and 47 browser checks
with no automated WCAG violations. Runtime Python coverage measured across
the same 20 test batches was **37.23% line and 25.84% branch**, substantially
below the requested acceptance threshold. These measurements do not establish
native-device, real-provider, broker-fill, production-failure or soak evidence.

Existing production application roles still ran an older source revision and
schema 0045 when inspected. Verification services ran the frozen candidate;
backend verification passed, frontend and mobile dependency audits failed,
and the static gate failed because Semgrep analysis was incomplete. GitHub
hosted jobs failed before test steps under the account billing restriction.

## New repairs requiring a new immutable candidate

- Explicit failed release evidence overrides an older configured certificate
  ID. Missing engine inventory blocks release, and public-testing configuration
  must pass actual effective database pool limits.
- Load profile hours are converted to seconds. Short or empty runs, HTTP
  throttling/errors, malformed shard counters, inconsistent concurrency and
  nonfinite metrics cannot certify capacity. Long load runs require an explicit
  CLI duration. Seven-day profiles can produce a soak report; passing a
  synthetic report fixture is not an actual soak.
- Generation locks use one canonical scope across engine, Telegram and database
  adapters. Redis Lua atomically checks canonical and historical keys and writes
  a random token with NX and expiry. Redis absence or command failure denies
  acquisition. Release compares the exact token, and task/thread ownership
  prevents inherited child context or a losing contender releasing a winner.
  General cached or asynchronous state writes are not used as lease authority.
- The legacy dedup wrapper imports existing functions, waits for actual async
  checks even inside a running event loop, uses the deduplicator's actual API,
  and cannot report success solely from local memory after lease failure.
- Database errors in legacy active-signal checks block generation.
- SQLAlchemy 2.1 Result, Select and Row annotations use direct column types.
  Nullable Telegram IDs are excluded from Telegram-only queues and broadcasts;
  web-only referrers use canonical user IDs and distinct reward references.
  Legacy performance queries use Signal's actual regime and asset-class
  columns instead of referencing nonexistent Outcome columns.

The new guard decision tests reached 100% line and 95% branch coverage for
`core/release_guard.py`. This is scoped evidence, not an overall core-engine
score. Local database integration includes actual SQL execution for performance
filters, separate web-only referral rewards, idempotent referral replay and
Telegram queue exclusions. The four repaired lock/database modules now join
the zero-error critical typing gate.

The cleanroom verification image includes redis-server and an explicit owned
loopback integration step. The runner clears application credentials, uses a
unique local port and test-key scope, captures tested-source hashes, and stops
its own server. Missing Redis or failed contracts block the step. The default
unit command double is identified separately from actual Redis integration.

## Operating limits and remaining gates

These generation leases are a single Redis instance accelerator. Database
uniqueness and durable delivery/execution idempotency remain necessary across
Redis failover and work exceeding the TTL. A coordinated immutable rollout is
required: historical workers can still write old lock formats. Clustered Redis
with incompatible cross-slot keys denies this script rather than falling back
to local memory. No financial guard is waived by a passing lease test.

Production database storage remained roughly 4.5 GB used of 5 GB. Migration
0046 copies a large legacy table before retiring it, so migration remains
blocked until capacity and restore evidence are adequate. Backup creation is
not restore certification. Temporary Railway SSH registration for downloading
the existing backup awaits explicit owner authorization after automatic
approval review rejected the account-level access change.

Other unresolved gates include dependency vulnerabilities, complete static
analysis, full-runtime typing debt, hosted CI, entitled live provider feeds,
per-tester prop-firm policy verification, actual broker/demo fills and lifecycle
reconciliation, Telegram/web production parity and failure drills, native
device and manual accessibility testing, monitored 24–72-hour soak, and two
complete audits with no new material gaps. Financial activation remains gated.
