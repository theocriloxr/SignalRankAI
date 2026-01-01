"""DEPRECATED: SQLite subscription storage removed.

SignalRankAI is Postgres-only. Subscription state is persisted via Postgres
tables (see `db/models.py`, `db/repository.py`, and the Paystack webhook in
`web/app.py`).

This module is kept only as a compatibility stub so any accidental imports fail
loudly.
"""

from __future__ import annotations


raise RuntimeError(
    "payments.subscriptions (SQLite) has been removed. Use Postgres-backed subscription persistence."
)
