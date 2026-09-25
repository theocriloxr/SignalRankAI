from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_web_signup_migration_is_single_head() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "db" / "migrations"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["0040_cross_channel_paper_receipt"]
    migration = _source("db/migrations/versions/0039_web_signup_acquisition.py")
    assert 'down_revision = "0038_account_security_product"' in migration
    assert "CREATE TABLE IF NOT EXISTS user_acquisition" in migration
    paper_receipts = _source("db/migrations/versions/0040_cross_channel_paper_receipts.py")
    assert 'down_revision = "0039_web_signup_acquisition"' in paper_receipts
    assert "ALTER COLUMN delivery_id DROP NOT NULL" in paper_receipts


def test_direct_signup_accepts_acquisition_and_referral_context() -> None:
    api = _source("web/platform_api.py")
    for marker in (
        "referral_code:",
        "signup_source:",
        "landing_path:",
        "http_referrer:",
        "utm_source:",
        "utm_medium:",
        "utm_campaign:",
        "process_referral_signup_for_user",
        "INSERT INTO user_acquisition",
    ):
        assert marker in api


def test_frontend_preserves_referral_and_utm_context() -> None:
    js = _source("web/platform_app/app.js")
    assert "function signupContext()" in js
    assert "qs.get('ref')" in js
    assert "qs.get('utm_source')" in js
    assert "document.referrer" in js


def test_custom_domain_is_canonical_production_origin() -> None:
    advisory = _source("SignalRankAI_v1.3.3_Railway_Production_Advisory.env.example")
    canary = _source("SignalRankAI_v1.3.3_Railway_Live_Owner_Canary.env.example")
    for profile in (advisory, canary):
        assert "APP_BASE_URL=https://signalrank.criloxsolutions.com" in profile
        assert "APP_ALLOWED_ORIGINS=https://signalrank.criloxsolutions.com" in profile
        assert "APP_COOKIE_SECURE=1" in profile
        assert "EXPECTED_ALEMBIC_HEAD=0040_cross_channel_paper_receipt" in profile


def test_email_links_prefer_configured_app_base_url_over_railway_domain() -> None:
    api = _source("web/platform_api.py")
    fn = api[api.index("def _app_base_url"):api.index("def _cookie_secure")]
    assert fn.index('os.getenv("APP_BASE_URL")') < fn.index('os.getenv("RAILWAY_PUBLIC_DOMAIN")')


def test_browser_root_opens_platform_app() -> None:
    app = _source("web/app.py")
    assert '"text/html" in accept' in app
    assert 'RedirectResponse(url="/app", status_code=307)' in app


def test_web_referrals_do_not_require_telegram_identity() -> None:
    source = _source("db/pg_features.py")
    fn = source[source.index("async def process_referral_signup_for_user"):source.index("async def process_referral_start")]
    assert "referred_user_id" in fn
    assert "user_id=int(referrer.id)" in fn
    assert "telegram_user_id=(" in fn
