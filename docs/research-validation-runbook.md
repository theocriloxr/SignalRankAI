# Research validation and immutable experiment history

## Runtime integration

The analytics role and legacy worker own an independent profile-health loop
(`ADAPTIVE_HEALTH_INTERVAL_SECONDS`, default 60, allowed 15–300 seconds).
Pausing or disabling research does not pause health surveillance.
`AdaptiveLearningWorker` also checks health before starting research. Analytics
supervises its recurring tasks and exits if a task unexpectedly stops; startup
failures cancel and await every task already created.

Publication and suspension share a PostgreSQL transaction advisory lock.
Suspension invalidates the cached approval before releasing that lock and commits
independently of research. Cache approvals carry profile-bound short leases
(150 seconds at the default cadence); outages, invalid leases and expired leases
resolve to neutral weights. This bounds stale cache use during an outage; it
does not prove instantaneous cross-process cache invalidation or Redis write
acknowledgement. Rollback also restores the neutral baseline and requires
revalidation before reactivation.

The operator diagnostics expose the last check as COMPLETED, ERROR, STALE or
UNAVAILABLE. COMPLETED reports a successful monitor iteration, not certified
edge. The current evidence is confirmed signal-delivery outcomes, not broker
fills or account equity. Invalid/nonfinite observations suspend a profile even
below the ordinary sample minimum. Validated per-profile health baselines,
instrument execution evidence and funded-account constraints remain unfinished.

The `RiskManager` spot-unit adviser now forwards account drawdown state into
sizing, preserves zero risk and soft throttles, and rejects malformed inputs or
wrong-side stops. Its 10% quote-notional cap is converted to units by dividing
by entry price. A minimum unit floor cannot exceed the loss budget or revive a
hard stop; floating-point rounding is also checked against both budgets.
Heuristic score/confidence and unvalidated model outputs cannot supply its
probability weight. The new `resolve_calibrated_probability` reuses the canonical
held-out evidence validator. Advice can reduce the configured base risk, with
no increases from regime, sentiment or supplied expectancy. Missing expectancy
does not fabricate a historical estimate.

These changes affect the existing engine adviser and conservative legacy WFO
replay. They do not convert spot units into broker lots/contracts, qualify a
funded account, establish an edge, or replace account/execution kill-switch
checks. The primary dynamic-risk path now shares the bounded probability and
drawdown policy with `RiskManager`. It preserves explicit/environment/profile
zero risk, accepts account mappings, stops at the reached hard drawdown limit
and rejects malformed risk/volatility configuration. Supplied positive
expectancy does not grant a capital increase or mix R units with drawdown
fractions. The primary spot sizing path also applies the 10% quote-notional
ceiling. An enabled asset-class cap cannot fall back to a larger quantity;
tiny valid units are retained for later venue rounding instead of imposing an
invented 0.01 minimum. Wrong-side stops and nonfinite geometry are rejected.
Reward/risk checks select finite targets on the profitable side of the trade,
and the signal freshness budget converts bar minutes to seconds and rejects
implausible future timestamps. Generation-time signals may not yet have a
creation timestamp; this check does not replace provider freshness or
point-in-time research evidence.
The separate legacy threshold sizers and correlation assumptions still require
consolidation and qualification. These advice limits remain unqualified for
broker contracts, commissions, spread/slippage, margin and funded-account rules.

Health reads at most 250 distinct resolved signals per profile in PostgreSQL,
ordered by outcome close time. Multiple component-evidence rows do not multiply
an observation; future closes and closes preceding the decision are excluded.
Component confidence is not a probability and is no longer used for Brier loss.
The monitor reuses the canonical calibration-evidence validator and the existing
Brier implementation, with the training target `r_multiple > 0`. Missing or
unvalidated calibration is reported as UNAVAILABLE, with a null Brier score.
Each calibration version must independently meet the health sample minimum;
the reported Brier score is the worst qualified version, so one healthy version
cannot hide another degraded version. This is a predictive-loss diagnostic,
not a complete calibration or model-baseline comparison. See the
[scikit-learn Brier documentation](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html).

Claimed validated probabilities with malformed values, missing qualification or
nonfinite metrics cause suspension, even below the ordinary sample minimum.
The shared public-display validator also rejects string/boolean probabilities,
noninteger sample counts and negative calibration-loss metrics. Overflowing
delivery metrics produce a suspension with null metrics instead of invalid
JSON. Successful iterations expose bounded profile diagnostics (first 20,
explicit truncation flag); every profile in the query is still evaluated.

Candidate outcome datasets include the timestamp at which an outcome or later
correction became available. Unresolved labels are excluded, rather than
converted into losses or break-even trades. Train decisions and label-availability
timestamps must both precede the validation start minus embargo. Missing label
availability, duplicate observations, nonfinite returns and mixed evidence
classes fail validation. Candidates are partitioned by asset, asset class and
evidence class.

The worker commits a deterministic trial definition before evaluation. A crash
can leave a pending trial, which remains included in the raw count. Terminal
evidence commits with its shadow candidate and WFO report. Identical retries do
not create another variant. Strategy display-name changes do not reset lineage.
Definitions/results reject updates, deletion and truncation at the database
level. This protects ordinary application/database writes; a privileged
database administrator can still alter the database or disable its triggers.

The adaptive worker checks for terminal ledger evidence before reevaluating an
identical trial. Closed failures are preserved and counted as skipped failures;
successful/rejected retries cannot create or overwrite another terminal result.
A changed code/configuration identity may produce a new trial. A new trial that
matches an existing profile is explicitly REJECTED, with its evaluated WFO
report, rather than left falsely pending.

Handled exceptions during WFO and candidate persistence roll back the evaluation
transaction, then record FAILED evidence and the optimization-run failure through
a separate transaction. Each rollback/recording attempt has an eight-second
deadline. Persisted failure diagnostics include the bounded exception class and
stage, never the exception message. A concurrently committed terminal result
is preserved. If failure recording itself is unavailable, the worker rethrows
the original error, emits a recording-failure diagnostic and retains the already
committed definition as pending. Process termination/cancellation can also leave
pending definitions; no synthetic terminal result is manufactured. This handler
does not certify recovery from every runtime or database failure.

The existing grid optimizer and Optuna tuner require a trial recorder. Use
`engine.adaptive.research_ledger.run_recorded_search` around a callable that
supplies its recorder to the optimizer. It runs the existing optimizer in a
worker thread, commits each STARTED event before calling the objective, then
records COMPLETED or FAILED evidence. Required provenance includes dataset,
feature/label/execution/risk versions, code commit, seed and scopes. A recorder
or database failure stops the search. There is no unrecorded fallback or model
activation. This adapter must run with real thread execution; unit-test helpers
that inline `asyncio.to_thread` are unsuitable for its integration test.

## Statistics and evidence units

Deflated Sharpe requires uniformly spaced excess returns, an explicit
annualization basis, a raw trial count and cross-trial Sharpe variance. Its
skew and kurtosis convention is Pearson kurtosis, not excess kurtosis. The raw
trial count is retained as the effective count without a dependence discount.
Its lag-one serial-dependence screen is only a screen, not proof of independent
observations. CSCV PBO requires aligned common observations for all candidates,
equally sized partitions and nonconstant trial series. It supplements, rather
than replaces, chronological validation.
CSCV also rejects oversized matrix/partition workloads before copying the
observations (at most two million candidate-observation visits). Boolean
observations cannot masquerade as numeric trade returns. The report records
its work count and method version; it never drops candidates to fit the budget.

Irregular trade R is not daily equity return. Its descriptive report therefore
does not invent annualized Sharpe. Drawdown duration is measured in observations
and explicitly labelled. The seeded moving-block bootstrap is conditional on
observed R and a declared risk fraction; it cannot prove survival against
unobserved gaps, liquidity crises or funded-prop rules.

Profit factor uses one canonical gross-win/gross-loss calculation. A sample
without observed losses reports `null` with a reason, including each WFO fold;
it never substitutes 999 or infinity. If any fold lacks a denominator, the
worst-fold factor is unavailable and that fold does not count as qualified
positive evidence. Numerical overflow fails evaluation.

The existing `DynamicSizer` is spot-unit advice, not instrument-specific broker
sizing. It requires a supplied historical win-rate estimate independently of
model confidence, blocks nonpositive Kelly edge and nonfinite inputs, and
reports the risk actually implied by its suggested units. It does not verify
that estimate's provenance. Venue/contract specifications, estimation
uncertainty and per-account/portfolio risk limits still require validation;
this helper cannot certify funded-prop suitability or authorize execution.

The adaptive outcome-weighting proxy cannot verify quote replay, historical
universe membership, point-in-time feature calculations, instrument costs,
historical search completeness or supported-regime coverage. The deterministic
auditor records these as blocking `UNVERIFIED` evidence. These candidates remain
SHADOW and are not eligible for financial promotion.

The legacy WFO runner now trains only on earlier, closed training observations.
Its replay uses post-decision observations, correct orderbook sides, available
liquidity, adverse entry/exit slippage, commissions on both notionals and
stop-first resolution of same-bar ambiguity. Unverified limit queues receive
no optimistic fill. Its current spot-unit simulation is not multi-asset broker
certification; contract/tick values, borrow, swap, funding and venue-specific
costs remain unverified.

## Operator diagnostics and authorization

`GET /api/v1/platform/operator/research` is OWNER/ADMIN-only and reads the canonical
ledger. `/research [asset]` uses the same snapshot for configured Telegram
owners/admins. Neither interface accepts client-supplied performance results or
promotes a strategy. The JSON snapshot includes hypothesis/version lineage,
specification, raw family counts, terminal status and immutable result hashes.

The existing web control room displays that snapshot in an OWNER/ADMIN research
panel. It supports asset filtering, retry after a failed read, hypothesis lineage,
failed/pending trials, statistical units and blocking integrity findings in both
themes and mobile viewports. Family counts retain all assets even when the trial
list is filtered. This is diagnostic access; there is no financial promotion
control. Owner-only maintenance failures no longer prevent an ADMIN from loading
permitted research diagnostics.

The required `research-browser-ui` CI gate uses a disposable owned PostgreSQL
database, actual HTTP authentication and synthetic observations. It checks both
themes on desktop and mobile, filtering, injected read failure/recovery, escaped
untrusted hypothesis text and customer access denial. Browser tooling is isolated
from the locked runtime to avoid changing its dependency versions. Reproduce it
with a loopback test `DATABASE_URL`, `APP_ENV=test`, and:

```sh
python scripts/run_research_browser_drill.py --output-dir artifacts/research-browser
```

Use `--browser-python` for an isolated interpreter containing
`requirements-browser-tests.txt` and an installed Chromium. The runner stops only
its own HTTP process and removes only its own uniquely named test database.
Reports label synthetic observations and distinguish a dirty checkout from an
immutable candidate. This gate does not replace native-device or broker testing.

## Schema 0050 deployment and recovery

1. Pass the required `backend-research-validation` release gate, including real
   PostgreSQL tests. Hosted CI creates disposable owned databases and migrates
   each from an empty schema; the suite's database is not destroyed.
2. Preserve a tested backup and apply the normal controlled migration path to
   `0050_profile_health_index`. Verify all three research tables and six enabled
   append-only/truncate guards on their expected relations and function. Both the
   startup gate and runtime readiness fail if any guard is disabled or misplaced.
   Verify the valid, ready, nonunique B-tree index
   `public.ix_adaptive_evidence_profile_signal` on
   `public.adaptive_signal_evidence (profile_id, signal_id)`. An identically
   named index on another relation, reversed keys, expressions, a partial
   predicate or included columns does not satisfy admission. Both gates use
   the same catalogue predicate; runtime checks retain one database round trip.
   Do not deploy a different commit per service.
3. Deploy only after every existing required release/approval gate passes.
4. If candidate execution is degraded, suspend it and use the neutral baseline.
   Older approvals require fresh validation before reactivation.
5. Do not downgrade 0049 to erase evidence or 0050 to remove surveillance
   support. Their downgrades deliberately fail.
   Use a forward repair or an approved recovery that preserves experiment
   history. A restore/retention policy for this new evidence is still required.

Migration 0050 builds its index concurrently, outside a transaction. Alembic's
autocommit block commits preceding revisions before starting the build, so a
failed build does not roll back earlier revisions. Retry the same migration:
a correctly defined valid/ready index is reused, and a correctly defined
invalid index left by a cancelled concurrent build is dropped concurrently
and rebuilt. A name collision or different definition blocks migration and
requires a reviewed forward repair; it is never automatically dropped.
The index supports the bounded surveillance query but is not a measured
production-latency guarantee. Full capacity and account qualification remain
separate requirements.

Migration environment loading now respects `SIGNALRANK_ALLOW_DOTENV=0`, defaults
to no dotenv access on production/Railway, and never lets `.env.local` overwrite
an explicitly selected `DATABASE_URL`. This avoids redirecting an isolated
migration into a different database.

## Relevant configuration

Existing variables remain authoritative: `ADAPTIVE_OPTIMISATION_ENABLED`,
`ADAPTIVE_MIN_OUTCOME_SAMPLES`, `ADAPTIVE_LOOKBACK_DAYS`,
`ADAPTIVE_WFO_MINIMUM_TRAIN_ROWS`, `ADAPTIVE_WFO_VALIDATION_ROWS`,
`ADAPTIVE_WFO_EMBARGO_SECONDS`, `ADAPTIVE_WFO_COST_R`,
`ADAPTIVE_DRIFT_MIN_LIVE_SAMPLES`, `ADAPTIVE_DRIFT_MAX_DRAWDOWN_R`,
`ADAPTIVE_DRIFT_MAX_BRIER`, `ADAPTIVE_DRIFT_MIN_EXPECTANCY_R`,
`ADAPTIVE_DB_TIMEOUT_SECONDS`. Promotion uses the versioned server-side
`PromotionPolicy`; callers cannot supply a weaker policy through the operator
command. Defaults are governance thresholds, not statistically demonstrated
universal constants. Per-instrument approved policies remain to be integrated.

`APP_ENV=test`, loopback PostgreSQL, `SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED=1`,
`SIGNALRANK_ALLOW_DOTENV=0` and disabled financial flags are mandatory for the
isolated integration runner. Unknown historical trial coverage remains visible
as `since_ledger_introduction`, with prior history unverified.

## Remaining research directive gaps

The Google Doc review is blocked by inaccessible content. Complete the
instrument-specific execution/capacity stress matrix, supported/disabled regime
policies, point-in-time universe/revision evidence, ML search integration at all
call sites, approved health baselines/decay analysis, portfolio interaction
validation, full operator UI, telemetry/alert retention, feature/pivot/repainting
tests and per-asset statistical qualification. No result in this candidate
certifies profitable trading or enables real-money execution.
