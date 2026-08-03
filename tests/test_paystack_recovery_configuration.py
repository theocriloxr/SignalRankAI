from __future__ import annotations

import pytest

from payments.paystack_events import paystack_recovery_configuration


@pytest.mark.parametrize(
    ("secret", "public", "expected_reason"),
    [
        ("", "", "paystack_secret_missing"),
        ("sk_test_secret", "", "configured"),
        ("sk_test_secret", "pk_live_public", "configured"),
        ("sk_live_secret", "pk_test_public", "configured"),
    ],
)
def test_recovery_requires_only_the_secret_for_replay(
    monkeypatch,
    secret: str,
    public: str,
    expected_reason: str,
) -> None:
    monkeypatch.setenv("PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", secret)
    monkeypatch.setenv("PAYSTACK_PUBLIC_KEY", public)

    if expected_reason == "configured":
        assert paystack_recovery_configuration() == (True, expected_reason)
    else:
        assert paystack_recovery_configuration() == (False, expected_reason)


@pytest.mark.parametrize(
    ("secret", "public"),
    [
        ("sk_test_secret", "pk_test_public"),
        ("sk_live_secret", "pk_live_public"),
    ],
)
def test_recovery_accepts_matching_key_modes(monkeypatch, secret: str, public: str) -> None:
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", secret)
    monkeypatch.setenv("PAYSTACK_PUBLIC_KEY", public)

    assert paystack_recovery_configuration() == (True, "configured")


def test_recovery_allows_secret_only_configuration(monkeypatch) -> None:
    monkeypatch.setenv("PAYMENTS_ENABLED", "1")
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_live_secret")
    monkeypatch.delenv("PAYSTACK_PUBLIC_KEY", raising=False)

    assert paystack_recovery_configuration() == (True, "configured")


def test_recovery_stays_off_when_payments_are_disabled(monkeypatch) -> None:
    monkeypatch.setenv("PAYMENTS_ENABLED", "0")
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_live_secret")
    monkeypatch.setenv("PAYSTACK_PUBLIC_KEY", "pk_live_public")

    assert paystack_recovery_configuration() == (False, "payments_disabled")
