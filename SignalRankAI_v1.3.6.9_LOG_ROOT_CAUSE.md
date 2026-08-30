# v1.3.6.8 Runtime Log Root Cause

## Primary failure

`db.pg_features.list_delivery_recipients_for_signal()` used `_env_bool()` but that module did not define or import the helper. The tracker called recipient outbox creation after writing the Outcome row but before committing. The resulting NameError aborted the transaction, so the terminal outcome and notification outbox were both absent.

This explains the observed combination:

1. price tracker repeatedly detected TP events;
2. `persist_outcome` failed 137 times;
3. the front-door outcome scheduler still reported successful job execution;
4. users received entry/risk/retrace messages but no durable final outcome messages;
5. reconciliation examined no missing projections because the older query could not repair existing stale pending rows or lifecycle disagreements.

## v1.3.6.9 failure boundary

The new order is:

```text
lifecycle transition
→ Outcome upsert
→ signal/archive update
→ COMMIT canonical trading truth
→ notification outbox transaction
→ front-door claim/send/receipt
→ worker reconciliation repairs missing outbox rows
```

Outcome truth is now durable even when notification fan-out fails.
