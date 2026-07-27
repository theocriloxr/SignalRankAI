# Phase 4 Pass 3 — Delivery Idempotency and Active-Message Reliability

Date: 2026-07-18  
Branch: `fix-2`  
Implementation checkpoint audited: `6e8fb68`  
Status: complete for Pass 3; Pass 4 has not started

## Outcome

The Telegram signal-delivery boundary now uses a channel-scoped operation identity, a durable PostgreSQL reservation/outbox row, a Redis acknowledgement stash, monotonic proof transitions, atomic active-message persistence, and a reconciliation worker.

The acceptance criterion for this pass is met by focused failure-injection tests: a duplicate/retry cannot overwrite confirmed proof, a timeout after transmission becomes `AMBIGUOUS` and is not retried, and an accepted Telegram response survives an injected DB proof failure and is later reconciled without another send.

## Canonical contract

The operation key is:

```text
sha256(user_id | signal_id | channel_id | signal_version | delivery_kind)
```

The implementation hashes the UTF-8 string joined with literal `|` delimiters. The normalized operation payload and hash are stored in the existing `SignalDelivery.telegram_api_result` JSON proof envelope.

The canonical states are:

```text
RESERVED → VALIDATING → SENDING → SENT → PROOF_PENDING → CONFIRMED
```

Failure/recovery states are `BLOCKED`, `FAILED_PRE_SEND`, `AMBIGUOUS`, and `RECONCILED`.

`SENDING`, `SENT`, `PROOF_PENDING`, `CONFIRMED`, `AMBIGUOUS`, `RECONCILED`, and `BLOCKED` prohibit blind reservation retry. `FAILED_PRE_SEND` remains safely retryable. Confirmed or reconciled proof cannot be replaced by a later failure or a second Telegram acknowledgement.

## Implementation

### Durable reservation and proof CAS

- The existing `signal_deliveries` row is the durable delivery outbox for this compatibility pass.
- Reservations store the exact operation identity and idempotency key.
- Conflicting channel/version/kind keys fail closed instead of being collapsed into the existing row.
- Reservation, phase advancement, and proof persistence lock the delivery row with `SELECT ... FOR UPDATE`.
- `VALIDATING` must persist before final validation, and `SENDING` must persist before Telegram I/O. If either critical write fails, the signal is not sent.
- Telegram proof is required to contain both `chat_id` and `message_id` before `sent_ok=True` is allowed.

### Telegram ambiguity and fallback behavior

- A timeout after the Bot API request begins raises `TelegramDeliveryAmbiguous`.
- Timeout and network-ambiguous errors are never retried by the guarded send loop.
- Rich-message timeout ambiguity cannot fall through to a plain-message duplicate.
- Deterministic rich/keyboard failures retain the existing plain HTML fallback.
- Rich, plain fallback, fresh send, and message-edit success all produce the same receipt envelope.

### Receipt stash and reconciliation

- A confirmed Bot API response is written to Redis under a versioned, hash-scoped key before proof persistence.
- A Redis set tracks pending receipt keys for bounded reconciliation scans.
- Direct critical DB proof success removes the stashed receipt only after commit.
- If DB proof fails, the receipt remains pending and the existing durable `SENDING` row prevents another send.
- The app-owned reconciliation loop replays the stored acknowledgement as `RECONCILED`, then removes it from Redis.
- When Redis is unavailable, direct critical DB proof can still confirm the send. If Redis and DB both fail, the durable `SENDING` state deliberately favors duplicate prevention over automatic resend.

### Active-message reliability

- `ActiveSignalMessage` is no longer written in an independent post-send transaction.
- Delivery confirmation/reconciliation and the active-message insert/update now flush in the same DB transaction.
- Message edits stash proof before any follow-up notice and carry replacement metadata so reconciliation can deactivate the old pointer and establish the new one.
- VIP webhook fanout remains supported as best-effort background work, but it starts only after the Telegram receipt is recoverable.

### Compatibility and migration boundary

No migration was introduced in this pass. This preserves the ordered migration/schema-reconciliation work planned for later phases instead of skipping it.

The current database constraint, `uq_signal_delivery_user_signal`, is intentionally coarser than the new channel-scoped key. During this compatibility phase, an attempted second key for the same user/signal fails closed. A later planned schema pass can widen physical uniqueness after reconciliation and migration rehearsal; it must not weaken the Pass 3 operation contract.

## Files

- `delivery/service.py` — operation identity, canonical states, monotonic transition rules, timeout ambiguity classification.
- `delivery/receipts.py` — typed Telegram receipt and Redis pending-receipt store.
- `delivery/worker.py` — one-shot and recurring receipt reconciliation plus app lifecycle ownership.
- `db/pg_features.py` — durable reservation metadata, row locks, no-blind-retry gate, monotonic proof write, atomic active-message persistence.
- `signalrank_telegram/bot.py` — durable phase writes, no ambiguous retry/fallback, immediate receipt stash, proof acknowledgement, worker startup/shutdown.
- `engine/core.py`, `engine/signal_lock.py`, `engine/signal_lifecycle.py` — canonical-state compatibility in delivered-signal queries.
- `tests/test_phase4_pass3_delivery_reliability.py` — eight Pass 3 reliability and failure-injection tests.
- `tests/test_signal_delivery_ack.py` — receipt-aware acknowledgement contract.

## Verification

### Static verification

```powershell
python -m compileall -q delivery db/pg_features.py signalrank_telegram/bot.py engine/core.py engine/signal_lock.py engine/signal_lifecycle.py
git diff --check
```

Result: passed.

### Focused Pass 3 and adjacent delivery tests

```powershell
python -m pytest tests/test_phase4_pass3_delivery_reliability.py tests/test_signal_delivery_ack.py tests/test_delivery_limit_guard.py tests/test_delivery_outcome_news_hardening.py -q
```

Result: **23 passed**, 2 warnings, in 11.27 seconds.

The eight new Pass 3 tests cover:

1. Exact channel-scoped idempotency hash and key separation.
2. Monotonic transition and no-blind-retry policy.
3. Redis receipt stash/list/acknowledge round trip.
4. Telegram timeout ambiguity with exactly one send attempt.
5. Delivery-boundary timeout retaining durable `SENDING` semantics.
6. Late failure unable to overwrite confirmed DB proof.
7. Atomic confirmation and active-message pointer persistence.
8. Accepted Telegram send, injected DB proof failure, and successful receipt reconciliation.

### Broader delivery/lifecycle regression set

Result: **52 passed, 4 failed**, 4 warnings, in 29.18 seconds.

The four failures are inherited: one admin-pulse source assertion and three outcome-tracker tests whose session mocks reject the pre-existing `noncritical=` keyword. No Pass 3 test or changed delivery path failed.

### Canonical deterministic repository suite

```powershell
$testFiles = @(rg --files tests -g 'test_*.py' | Where-Object { $_ -notlike '*test_broker_permission_validation.py' } | Sort-Object)
python -m pytest @testFiles -q
```

Result: **455 passed, 31 failed, 2 errors**, 34 warnings, in 135.14 seconds.

Compared with the final Pass 2 checkpoint of 447 passed, 31 failed, and 2 errors, Pass 3 adds exactly **8 passing tests** while leaving inherited failure and error counts unchanged.

The 31 inherited failures remain in the previously recorded admin-pulse, web/Paystack/Flask-ASGI, Railway pool expectation, readiness/scheduler, outcome mock, signal-visibility, encoding, telemetry, and source-contract groups. The two inherited errors remain Windows ACL failures creating `tmp_path` beneath `C:\Users\sammm\AppData\Local\Temp\pytest-of-Theophilus`.

### Collection

```powershell
python -m pytest --collect-only -q
```

Result: **488 tests collected, 1 inherited collection error** in 17.84 seconds. The blocker remains `tests/test_broker_permission_validation.py`, which imports missing `verify_api_key` from `web.app`.

## Pass boundary

Pass 3 is complete. The outcome-tracker redesign, lifecycle transition CAS, batched quotes, and notification separation belong to Phase 4 Pass 4 and were not implemented here.
