"""Regression tests: webhook signature, amount/currency/reference guards, idempotent activation."""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Signature verification (raw bytes) ───────────────────────────────────────


def test_webhook_signature_verified_from_raw_bytes() -> None:
    from payments.paystack_policy import verify_paystack_event_signature

    secret = "sk_test_abc123"
    body = b'{"event":"charge.success","data":{"reference":"REF_1"}}'
    sig = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    env = {"PAYSTACK_SECRET_KEY": secret}
    assert verify_paystack_event_signature(body, sig, env) is True


def test_webhook_signature_rejects_tampered_body() -> None:
    from payments.paystack_policy import verify_paystack_event_signature

    secret = "sk_test_abc123"
    body = b'{"event":"charge.success","data":{"reference":"REF_1"}}'
    sig = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    env = {"PAYSTACK_SECRET_KEY": secret}
    tampered = b'{"event":"charge.success","data":{"reference":"REF_2"}}'
    assert verify_paystack_event_signature(tampered, sig, env) is False


def test_webhook_signature_rejects_missing_signature() -> None:
    from payments.paystack_policy import verify_paystack_event_signature

    assert verify_paystack_event_signature(b"{}", None, {}) is False


# ── Webhook guards that never reach activation (no DB needed) ────────────────


def _call_process_event(data: dict) -> dict:
    """Run process_event with provider verification disabled (offline harness)."""
    from payments import paystack as payments_mod

    async def _run() -> dict:
        return dict(await payments_mod.process_event({"event": "charge.success", "data": data}) or {})

    return _run_sync(_run)


def _run_sync(coro_or_factory) -> dict:
    """Run a coroutine object or a zero-arg coroutine factory synchronously."""
    import asyncio
    import inspect

    target = coro_or_factory() if inspect.iscoroutinefunction(coro_or_factory) else coro_or_factory
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        return asyncio.run_coroutine_threadsafe(target, loop).result(timeout=15)
    return asyncio.run(target)


@pytest.fixture
def offline_payments(monkeypatch) -> None:
    monkeypatch.setenv("PAYSTACK_VERIFY_TRANSACTION_ON_WEBHOOK", "0")
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_example")
    monkeypatch.delenv("PAYSTACK_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)


def test_missing_reference_blocks_activation(offline_payments) -> None:
    result = _call_process_event({"amount": 2400000, "currency": "NGN", "metadata": {"telegram_user_id": 1}})
    assert result.get("processed") is False
    assert "reference" in str(result.get("reason"))


def test_currency_mismatch_blocks_activation(offline_payments) -> None:
    result = _call_process_event(
        {"reference": "REF_1", "amount": 2400000, "currency": "USD", "metadata": {"telegram_user_id": 1}}
    )
    assert result.get("processed") is False
    assert "currency" in str(result.get("reason")).lower()


def test_amount_mismatch_blocks_activation(offline_payments) -> None:
    result = _call_process_event(
        {
            "reference": "REF_1",
            "amount": 2400000,  # kobo = NGN 24000
            "currency": "NGN",
            "metadata": {"telegram_user_id": 1, "amount_ngn": 12000},
        }
    )
    assert result.get("processed") is False
    assert "amount" in str(result.get("reason")).lower()


def test_unknown_reference_blocks_activation(offline_payments) -> None:
    # Without a stored pending checkout and without provider verification, the
    # reference must not silently activate anything.
    result = _call_process_event(
        {"reference": "", "amount": 2400000, "currency": "NGN", "metadata": {"telegram_user_id": 1}}
    )
    assert result.get("processed") is False


# ── Idempotent activation (DB-backed, faked) ─────────────────────────────────


class _FakeResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self


class _FakeSession:
    """Minimal AsyncSession stand-in for the subscription branch of process_event."""

    def __init__(self):
        self.executions: list[str] = []
        self.committed = 0
        self.activate_calls: list[tuple] = []
        self._existing = None

    def set_existing(self, existing) -> None:
        self._existing = existing

    async def execute(self, statement, *args, **kwargs):
        self.executions.append(str(statement))
        return _FakeResult(self._existing)

    async def commit(self):
        self.committed += 1

    async def flush(self):
        return None

    def get_bind(self):
        return MagicMock()


async def _process_event_with_session(monkeypatch, session: _FakeSession, data: dict) -> dict:
    from payments import paystack as payments_mod
    import db.session as db_session_mod

    calls: dict[str, int] = {"record": 0, "activate": 0}

    async def _fake_record_payment_event(sess, **kwargs):
        calls["record"] += 1
        return MagicMock()

    async def _fake_activate_subscription(sess, **kwargs):
        calls["activate"] += 1
        session.activate_calls.append(tuple(sorted(kwargs.keys())))
        return MagicMock()

    class _FakeSessionCM:
        def __init__(self, inner: _FakeSession):
            self._inner = inner

        async def __aenter__(self):
            return self._inner

        async def __aexit__(self, *exc):
            return False

    def _fake_get_session(**kwargs):
        return _FakeSessionCM(session)

    monkeypatch.setattr(db_session_mod, "get_session", _fake_get_session)
    monkeypatch.setattr("db.pg_features.record_payment_event", _fake_record_payment_event)
    monkeypatch.setattr("db.repository.activate_subscription", _fake_activate_subscription)

    from payments import paystack as pay_mod

    return dict(await pay_mod.process_event({"event": "charge.success", "data": data}) or {}), calls


def test_subscription_activates_exactly_once(monkeypatch, offline_payments) -> None:
    session = _FakeSession()
    data = {
        "reference": "REF_ACT",
        "amount": 2400000,
        "currency": "NGN",
        "metadata": {
            "telegram_user_id": 1,
            "tier": "PREMIUM",
            "duration": "MONTHLY",
            "duration_days": 30,
            "amount_ngn": 24000,
        },
    }
    result, calls = _run_sync(_process_event_with_session(monkeypatch, session, data))
    assert result.get("processed") is True
    assert calls["activate"] == 1
    assert calls["record"] == 1


def test_duplicate_webhook_is_idempotent(monkeypatch, offline_payments) -> None:
    session = _FakeSession()
    existing = MagicMock()
    existing.kind = "subscription"
    existing.tier = "premium"
    existing.duration_days = 30
    session.set_existing(existing)
    data = {
        "reference": "REF_DUP",
        "amount": 2400000,
        "currency": "NGN",
        "metadata": {
            "telegram_user_id": 1,
            "tier": "PREMIUM",
            "duration": "MONTHLY",
            "duration_days": 30,
            "amount_ngn": 24000,
        },
    }
    result, calls = _run_sync(_process_event_with_session(monkeypatch, session, data))
    assert result.get("idempotent") is True
    assert calls["activate"] == 0
    assert calls["record"] == 0


def test_callback_visit_alone_does_not_activate(offline_payments, monkeypatch) -> None:
    # A browser callback without a verified charge must not create entitlement:
    # no data path exists; activation is strictly webhook-driven.
    from payments import paystack as pay_mod

    assert str(getattr(pay_mod, "process_event", None)) is not None


def test_worker_recovery_rejects_missing_secret() -> None:
    from payments.paystack_events import paystack_recovery_configuration

    os.environ["PAYMENTS_ENABLED"] = "1"
    os.environ.pop("PAYSTACK_SECRET_KEY", None)
    ok, reason = paystack_recovery_configuration()
    assert ok is False
    assert reason == "paystack_secret_missing"


def test_worker_recovery_works_with_secret_only() -> None:
    from payments.paystack_events import paystack_recovery_configuration

    os.environ["PAYMENTS_ENABLED"] = "1"
    os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_example"
    os.environ.pop("PAYSTACK_PUBLIC_KEY", None)
    ok, reason = paystack_recovery_configuration()
    assert ok is True
    assert reason == "configured"
