# Live Production Evidence Runbook

Use this runbook to close the remaining public-launch proof gaps. It is designed
for Railway monolith deployments with Postgres and Redis.

## Evidence Command

Run on Railway or locally with the same environment variables:

```powershell
python scripts/live_production_evidence.py --days 30 --provider-smoke --json-out live-evidence.json
```

For local testing with a dotenv file:

```powershell
python scripts/live_production_evidence.py --env-file .env --days 30 --provider-smoke --json-out live-evidence.json
```

The script exits `0` only when every evidence gate passes. It exits nonzero when
anything is failed or skipped.

## What It Proves

### Production Readiness 90+ Evidence

`readiness_90_evidence=true` means:

- required Railway env exists;
- Postgres query succeeds;
- Redis read/write succeeds;
- public `/health` succeeds when URL env is configured;
- outcome coverage is high enough to estimate win rate;
- provider OHLC smoke passes across configured asset classes;
- broker execution evidence is not skipped.

Do not raise all scorecard rows to 90+ unless `readiness_90_evidence=true` and
the evidence file is retained.

### Railway Live Behavior

The script checks:

- `DATABASE_URL`;
- `REDIS_URL` or `REDIS_PRIVATE_URL`;
- `TELEGRAM_BOT_TOKEN`;
- `OWNER_IDS`;
- optional `PUBLIC_BASE_URL`, `RAILWAY_PUBLIC_DOMAIN`, or `RAILWAY_STATIC_URL`.

### Provider OHLC and Market-Hours Proof

Run with `--provider-smoke`.

Default representative symbols:

- `BTCUSDT:crypto`
- `EURUSD:forex`
- `XAUUSD:commodity`
- `AAPL:equity`
- `SPY:indices`

Override:

```env
LIVE_PROVIDER_SMOKE_ASSETS=BTCUSDT:crypto,EURUSD:forex,XAUUSD:commodity,AAPL:equity,SPY:indices
```

Closed non-crypto markets are treated as valid market-hours skips. Open markets
must return real OHLC candles.

### Broker Execution Proof

The script checks linked MT5 credentials and encrypted exchange links. It does
not place any order by default.

Sandbox order execution requires a separate explicit safety flag:

```env
BROKER_SANDBOX_ALLOW_ORDER=I_UNDERSTAND_THIS_PLACES_A_SANDBOX_ORDER
```

Do not set this against a live account. Use a broker sandbox/demo account only.

### Outcome Tracking and Expected Win Rate

The script computes:

- delivered signals;
- tracked outcomes;
- coverage percentage;
- wins;
- losses;
- observed win rate;
- Wilson 95% confidence interval;
- per-asset-class breakdown.

Default reliability gate:

```env
EXPECTED_WIN_RATE_MIN_COVERAGE=0.80
EXPECTED_WIN_RATE_MIN_TRACKED=100
```

If coverage is below the gate, the expected win rate is not considered reliable.

## Scorecard Rule

Only update `docs/PRODUCTION_READINESS_SCORECARD.md` to minimum 90 after:

1. `python scripts/production_readiness_check.py` passes.
2. `python scripts/live_production_evidence.py --provider-smoke` exits `0`.
3. Broker sandbox execution is proven with non-live accounts.
4. The generated evidence JSON is archived.

Until then, keep lower subsystem scores and list missing live evidence honestly.
