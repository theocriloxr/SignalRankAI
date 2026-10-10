# Signal delivery and challenger evidence recovery, October 10

This increment repairs evidence collection and qualification behavior. It does
not establish production recovery, model promotion, broker acceptance or live
financial readiness. The release remains PR #189 on
`fix/release-recovery-20261008`, continuing published parent `19bc91cc`.

## Production observations

Read-only Railway logs and database queries found all four serving application
roles running source `8f8583933a853a54ba1b3585610ee466903c08fc` against schema
`0045_mt5_credential_retirement`. The engine, delivery/paper worker and Telegram
front door are active. Telegram reports no active signals to resend. In one
observed batch, 108 strategy ideas became 13 strict candidates, with zero ML
passes. Analytics repeatedly reports drift and zero approvals in 512 recent
predictions. The old champion's certified raw cutoff remains 0.84; changing the
environment's 0.50 fallback does not replace that certified cutoff.

The primary artifact `48bce7fbf31461e94faabfb064c1026f06049731e5b60145ef7fec44ef1ad434`
still uses the score features excluded from the newer v4 training contract.
The newer candidate `2c18074f2bd62f7247120adba320e28959c1011806ad1c3ae3cb224a2cbff06d`
has recorded offline AUC and calibration regressions and is explicitly not
admitted to forward promotion. Its existence is not permission to serve it.

`REJECTION_LOG_WRITE_ENABLED=0` on the engine and both worker shadow-tracker
switches are zero on delivery. Production still has a physical rejection table,
while the serving source's batch writer uses DecisionLog. The newest successful
delivery with `sent_ok IS TRUE` is October 6 at 14:13:32 UTC. A non-null delivery
timestamp alone is insufficient evidence: the broader timestamp-only query
returned a later October 8 value. The count of confirmed successful receipts in
the inspected table is 486; the larger timestamp-only count includes unconfirmed
records. These observations do not identify any tester's personal account.

Financial execution remains disabled, the global kill switch remains enabled,
and paper trading is already configured on. No production variables, source
pins, schema, deployments or customer records were changed during this diagnosis.

## Implemented repair

- Rejection batches inspect the actual PostgreSQL relation and write one physical
  owner: the legacy table before 0046, the DecisionLog owner of the computed view
  after 0046. Unknown/missing storage defers the batch rather than discarding it.
- Recording returns an explicit queue acknowledgement. Disabled recording cannot
  consume the challenger's six-hour duplicate window; declined or failed
  submissions release their claim. The process cache is synchronized and bounded
  at 4,096 entries even before entries expire. A queue acknowledgement is never
  described as durable evidence.
- Forward queries apply artifact and observation-type filters before the row
  limit. They snapshot plain values before rollback, avoiding detached ORM reads.
  Pending observations enter the observation/pass-rate denominator, but only
  chronologically available tracked outcomes enter resolved results and class
  coverage. Future decisions and future labels cannot qualify a model.
- Excess cohort history fails qualification instead of selecting an apparently
  favorable truncated subset. Invalid, nonfinite or reversed trade geometry
  cannot improve statistics. No-loss profit factor remains undefined and cannot
  satisfy the profit-factor gate.
- Engine cycle diagnostics and the existing owner pulse expose disabled or
  failed challenger recording. Forward results explicitly label their statistics
  as `shadow_barrier_labels_gross_of_costs`: these are not broker fills, net
  portfolio performance or live-money acceptance.

The actual PostgreSQL regressions exercise the legacy physical relation and
the current migration view, failed commit/retry, artifact filtering amid more
than 100 unrelated records, pending/future evidence and cohort overflow. Unit
checks cover disabled/re-enabled recording, refused/failed submissions, cache
capacity, invalid geometry and operator diagnostics. The PostgreSQL cases are
included in the mandatory release manifest; the forward governor is included
in critical typing. No quality threshold, promotion authorization or financial
guard was relaxed.

## Remaining recovery and acceptance

The production inventory and runtime scan covers all 18 resources using two
explicit service groups within the connector's ten-service limit. The four
serving roles have one running replica each; PgBouncer has three. Three historical
verification services are offline. The provider-certification job reports
`SUCCESS`/`Online` but has zero running replicas and one crashed replica. Its
prior source-guard failure is not a provider-certification pass. The backup cron's
last execution succeeded on October 10 at 02:03:33 UTC. PostgreSQL's volume is
20,000 MB; the former 5 GB capacity is no longer the current allocation.

The read-only availability monitor now queries `serviceInstance.activeDeployments`
with `deploymentStopped` and actual replica states. Deployment history or CLI
service status alone cannot prove liveness: service status selects the latest
failed attempt even while an older approved application is running. Exactly the
configured number of distinct replicas must be running; removed historical
replicas are ignored, and crashed, pending, unknown, missing or excess replicas
interrupt the window. Existing successful deployment badges cannot hide a stopped
job. This does not convert availability monitoring into release-soak acceptance.

The published recovery checkpoint `6e52b42d` passed all 3,445 local tests and both
hosted Python 3.11/3.12 suites, with no failures or skips and unchanged clean
source identities. Hosted frontend, static and browser checks passed. Mobile
typing and its 44 dependency/flow checks passed, but its four high dependency
audit rows still fail aggregate release certification. These results precede the
additional monitor repair described above; successor verification is required.

The production configuration switches still require a controlled operational
change after the corrected source is qualified and deployed. Re-enable recording
on the engine and the canonical delivery shadow tracker, then verify new durable
observations and genuine tracked labels. Preserve the failed candidate and
champion evidence; qualify a valid replacement using the required offline,
forward, schema and explicit approval gates. Do not manufacture signals to
satisfy a schedule or turn off model admission to clear a symptom.

PR #189 still requires exact-source hosted release gates, including the unresolved
mobile dependency security gate. Candidate migration/restore, isolated staging,
actual provider and demo-broker lifecycle tests, installed native acceptance,
fresh continuous 24–72-hour soak and two complete clean audits remain unfinished.
The larger research, customer, design, routing and resilience completion backlog
also remains. Healthy old application instances do not certify this successor,
and current delivery evidence does not authorize live financial activation.

Raw credentials and customer records were not exported. Filtered incident
receipts are retained in the workspace under `artifacts/ui-refresh-20261003/`:
`signal-outage-diagnostics-20261010.json`, `signal-outage-followup-20261010.json`
and `signal-outage-confirmed-20261010.json`. The initial follow-up retains the
failed plural-table query; the confirmed successor uses the actual
`decision_log` table and `sent_ok IS TRUE` delivery filter.
