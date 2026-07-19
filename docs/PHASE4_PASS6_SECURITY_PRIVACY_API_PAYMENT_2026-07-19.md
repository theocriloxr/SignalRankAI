# Phase 4 Pass 6 — Security, Privacy, API, and Payment Boundaries

Date: 2026-07-19  
Baseline: Phase 4 Pass 5 canonical replacement  
Status: Complete

## Objective

Restore one ASGI web boundary and close the API, broker-credential, token, and
payment compatibility gaps that prevented the security contract from being
tested. Safety-sensitive behavior remains opt-in and fail-closed.

## Implemented

- Restored the canonical FastAPI web application. The previous Flask shim was
  not callable by Uvicorn or `httpx.ASGITransport`, and silently removed the
  health, broker, token, and Paystack routes.
- Exported `verify_api_key` from `web.app` as a compatibility dependency.
  Missing/invalid credentials return `401`; an unavailable token database
  returns `503` for safe retry. Bearer and `X-API-Key` credentials are both
  accepted.
- Mounted the versioned `web.api` router at `/api/v1` in the process-owned web
  app and retained unversioned token lifecycle aliases for migration.
- Kept broker permission validation trade-only: read + trade are required and
  withdraw/transfer permissions are rejected. Exchange secrets are Fernet
  encrypted and only a bounded key mask is returned.
- Preserved rate-limit policy responses instead of swallowing `429` errors.
- Made Paystack entitlement mutation explicitly opt-in through
  `PAYMENTS_ENABLED=true` (default off); raw-body HMAC uses the current secret
  with constant-time comparison.
- Routed Paystack activation through the canonical idempotent repository
  transaction and rejected events without a reference, positive amount, or
  supported NGN currency.

## Verification

```text
python -m pytest tests/test_broker_permission_validation.py \
  tests/test_paystack_webhook.py tests/test_web_api_tokens.py \
  tests/test_telemetry.py tests/test_enterprise_features.py -q --tb=short

85 passed
```

The broader deterministic repository suite continues to be run by the parent
phase coordinator; inherited collection/environment failures remain tracked in
the prior pass reports.

## Safety invariants

- No raw API token, broker key/secret, webhook secret, or encryption key is
  persisted in the broker state payload or returned by an API response.
- Payment signatures authenticate origin, but do not by themselves enable
  entitlement writes; the explicit payments flag is required.
- API token identity is derived from the presented credential, never from a
  caller-supplied user id.
- Broker linking fails closed when `ENCRYPTION_KEY` is unavailable.
