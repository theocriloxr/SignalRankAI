# SignalRankAI v1.3.0 — Production Cutover and Outcome Recovery

Release date: 2026-07-30  
Fingerprint: `v1.3.0-production-cutover-outcome-recovery-20260730`

## Why v1.2.9 stopped delivering signals

The supplied Railway log proves the signal engine was generating viable candidates, but none reached storage or dispatch. The causal chain was:

1. The active Alembic chain ended at `0027_launch_paper_trading` and did not contain the historical outcome uniqueness migration.
2. `upsert_outcome()` issued `ON CONFLICT (signal_id)`, but PostgreSQL had no unique or exclusion constraint on `outcomes.signal_id`.
3. Outcome writes failed 514 times in the supplied log.
4. Five proof-backed delivered signals therefore remained unarchived and occupied the global portfolio limit.
5. The portfolio gate blocked 510 otherwise-valid candidates at `5/5` open trades.
6. The engine still generated strategy candidates and scores near 95, but every observed cycle reported `stored=0` and `dispatched=0`.
7. The deployment was still an acknowledged staging deployment with `PUBLIC_TESTING_MODE=1` and a two-user delivery allowlist.

## Production repairs

### Database and lifecycle

- Added active migration `0028_outcome_projection_guard`.
- Reconciles duplicate outcome projections deterministically.
- Repoints `outcome_notifications.outcome_id` before removing duplicate outcomes.
- Repairs a same-name non-unique index if schema drift created one.
- Creates the unique PostgreSQL index `uq_outcomes_signal_id`.
- Makes `0028_outcome_projection_guard` the sole Alembic head.
- Adds the corresponding ORM uniqueness contract.
- Replaced the fragile PostgreSQL `ON CONFLICT` outcome writer with:
  - a per-signal PostgreSQL transaction advisory lock;
  - a row-level `FOR UPDATE` lock;
  - deterministic update-or-insert behavior;
  - retained notification and metadata progression behavior.
- Outcome persistence can now recover even before the uniqueness guard is inspected, while the database constraint permanently prevents races.
- Terminal reconciliation continues to archive terminal signals, which releases portfolio capacity.

### Production/public cutover

- Production runtime forcibly clears inherited staging state:
  - `PUBLIC_TESTING_MODE=0`;
  - `FULL_SYSTEM_STAGING_TEST_MODE=0`;
  - `FULL_SYSTEM_STAGING_TEST_ACTIVE=0`;
  - blank `DELIVERY_AUDIENCE_ALLOWLIST`;
  - `RESEND_AUDIENCE_ALLOWLIST_ONLY=0`;
  - `FREE_RANDOM_DISTRIBUTION_ENABLED=0`.
- `/readyz` now rejects empty or `<...>` example credentials and returns HTTP 503 unless:
  - Railway's authoritative environment is `production` or `prod`;
  - testing/staging mode is disabled;
  - no delivery allowlist is active;
  - public free-signal distribution is enabled;
  - both engine and worker loops are enabled;
  - state and delivery Redis services are configured and distinct;
  - public payments use a matching live Paystack key pair;
  - database revision is exactly the sole repository head;
  - outcome duplicates are zero;
  - `uq_outcomes_signal_id` exists and is unique.
- The production profile uses a normal global eligibility query instead of a user-ID allowlist.
- Portfolio exposure also fails closed when both PostgreSQL and Redis exposure truth are unavailable.
- Real-money broker execution, copy trading, live MT5 accounts, Bybit execution, and real payouts remain fail-closed.

### Market-data corrections

- TradingView scraping is disabled in the production profile because the supplied run repeatedly exhausted its unauthenticated rate limit.
- Yahoo symbol routing now maps:
  - `WTI`, `USOIL`, `OIL`, `CRUDEOIL` → `CL=F`;
  - `BRENT`, `UKOIL` → `BZ=F`;
  - `GER40` → `^GDAXI`;
  - `UK100` → `^FTSE`;
  - `FRA40` → `^FCHI`;
  - `US500` → `^GSPC`;
  - `NAS100` → `^NDX`;
  - other supported broker-index aliases to their correct Yahoo indices.
- Corrected malformed FX fallback formatting from `EURUSDX` to `EURUSD=X`.
- Commodity symbols are now classified as `commodity` in portfolio exposure accounting.

## Deployment contract

Deploy the complete v1.3.0 archive as a full replacement. Railway's `preDeployCommand` runs:

```bash
python -m alembic upgrade head && \
python scripts/deployment_diagnostics.py --phase predeploy --strict-core \
  --output /tmp/signalrank_predeploy_diagnostics.json
```

The application will not become ready if migration `0028` or its unique guard is missing. Replace every `<...>` value in the production environment profile before deployment; placeholders are documentation, not runnable credentials.

Expected boot marker:

```text
[boot] SignalRankAI v1.3.0 ... env=production release=v1.3.0-production-cutover-outcome-recovery-20260730
```

Expected recovery markers:

```text
[outcome_tracker] Outcome persisted:
[readyz] ... production_cutover ... public_production
```

Forbidden after deployment:

```text
no unique or exclusion constraint matching the ON CONFLICT specification
Portfolio maxed out (5/5 trades)   # may appear only if five positions are genuinely still open
FULL SYSTEM STAGING TEST MODE active
delivery audience allowlist active
```

## External boundaries

The code can make Telegram onboarding and signal delivery globally eligible, but it cannot guarantee Telegram reachability, payment acceptance, market-data availability, or legal eligibility in every country. Paystack acceptance remains subject to Paystack's supported cards, currencies, countries, account approval, and live credentials. Real-money execution stays disabled until broker-specific live certification and jurisdictional controls are completed.
