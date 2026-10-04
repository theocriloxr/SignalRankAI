# Production recovery and next audit repair, 4 October 2026

The latest published candidate at this checkpoint is
`abc83e91c33232ad32eaede9bb56c402b7c25cbd`. It is not approved for financial
execution or promoted to the production business roles.

## Deployment trigger and recovery

The four production business services watched only `production-release/**`.
Changes elsewhere in the authorized branch were consequently skipped. Their
watch filters now cover `**`.

Enabling that trigger exposed an unsafe promotion path: the three standalone
background roles lacked pre-deploy source checks. Their candidate containers
were promoted and subsequently exited when their startup source gates rejected
the unapproved commit. An attempted recovery with `/readyz` also failed because
these standalone processes have no HTTP listener. That unsupported probe was
removed; it must not be described as working background readiness protection.

The worker, engine and analytics roles were restored to the previously approved
`8f8583933a853a54ba1b3585610ee466903c08fc` release. Railway reported SUCCESS for:

| Role | Recovery deployment |
| --- | --- |
| Worker | `ef4ab249-69d9-422b-8bd7-63ec2d4c5051` |
| Engine | `8cf04d53-d920-493e-b143-d781c1c4abfc` |
| Analytics | `c4212558-d34f-41ea-97fb-3f258aac5564` |

Each background service now runs both read-only admission commands before
promotion: `python scripts/assert_release_source.py && python
scripts/assert_database_schema.py`. The frontdoor retains its guarded migration
pre-deploy command and actual HTTP `/readyz` check. Production remains at schema
0045; the latest candidate expects 0048. Database capacity and a verified restore
remain prerequisites for that migration. No production records were deleted,
schema gates relaxed, or financial switches enabled during recovery.

## Evidence on the published candidate

- Full local suite: 2,528 passed; no failed, skipped or unparsed batches, and
  source identity remained unchanged during the run.
- Local HTTP browser verification: 47 checks passed; automated accessibility
  scan reported zero violations. This uses a synthetic user and local PostgreSQL,
  and does not establish native-device or production-user certification.
- Hosted isolated backend: 807 tests passed, plus 31 contracts against an owned
  real Redis 8.0.2 process. The verifier stopped its own server and used no
  production connections. Financial readiness was explicitly not certified.
- Critical typing: 32 files passed. Full runtime typing still reports 1,214
  local errors (1,210 on the Linux static verifier), plus six warnings.
- Frontend dependency audit: five high findings. Mobile: sixteen high and seven
  moderate. Neither build passed its security gate.
- Static gate: Python dependencies passed their vulnerability audit, but
  Semgrep's incomplete taint analysis blocked certification despite zero
  reported findings.
- GitHub CI run `37174325607`: failure with no executed job steps. It is not a
  hosted certification pass.

The previous full coverage measurement remains roughly 37% line and 26%
branch coverage. Passing test counts cannot replace coverage, runtime financial
evidence or the requested score targets.

## Additional deduplication repair

The semantic and strict history checks previously returned clearance after
database admission, query or transaction-exit errors. They now block a candidate
when history cannot be verified. Recent-history APIs raise an explicit sanitized
authority-unavailable error instead of returning an empty list. A capped query
cannot establish absence beyond its last returned row.

BUY/LONG and SELL/SHORT aliases are canonicalized in checks and strict batches;
queries include historical aliases. Invalid entries and invalid scopes do not
receive dedup clearance. Dictionary signal payloads have mapping types rather
than incorrect ORM-model annotations. Sparse rejection tracking returns zero
and its nullable metadata is handled explicitly. Regression coverage includes
fault injection and actual PostgreSQL reads. This repair is independently
validated before publication; it does not authorize live trading.

Remaining launch gates include database headroom and restore evidence, dependency
security repairs and complete static analysis, hosted CI, overall coverage and
typing debt, entitled market feeds, each tester's funded-account firm rules,
broker fills and reconciled exits, failure and recovery drills, native devices,
a monitored 24-72-hour soak, and two complete audits with no new material gaps.
