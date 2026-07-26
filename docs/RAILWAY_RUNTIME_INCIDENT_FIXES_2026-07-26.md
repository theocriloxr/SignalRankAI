# Railway Runtime Incident Fixes — 2026-07-26

## Incident evidence addressed

The Railway runtime showed:

- the engine calling an async circuit-breaker from `ThreadPoolExecutor-0_0` with no event loop;
- CryptoCompare/Binance WebSocket restart storms;
- Telegram `/telegram/webhook` returning unexplained HTTP 503 responses;
- a missing `decision_log.created_at` column;
- critical outcome tracking timing out on DB admission;
- new SQLAlchemy engines appearing on successive scheduler event loops;
- waitlist jobs unavailable;
- proxy validation calling `https://example.com/proxies`;
- FREE distribution queuing signals during an owner-only validation run;
- boot metadata reporting `build=unknown`.

## Implemented corrections

### Engine circuit breaker

`engine/core.py` no longer calls `asyncio.get_event_loop().run_until_complete()` in the engine thread. It uses the repository's shared async bridge with a bounded timeout.

`engine/market_circuit_breaker.py` now obtains the BTC reference through the configurable REST order:

```env
CIRCUIT_BREAKER_PRICE_PROVIDERS=coinbase,okx,binance
```

The failure of Binance in one region no longer removes every circuit-breaker price source.

### WebSocket isolation

`config.py` now requires both flags before WebSockets can start:

```env
WS_INGEST_ENABLED=1
CRYPTO_WS_ENABLED=1
```

Both default to `0`. `worker/worker.py` logs that REST remains authoritative when WebSockets are disabled.

### Telegram webhook diagnostics

The webhook route now logs a structured rejection reason and queue snapshot for every non-200 response. `/readyz` also fails when the webhook secret is missing on Railway.

Examples of explicit reasons:

- `webhook_secret_not_configured`
- `invalid_webhook_secret`
- `queue_full`
- `invalid_payload`

### Database diagnostics and lifecycle priority

The outcome tracker uses the stable label:

```text
outcome_tracker.fetch_active_signals
```

DB sessions are recorded in an active-holder registry. Admission timeouts now include:

- priority snapshot;
- active holders and hold duration;
- caller labels;
- session metrics;
- engine inventory.

A stale `SIGNALRANK_DISABLE_BACKGROUND_THREADS=1` is ignored on Railway, preventing each scheduler invocation from creating a new short-lived event loop and SQLAlchemy engine.

### Schema readiness

`railway.json` now runs:

```bash
python -m alembic upgrade head
```

before every deployment. `/readyz` verifies both the sole migration head and the required `decision_log.created_at` column.

### FREE distribution safety

FREE distribution and the delayed FREE queue are now explicit opt-in features. Their default is disabled.

```env
FREE_RANDOM_DISTRIBUTION_ENABLED=0
FREE_SIGNAL_DISTRIBUTION_ENABLED=0
```

Already queued rows can be inspected safely:

```bash
python scripts/quarantine_free_signal_queue.py
```

Quarantine them only after reviewing the dry run:

```bash
python scripts/quarantine_free_signal_queue.py --apply --status suppressed
```

### Proxy validation safety

Proxy discovery defaults to disabled and never contacts a placeholder URL. It requires:

```env
PROXY_VALIDATION_ENABLED=1
PROXY_API_PROVIDER_URL=https://real-provider.example/api
```

### Waitlist jobs

Waitlist jobs moved to `services/waitlist_jobs.py`, avoiding import of the full web application merely to register scheduler jobs. Import and runtime failures now include complete tracebacks.

### Build identity

The boot banner reads Railway's commit and deployment variables:

- `RAILWAY_GIT_COMMIT_SHA`
- `RAILWAY_DEPLOYMENT_ID`
- `RAILWAY_ENVIRONMENT_NAME`

## Deployment diagnostics

The pre-deploy command runs the new evidence-first audit:

```bash
python scripts/deployment_diagnostics.py \
  --phase predeploy \
  --strict-core \
  --output /tmp/signalrank_predeploy_diagnostics.json
```

After startup, Railway runs a one-time read-only runtime diagnosis when:

```env
DEPLOYMENT_DIAGNOSTICS_ENABLED=1
```

The report distinguishes:

- `PASS`
- `FAIL`
- `WARN`
- `BLOCKED`
- `SKIPPED`

Missing credentials are never treated as passed tests.

For the full hermetic suite and live provider certification, use an isolated staging certification service:

```bash
python scripts/deployment_diagnostics.py \
  --phase full \
  --run-full-suite \
  --live-providers \
  --continue-on-failure \
  --output /tmp/signalrank_full_diagnostics.json
```

Do not run the deep suite in the customer-facing monolith during normal traffic.

## Additional queue and scanner diagnostics

The runtime audit now inspects Telegram Redis Stream consumer-group lag, pending age, dead letters, legacy webhook-list items and the state-side signal-dispatch list. This closes the diagnostic gap behind the unexplained webhook `503` and the Railway report of pending delivery work.

The report also inventories advanced code/security scanners and runs them when explicitly enabled in an isolated certification service. Missing tools or credentials are reported as `BLOCKED`; they are never silently counted as successful.
