"""Sign-in and sign-up work with a leftover session cookie (8 Nov 2026).

Owner report: new users could not join from the site, plus other sign-in
issues. The CSRF middleware's docstring exempted public login/registration but
the code did not, so a visitor holding an old sr_access/sr_refresh cookie
without a matching sr_csrf got "CSRF validation failed". The exemption now
exists and requires a same-site Origin/Referer, so a foreign page still
cannot sign a visitor in.
"""
from pathlib import Path

from fastapi.testclient import TestClient

from web.app import _PUBLIC_AUTH_PATHS, app

ROOT = Path(__file__).resolve().parents[1]
HOST = "https://signalrank.criloxsolutions.com"
LOGIN = "/api/v1/platform/auth/login"
BODY = {"email": "nobody@example.com", "password": "Wrong-password-1", "client_type": "web"}


def _client() -> TestClient:
    client = TestClient(app, base_url=HOST, raise_server_exceptions=False)
    client.cookies.set("sr_refresh", "stale-refresh-token")
    return client


def test_same_site_sign_in_with_a_stale_cookie_is_not_refused_by_csrf():
    response = _client().post(LOGIN, json=BODY, headers={"origin": HOST})
    assert response.status_code != 403 or "CSRF" not in response.text


def test_foreign_origin_sign_in_with_a_cookie_still_needs_csrf():
    response = _client().post(LOGIN, json=BODY, headers={"origin": "https://evil.example"})
    assert response.status_code == 403 and "CSRF" in response.text


def test_cookie_mutations_outside_the_auth_entry_points_still_need_csrf():
    assert "/api/v1/platform/auth/logout" not in _PUBLIC_AUTH_PATHS
    response = _client().post("/api/v1/platform/auth/logout", headers={"origin": HOST})
    assert response.status_code == 403


def test_sign_up_links_and_form_tell_the_real_rules():
    page = (ROOT / "frontend" / "src" / "app" / "page.tsx").read_text(encoding="utf-8")
    nav = (ROOT / "frontend" / "src" / "components" / "PublicNav.tsx").read_text(encoding="utf-8")
    entry = (ROOT / "frontend" / "src" / "components" / "AccountEntry.tsx").read_text(encoding="utf-8")
    field = (ROOT / "frontend" / "src" / "components" / "ui" / "PasswordField.tsx").read_text(encoding="utf-8")
    assert 'href="/login?mode=register"' in page and 'href="/login?mode=register"' in nav
    assert '["register", "signup", "create"].includes(requested)' in entry
    assert "email_already_registered" in entry and "authErrorMessage(response.response.status, response.error)" in entry
    assert 'aria-label={visible ? "Hide password" : "Show password"}' in field
    assert "Three of: lowercase, uppercase, number, symbol" in field
