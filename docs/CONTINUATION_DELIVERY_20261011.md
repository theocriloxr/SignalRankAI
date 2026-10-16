# Delivery incident recovery, 11 October 2026

Production was inspected with read-only SQL and actual active-deployment logs.
The four application roles still serve approved commit
`8f8583933a853a54ba1b3585610ee466903c08fc`, schema0045. The continuation branch
is a separate candidate; healthy old replicas do not certify it.

At 14:27 UTC, the last confirmed Telegram delivery remained 6 October 14:13 UTC.
Two canonical signals were stored on 11 October, but were subsequently expired.
The 10:49 BTC signal passed the ML gate and was stored successfully; its live
price had crossed its short stop before fan-out. Retry then rejected it at
22.6 seconds against the existing 20-second queue limit. Other recipients were
blocked by TERMS_REQUIRED. The current 14:27 scanner sample had 90 ideas,
10 strict candidates and zero model passes. These are distinct admission,
opportunity and recipient problems; no threshold or terms bypass is justified.

## Candidate repairs

- Retry selection checks age and queue freshness before deduplicating asset/
  timeframe buckets and applying its existing delivery limit. Nonfinite scores
  and incomplete identities cannot displace qualified retries.
  Optional stale-row housekeeping is deferred when fresh work exists; other
  passes bound its writes by the existing resend count instead of writing for
  every stale row before checking the send deadline.
- Engine fan-out validates shared opportunity state with the existing typed
  quote/final-delivery contract before per-recipient database work. Empty or
  failed prefilters stop immediately. Each eventual send still performs its
  own account, entitlement, quota, profile, deduplication and live-quote checks.
- Only analytical age expiry can expire the analytical signal in this shared
  prefilter. Provider failures, queue expiry and missed entry do not rewrite
  analytical monitoring or outcome authority.
- Background fan-out binds its original cycle's top-level candidate copies,
  recipient tuple and telemetry dictionary. Its cleanup wrapper binds the
  original coroutine and compare-and-delete lock token. Later scanner iterations
  cannot substitute their batch or release another cycle's lock. This does not
  establish deep immutability of every nested legacy signal payload.

Regression tests exercise real freshness/quote contracts and the actual engine
coroutines delayed across simulated next-cycle changes. Synthetic quotes and
market sessions are explicitly local tests, not provider or delivery evidence.

## Production and release boundaries

The read-only provider verifier was found blocked before its script ran:
runtime c7684b34178b differed from expected 56004770b333. Recovery pins that
diagnostic service and its expected source to the already approved production
commit; it does not approve the continuation candidate or execute orders.
The verifier is a one-shot, restart NEVER service, so a completed run need not
have a running replica. Certification results must be read from its actual
new deployment and cannot be inferred from Railway's Online display.

Current required mobile audit remains red with four high dependency rows.
The primary advisory for node-forge <=1.4.0 still lists no patched version:
https://github.com/advisories/GHSA-86w9-cpqp-85rv . No audit exception or gate
waiver was introduced. Candidate production rollout, all-class provider
acceptance, account-specific demo/prop execution, installed native devices,
fresh candidate staging soak and two clean full audits remain unverified.
Financial flags remain OFF and kill ON. Terms acceptance belongs to each
customer and must not be fabricated by an operator or repair script.
