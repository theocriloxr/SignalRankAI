from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_legal_pages_and_routes_exist() -> None:
    app = source("web/app.py")
    for route, filename in (
        ("/privacy", "privacy.html"),
        ("/terms", "terms.html"),
        ("/cookies", "cookies.html"),
        ("/billing-policy", "billing-policy.html"),
        ("/risk-disclosure", "risk-disclosure.html"),
        ("/accessibility", "accessibility.html"),
    ):
        assert f'@app.get("{route}"' in app
        assert filename in app
        assert (ROOT / "web" / "platform_app" / filename).exists()


def test_signup_and_telegram_activation_require_platform_privacy_acknowledgement() -> None:
    api = source("web/platform_api.py")
    html = source("web/platform_app/index.html")
    mobile = source("mobile/App.tsx")
    assert 'CURRENT_PLATFORM_TERMS_VERSION = "2026-10-03"' in api
    assert "platform_terms_accepted: bool = False" in api
    assert "privacy_acknowledged: bool = False" in api
    assert api.count("age_eligibility_confirmed: bool = False") >= 2
    assert "marketing_consent: bool = False" in api
    assert api.count("payload.platform_terms_accepted is not True") >= 2
    assert api.count("payload.privacy_acknowledged is not True") >= 2
    assert api.count("payload.age_eligibility_confirmed is not True") >= 2
    assert html.count('name="platform_terms_accepted"') >= 2
    assert html.count('name="privacy_acknowledged"') >= 2
    assert html.count('name="age_eligibility_confirmed"') >= 2
    assert html.count('name="marketing_consent"') >= 2
    assert "mode==='register'||mode==='activate'" in mobile
    assert "ageEligibilityConfirmed" in mobile
    assert "at least 18" in mobile


def test_platform_terms_do_not_silently_enable_execution_terms() -> None:
    api = source("web/platform_api.py")
    register = api[api.index('@router.post("/auth/register"'):api.index('@router.post("/auth/login")')]
    activate = api[api.index('@router.post("/auth/telegram/complete"'):api.index('@router.post("/auth/telegram/login")')]
    assert "terms_version" in register and "terms_accepted_at" in register
    assert "accepted_terms" not in register
    assert "terms_version" in activate and "terms_accepted_at" in activate
    assert "accepted_terms" not in activate


def test_recurring_billing_requires_explicit_acknowledgement() -> None:
    api = source("web/platform_api.py")
    checkout = source("payments/checkout.py")
    web = source("web/platform_app/app.js")
    mobile_api = source("mobile/src/api.ts")
    mobile_app = source("mobile/App.tsx")
    assert "recurring_acknowledged: bool = False" in api
    assert "recurring_billing_acknowledgement_required" in checkout
    assert 'metadata["billing_terms_version"] = "2026-10-03"' in checkout
    assert "Renews automatically until cancelled" in web
    assert "recurring_acknowledged:recurring" in web
    assert "recurring_acknowledged: recurringAcknowledged" in mobile_api
    assert "Recurring subscription" in mobile_app


def test_auto_renew_is_opt_in_for_new_accounts_and_verified_recurring_payments() -> None:
    models = source("db/models.py")
    identity = source("services/platform/identity.py")
    paystack = source("payments/paystack.py")
    cancellation = source("services/subscription_cancellation.py")
    assert "auto_renew: Mapped[bool] = mapped_column(Boolean, default=False" in models
    assert "auto_renew,created_at" in identity
    assert "payment_user.auto_renew = True" in paystack
    assert "if provider_plan_code:" in paystack
    assert "was_auto_renew = bool(user.auto_renew)" in cancellation
    assert "(was_auto_renew or sub_code) and not gateway_cancelled" in cancellation


def test_compliance_ui_rotates_pwa_cache() -> None:
    worker = source("web/platform_app/service-worker.js")
    html = source("web/platform_app/index.html")
    assert "signalrank-shell-v39" in worker
    assert "styles.css?v=39" in worker
    assert "app.js?v=39" in worker
    assert "styles.css?v=39" in html
    assert "app.js?v=39" in html


def test_authenticated_privacy_rights_requests_are_available_cross_channel() -> None:
    html = source("web/platform_app/index.html")
    web = source("web/platform_app/app.js")
    mobile = source("mobile/App.tsx")
    assert 'requestDataExportButton' in html
    assert 'requestAccountDeletionButton' in html
    assert "category:'privacy'" in web
    assert "Personal data access / export request" in web
    assert "Account deletion review" in web
    assert "do not abandon any active broker position" in web.lower()
    assert "Request my data export" in mobile
    assert "Request account deletion review" in mobile
    assert "category:'privacy'" in mobile
