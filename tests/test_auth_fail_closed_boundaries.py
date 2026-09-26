"""HTTP auth regressions with real local commit/rollback behavior.

SQLite supplies transaction durability here; PostgreSQL row-lock concurrency and
external Telegram/email integrations still require connected staging evidence.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Depends, FastAPI

from services.platform import identity
from services.security import encrypt_secret
from web import platform_api


class _Result:
    def __init__(self, cursor):
        self.rowcount = cursor.rowcount
        self.rows = []
        if cursor.description:
            names = [column[0] for column in cursor.description]
            for values in cursor.fetchall():
                row = dict(zip(names, values))
                for key, value in row.items():
                    if value and key.endswith("_at"):
                        row[key] = datetime.fromisoformat(value)
                    elif value and key in {"metadata", "scopes"}:
                        row[key] = json.loads(value)
                self.rows.append(row)
        self.as_mapping = False

    def mappings(self):
        self.as_mapping = True
        return self

    def first(self):
        if not self.rows:
            return None
        return self.rows[0] if self.as_mapping else tuple(self.rows[0].values())

    def scalar_one(self):
        return next(iter(self.rows[0].values()))


class _Database:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.create_function("NOW", 0, lambda: datetime.utcnow().isoformat(" "))
        self.connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))
        self.connection.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY,account_status TEXT,tier TEXT);
            INSERT INTO users VALUES(1,'active','professional');
            INSERT INTO users VALUES(2,'active','professional');
            CREATE TABLE user_sessions(
                session_id TEXT PRIMARY KEY,user_id INTEGER,refresh_token_hash TEXT,
                session_family_id TEXT,device_id TEXT,user_agent_hash TEXT,ip_hash TEXT,
                expires_at TEXT,revoked_at TEXT,rotated_to_session_id TEXT,
                revoke_reason TEXT,refresh_reuse_detected BOOLEAN,last_used_at TEXT);
            CREATE TABLE security_events(
                user_id INTEGER,event_type TEXT,severity TEXT,session_id TEXT,
                device_id TEXT,ip_hash TEXT,metadata TEXT);
            CREATE TABLE login_challenges(
                challenge_id TEXT,user_id INTEGER,purpose TEXT,token_hash TEXT,
                environment TEXT,metadata TEXT,expires_at TEXT,consumed_at TEXT,
                consumed_ip_hash TEXT,attempts INTEGER DEFAULT 0,max_attempts INTEGER DEFAULT 5);
            CREATE TABLE user_mfa_totp(
                user_id INTEGER PRIMARY KEY,encrypted_secret TEXT,enabled BOOLEAN,
                created_at TEXT,updated_at TEXT,verified_at TEXT,last_used_step INTEGER);
            CREATE TABLE account_recovery_codes(
                recovery_code_id TEXT,user_id INTEGER,code_hash TEXT,used_at TEXT);
            CREATE TABLE api_keys(
                key_id TEXT,user_id INTEGER,scopes TEXT,expires_at TEXT,key_prefix TEXT,
                secret_hash TEXT,active BOOLEAN,revoked_at TEXT,last_used_at TEXT);
        """)
        self.connection.commit()

    async def execute(self, statement, params=None):
        # Local dialect adaptation only. No external database/network is used.
        sql = str(statement).replace(" FOR UPDATE", "").replace("::text", "")
        sql = sql.replace(" AS JSONB)", " AS TEXT)")
        params = {
            key: value.isoformat(" ") if isinstance(value, datetime) else value
            for key, value in (params or {}).items()
        }
        return _Result(self.connection.execute(sql, params))

    async def commit(self):
        self.connection.commit()

    async def rollback(self):
        self.connection.rollback()

    @asynccontextmanager
    async def session(self, **kwargs):
        try:
            yield self
        finally:
            self.connection.rollback()

    def add_session(self, sid, *, uid=1, raw=None, family="family-1", revoked=False, successor=None):
        self.connection.execute(
            "INSERT INTO user_sessions(session_id,user_id,refresh_token_hash,session_family_id,"
            "expires_at,revoked_at,rotated_to_session_id) VALUES(?,?,?,?,?,?,?)",
            (sid, uid, identity._sha256(raw or sid), family,
             (datetime.utcnow() + timedelta(days=1)).isoformat(" "),
             datetime.utcnow().isoformat(" ") if revoked else None, successor),
        )
        self.connection.commit()

    def add_challenge(self, token, *, attempts=2):
        self.connection.execute(
            "INSERT INTO login_challenges(challenge_id,user_id,purpose,token_hash,metadata,"
            "expires_at,max_attempts) VALUES('challenge',1,'mfa_login',?,'{}',?,?)",
            (identity._sha256(token), (datetime.utcnow() + timedelta(minutes=5)).isoformat(" "), attempts),
        )
        self.connection.commit()

    def add_mfa(self, *, enabled=True):
        secret = "JBSWY3DPEHPK3PXP"
        self.connection.execute(
            "INSERT INTO user_mfa_totp(user_id,encrypted_secret,enabled,created_at) VALUES(1,?,?,NOW())",
            (encrypt_secret(secret), enabled),
        )
        self.connection.commit()
        return secret


@pytest.fixture
def auth_runtime(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("APP_AUTH_SECRET", "test-only-auth-secret-" * 3)
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = _Database()
    monkeypatch.setattr(platform_api, "get_session", db.session)
    monkeypatch.setattr(platform_api, "is_db_configured", lambda: True)

    async def snapshot(session, user_id):
        return (await session.execute("SELECT * FROM users WHERE id=:uid", {"uid": user_id})).mappings().first()

    monkeypatch.setattr(platform_api, "user_snapshot", snapshot)
    app = FastAPI()
    app.include_router(platform_api.router, prefix="/api/v1")

    @app.get("/api-key-probe")
    async def api_key_probe(user=Depends(platform_api.professional_api_user)):
        return {"user_id": user["id"]}

    yield db, app
    db.connection.close()


@asynccontextmanager
async def _client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        yield client


async def test_refresh_replay_commits_family_revocation_and_clears_cookies(auth_runtime):
    db, app = auth_runtime
    raw = "srr_" + "old-refresh" * 6
    db.add_session("old", raw=raw, revoked=True, successor="new")
    db.add_session("new")
    db.add_session("other", uid=2, family="family-2")
    async with _client(app) as client:
        response = await client.post("/api/v1/platform/auth/refresh", json={"refresh_token": raw})
        assert response.status_code == 401
        assert response.json()["detail"] == "refresh_token_revoked"
        assert len(response.headers.get_list("set-cookie")) == 4
        revoked = db.connection.execute(
            "SELECT revoked_at,revoke_reason,refresh_reuse_detected FROM user_sessions WHERE session_id='new'"
        ).fetchone()
        assert revoked[0] and revoked[1:] == ("refresh_reuse_detected", 1)
        token = identity.encode_access_token(1, session_id="new")
        denied = await client.get("/api/v1/platform/me", headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 401
    assert db.connection.execute("SELECT revoked_at FROM user_sessions WHERE session_id='other'").fetchone() == (None,)
    assert db.connection.execute("SELECT event_type FROM security_events").fetchone() == ("session.refresh_reuse_detected",)


async def test_valid_refresh_rotates_once_then_replay_invalidates_successor(auth_runtime):
    db, app = auth_runtime
    raw = "srr_" + "valid-refresh" * 6
    db.add_session("old", raw=raw)
    async with _client(app) as client:
        refreshed = await client.post(
            "/api/v1/platform/auth/refresh", json={"refresh_token": raw, "client_type": "mobile"},
        )
        assert refreshed.status_code == 200
        successor = refreshed.json()["session_id"]
        assert successor != "old"
        assert db.connection.execute("SELECT rotated_to_session_id FROM user_sessions WHERE session_id='old'").fetchone() == (successor,)
        replay = await client.post("/api/v1/platform/auth/refresh", json={"refresh_token": raw})
        assert replay.status_code == 401
    assert db.connection.execute("SELECT revoked_at FROM user_sessions WHERE session_id=?", (successor,)).fetchone()[0]


@pytest.mark.parametrize("status", ["suspended", "closed", "", None])
async def test_unknown_or_inactive_account_rejects_sessions_refresh_and_api_keys(auth_runtime, status):
    db, app = auth_runtime
    raw = "srr_" + "inactive-refresh" * 4
    db.add_session("session", raw=raw)
    api_key = "srk_prefix_" + "api-secret" * 4
    db.connection.execute("UPDATE users SET account_status=? WHERE id=1", (status,))
    db.connection.execute(
        "INSERT INTO api_keys(key_id,user_id,scopes,key_prefix,secret_hash,active) VALUES('key',1,'[]','srk_prefix',?,TRUE)",
        (hashlib.sha256(api_key.encode()).hexdigest(),),
    )
    db.connection.commit()
    token = identity.encode_access_token(1, session_id="session")
    async with _client(app) as client:
        session = await client.get("/api/v1/platform/me", headers={"Authorization": f"Bearer {token}"})
        api = await client.get("/api-key-probe", headers={"Authorization": f"Bearer {api_key}"})
        refresh = await client.post("/api/v1/platform/auth/refresh", json={"refresh_token": raw})
    assert (session.status_code, api.status_code, refresh.status_code) == (401, 401, 401)
    assert db.connection.execute("SELECT COUNT(*) FROM user_sessions").fetchone() == (1,)
    assert db.connection.execute("SELECT last_used_at FROM api_keys").fetchone() == (None,)
    with pytest.raises(identity.AuthenticationError, match="account_unavailable"):
        await identity.create_session_tokens(db, user_id=1)


async def test_session_id_cannot_be_borrowed_from_another_user(auth_runtime):
    db, app = auth_runtime
    db.add_session("user-two-session", uid=2)
    token = identity.encode_access_token(1, session_id="user-two-session")
    async with _client(app) as client:
        response = await client.get("/api/v1/platform/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.parametrize("path,payload", [
    ("login", {"email": "person@example.test", "password": "password"}),
    ("telegram/login", {"payload": {"id": "1"}}),
    ("telegram/mini-app", {"init_data": "test-first-factor"}),
    ("telegram/complete", {"token_or_code": "123456", "email": "person@example.test", "password": "LongPassword123"}),
    ("magic-link/complete", {"token": "src_" + "x" * 40}),
])
async def test_all_login_methods_require_enabled_mfa_before_creating_sessions(auth_runtime, monkeypatch, path, payload):
    db, app = auth_runtime
    db.add_mfa()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    for name in ("authenticate_email_password", "ensure_telegram_user", "complete_telegram_activation", "consume_magic_login"):
        monkeypatch.setattr(platform_api, name, AsyncMock(return_value=1))
    monkeypatch.setattr(platform_api, "validate_telegram_login_payload", lambda *args: {"id": "1"})
    monkeypatch.setattr(platform_api, "validate_telegram_mini_app_init_data", lambda *args: {"user": {"id": "1"}})
    async with _client(app) as client:
        response = await client.post(f"/api/v1/platform/auth/{path}", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["authenticated"] is False
    assert response.json()["mfa_required"] is True
    assert "set-cookie" not in response.headers
    assert db.connection.execute("SELECT COUNT(*) FROM user_sessions").fetchone() == (0,)
    assert db.connection.execute("SELECT purpose FROM login_challenges").fetchone() == ("mfa_login",)


async def test_failed_mfa_attempts_survive_rollback_and_exhaust_challenge(auth_runtime, monkeypatch):
    db, app = auth_runtime
    raw = "src_" + "challenge" * 5
    db.add_challenge(raw, attempts=2)
    verify = AsyncMock(side_effect=identity.AuthenticationError("invalid_mfa_code"))
    monkeypatch.setattr(identity, "verify_user_mfa", verify)
    async with _client(app) as client:
        for expected in ("invalid_mfa_code", "invalid_mfa_code", "challenge_attempt_limit"):
            response = await client.post("/api/v1/platform/auth/mfa/complete", json={"token": raw, "code": "000000"})
            assert response.status_code == 401
            assert response.json()["detail"] == expected
    assert verify.await_count == 2
    assert db.connection.execute("SELECT attempts,consumed_at FROM login_challenges").fetchone() == (2, None)
    assert db.connection.execute("SELECT COUNT(*) FROM user_sessions").fetchone() == (0,)


async def test_verified_mfa_issues_session_and_challenge_cannot_replay(auth_runtime):
    db, app = auth_runtime
    raw = "src_" + "challenge" * 5
    secret = db.add_mfa()
    db.add_challenge(raw)
    code, _ = identity._totp_code(secret)
    async with _client(app) as client:
        response = await client.post(
            "/api/v1/platform/auth/mfa/complete", json={"token": raw, "code": code, "client_type": "mobile"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["authenticated"] is True
        assert response.json()["access_token"]
        replay = await client.post("/api/v1/platform/auth/mfa/complete", json={"token": raw, "code": code})
    assert replay.status_code == 401
    assert replay.json()["detail"] == "challenge_already_used"
    assert db.connection.execute("SELECT COUNT(*) FROM user_sessions").fetchone() == (1,)


async def test_mfa_setup_cannot_replace_enabled_secret(auth_runtime):
    db, app = auth_runtime
    db.add_mfa()
    before = db.connection.execute("SELECT encrypted_secret,enabled FROM user_mfa_totp").fetchone()
    app.dependency_overrides[platform_api.current_user] = lambda: {"id": 1, "account_status": "active"}
    async with _client(app) as client:
        response = await client.post("/api/v1/platform/security/mfa/setup")
    assert response.status_code == 409
    assert response.json()["detail"] == "mfa_already_enabled"
    assert db.connection.execute("SELECT encrypted_secret,enabled FROM user_mfa_totp").fetchone() == before


@pytest.mark.parametrize("authorization", ["Bearer ", "Bearer unrelated", "Basic unrelated"])
async def test_authorization_header_cannot_bypass_cookie_csrf(authorization):
    from web.app import platform_csrf_middleware

    app = FastAPI()
    app.middleware("http")(platform_csrf_middleware)

    @app.post("/api/v1/platform/auth/refresh")
    async def mutation():
        return {"mutated": True}

    async with _client(app) as client:
        client.cookies.set("sr_refresh", "ambient-cookie")
        blocked = await client.post("/api/v1/platform/auth/refresh", headers={"Authorization": authorization})
        assert blocked.status_code == 403
        client.cookies.set("sr_csrf", "csrf-proof")
        allowed = await client.post("/api/v1/platform/auth/refresh", headers={"Authorization": authorization, "X-CSRF-Token": "csrf-proof"})
        assert allowed.status_code == 200
        client.cookies.clear()
        bearer_only = await client.post("/api/v1/platform/auth/refresh", headers={"Authorization": "Bearer token"})
        assert bearer_only.status_code == 200


async def test_malformed_authorization_never_falls_back_to_access_cookie(auth_runtime):
    db, app = auth_runtime
    db.add_session("session")
    async with _client(app) as client:
        client.cookies.set("sr_access", identity.encode_access_token(1, session_id="session"))
        response = await client.get("/api/v1/platform/me", headers={"Authorization": "Bearer "})
    assert response.status_code == 401
