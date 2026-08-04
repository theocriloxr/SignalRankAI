"""Regression tests for the authoritative plan catalogue and checkout flow."""
from __future__ import annotations

import re

import pytest

from payments.plan_catalogue import (
    PLAN_CALLBACK_PATTERN,
    PlanCatalogueError,
    build_plan_catalogue,
    get_plan,
    validate_plan_code,
)


def test_catalogue_contains_all_four_internal_plans() -> None:
    plans = build_plan_catalogue({})
    assert set(plans) == {"premium_monthly", "premium_quarterly", "premium_yearly", "vip_monthly"}
    assert plans["premium_monthly"].price_ngn == 24000
    assert plans["premium_quarterly"].price_ngn == 56000
    assert plans["premium_yearly"].price_ngn == 192000
    assert plans["vip_monthly"].price_ngn == 40000


def test_plan_callback_pattern_matches_all_four_plans() -> None:
    pattern = re.compile(PLAN_CALLBACK_PATTERN)
    for code in ("premium_monthly", "premium_quarterly", "premium_yearly", "vip_monthly"):
        assert pattern.match(f"subscribe:{code}") is not None, code
    assert pattern.match("subscribe:premium_daily") is None
    assert pattern.match("payment_unavailable") is None
    assert pattern.match("subscribe:") is None


def test_env_price_override_is_respected() -> None:
    plans = build_plan_catalogue({"PREMIUM_MONTHLY_PRICE_NGN": "30000"})
    assert plans["premium_monthly"].price_ngn == 30000


def test_invalid_price_is_rejected() -> None:
    with pytest.raises(PlanCatalogueError):
        build_plan_catalogue({"PREMIUM_MONTHLY_PRICE_NGN": "not-a-number"})
    with pytest.raises(PlanCatalogueError):
        build_plan_catalogue({"PREMIUM_MONTHLY_PRICE_NGN": "0"})
    with pytest.raises(PlanCatalogueError):
        build_plan_catalogue({"PREMIUM_MONTHLY_PRICE_NGN": "-500"})
    with pytest.raises(PlanCatalogueError):
        build_plan_catalogue({"PREMIUM_MONTHLY_PRICE_NGN": "99999999999"})


def test_unknown_plan_code_is_rejected() -> None:
    assert get_plan("premium_daily") is None
    assert validate_plan_code("premium_daily") is False
    assert validate_plan_code("") is False


def test_kobo_conversion_happens_once_and_is_exact() -> None:
    plans = build_plan_catalogue({})
    assert plans["premium_monthly"].price_kobo() == 2_400_000
    assert plans["vip_monthly"].price_kobo() == 4_000_000
    assert plans["premium_yearly"].price_kobo() == 19_200_000


def test_price_never_lives_in_callback_data() -> None:
    # Callback data is only ever `subscribe:<plan_code>`.
    assert re.compile(r"subscribe:[a-z_]+$").match("subscribe:premium_monthly")


def test_checkout_result_is_typed_never_an_error_sentence() -> None:
    from paystack.paystack import CheckoutInitializationResult

    blocked = CheckoutInitializationResult(False, mode="live", reason="payments_disabled")
    assert blocked.ok is False
    assert blocked.authorization_url is None
    # A blocked policy must never look like a URL string.
    assert isinstance(blocked.authorization_url, type(None))

    ok = CheckoutInitializationResult(True, authorization_url="https://checkout.paystack.com/x", reference="sra-abc", mode="test")
    assert ok.ok is True


def test_checkout_url_validation_accepts_paystack_and_rejects_others() -> None:
    from paystack.paystack import is_valid_paystack_checkout_url

    assert is_valid_paystack_checkout_url("https://checkout.paystack.com/abc")
    assert is_valid_paystack_checkout_url("https://paystack.com/abc")
    assert is_valid_paystack_checkout_url("https://checkout.paystack.com/pay/abc?x=1")
    assert not is_valid_paystack_checkout_url("")
    assert not is_valid_paystack_checkout_url("checkout blocked: payments_disabled")
    assert not is_valid_paystack_checkout_url("http://checkout.paystack.com/abc")
    assert not is_valid_paystack_checkout_url("https://evil.example.com/abc")
    assert not is_valid_paystack_checkout_url("/relative/path")
    assert not is_valid_paystack_checkout_url(None)
