import smtplib
import pytest

from scripts import smtp_preflight


def settings(**overrides):
    return {"SMTP_HOST": "smtp.example.test", "SMTP_USERNAME": "operator", "SMTP_PASSWORD": "fixture-password",
            "SMTP_PORT": "587", "SMTP_USE_STARTTLS": "1", **overrides}


@pytest.mark.parametrize("missing", ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"])
def test_missing_credentials_fail_before_network(monkeypatch, missing):
    monkeypatch.setattr(smtp_preflight.smtplib, "SMTP", lambda *a, **kw: pytest.fail("network accessed"))
    with pytest.raises(ValueError, match="required"):
        smtp_preflight.authenticate(settings(**{missing: ""}))


def test_plaintext_authentication_is_rejected(monkeypatch):
    monkeypatch.setattr(smtp_preflight.smtplib, "SMTP", lambda *a, **kw: pytest.fail("network accessed"))
    with pytest.raises(ValueError, match="verified_tls_required"):
        smtp_preflight.authenticate(settings(SMTP_USE_SSL="0", SMTP_USE_STARTTLS="0"))


def test_authentication_uses_verified_tls_and_never_sends(monkeypatch):
    events = []
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ehlo(self): events.append("ehlo")
        def starttls(self, *, context):
            assert context.check_hostname
            events.append("tls")
        def login(self, username, password):
            assert (username, password) == ("operator", "fixture-password")
            events.append("login")
        def send_message(self, *args): pytest.fail("email sent")
    monkeypatch.setattr(smtp_preflight.smtplib, "SMTP", lambda *a, **kw: Client())
    result = smtp_preflight.authenticate(settings())
    assert events == ["ehlo", "tls", "ehlo", "login"]
    assert result["authenticated"] and not result["email_sent"]


def test_provider_authentication_error_does_not_leak_response_or_credentials(monkeypatch, capsys):
    def rejected():
        raise smtplib.SMTPAuthenticationError(535, b"sensitive provider response fixture-password")
    monkeypatch.setattr(smtp_preflight, "authenticate", rejected)
    assert smtp_preflight.main() == 1
    output = capsys.readouterr().out
    assert '"smtp_code": 535' in output
    assert "sensitive provider response" not in output and "fixture-password" not in output
