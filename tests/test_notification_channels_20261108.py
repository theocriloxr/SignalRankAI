"""Email and app (push) notifications per tier (owner request, 8 Nov 2026)."""
from __future__ import annotations

import asyncio
import json
import os
import struct
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services import notification_channels as nc
from services.web_push import _hkdf, b64u, b64u_decode, encrypt_payload, public_bytes, vapid_authorization

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


def _decrypt(body: bytes, receiver, auth: bytes) -> bytes:
    """Browser-side RFC 8291 decryption, to prove the sender's encryption."""
    salt, idlen = body[:16], body[20]
    sender_pub, ct = body[21:21 + idlen], body[21 + idlen:]
    assert struct.unpack("!I", body[16:20])[0] == 4096
    shared = receiver.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sender_pub))
    ikm = _hkdf(auth, shared, b"WebPush: info\x00" + public_bytes(receiver) + sender_pub, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, ct, None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


def test_web_push_encryption_round_trips():
    receiver = ec.generate_private_key(ec.SECP256R1())
    auth = os.urandom(16)
    body = encrypt_payload(b'{"title":"BTCUSDT LONG"}', b64u(public_bytes(receiver)), b64u(auth))
    assert _decrypt(body, receiver, auth) == b'{"title":"BTCUSDT LONG"}'


def test_vapid_token_verifies():
    key = ec.generate_private_key(ec.SECP256R1())
    header = vapid_authorization("https://fcm.googleapis.com/fcm/send/abc", key, "mailto:ops@example.com")
    token = header.split("t=")[1].split(",")[0]
    head, claims, sig = token.split(".")
    raw = b64u_decode(sig)
    key.public_key().verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                            f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    assert json.loads(b64u_decode(claims))["aud"] == "https://fcm.googleapis.com"
    assert header.endswith("k=" + b64u(public_bytes(key)))


def test_quiet_hours():
    at = datetime(2026, 11, 8, 23, 30, tzinfo=timezone.utc)
    assert nc.in_quiet_hours("22:00", "07:00", "UTC", now=at)
    assert not nc.in_quiet_hours("08:00", "20:00", "UTC", now=at)
    assert not nc.in_quiet_hours(None, None, "UTC", now=at)


def test_free_email_never_carries_exact_levels():
    signal = {"signal_id": "s-1", "asset": "BTCUSDT", "direction": "long", "timeframe": "1h", "entry": 76543.21,
              "stop_loss": 75000.5, "take_profit": [80000.75], "score": 90, "strategy_name": "ADX Trend"}
    free = nc.render_signal_email(signal, "free")
    vip = nc.render_signal_email(signal, "vip")
    assert vip is not None and "Entry: 76,543.21" in vip[1] and "Stop Loss: 75,000.50" in vip[1]
    assert free is not None and "75,000.50" not in free[1] and "76,543.21" not in free[1]
    assert "🔒" in free[1]  # the same locked teaser Free users get on Telegram


class _FakeHttp:
    def __init__(self):
        self.posts = []

    async def post(self, url, content=None, json=None, headers=None):
        self.posts.append({"url": url, "content": content, "json": json, "headers": headers})

        class R:
            status_code = 201 if content is not None else 200

            @staticmethod
            def json():
                return {"data": [{"status": "ok"} for _ in (json or [])]}
        return R()

    async def aclose(self):
        pass


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_dispatch_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url
    from services import security, web_push

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("WEB_PUSH_VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(web_push, "_cached_key", None)
    for name in ("_fernet", "_FERNET", "_cached_fernet"):
        if hasattr(security, name):
            monkeypatch.setattr(security, name, None)
    receiver = ec.generate_private_key(ec.SECP256R1())
    auth = os.urandom(16)
    subscription = {"endpoint": "https://push.example.test/sub/1",
                    "keys": {"p256dh": b64u(public_bytes(receiver)), "auth": b64u(auth)}}

    async def scenario():
        from db.session import dispose_engine_for_event_loop

        engine = create_async_engine(url)
        uid = None
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM runtime_state WHERE key='web_push:vapid:v1'"))
                uid = (await conn.execute(text(
                    "INSERT INTO users (created_at, tier, primary_email, email_verified_at) "
                    "VALUES (NOW(), 'vip', 'notify.test@example.com', NOW()) RETURNING id"))).scalar_one()
                await conn.execute(text(
                    "INSERT INTO notification_preferences(user_id, email_enabled, push_enabled) VALUES (:u, TRUE, TRUE)"),
                    {"u": uid})
                await conn.execute(text(
                    "INSERT INTO signals (signal_id, asset, timeframe, direction, entry, stop_loss, take_profit, score, "
                    "strategy_name, strategy_group, strength, created_at, display_id) VALUES ('nc-1','BTCUSDT','1h','long',"
                    "76543.21,75000.5,'[80000.75]',90,'ADX Trend','trend',1,NOW() AT TIME ZONE 'utc','nc1')"))
                await conn.execute(text(
                    "INSERT INTO notification_events(notification_id,user_id,event_type,title,body,severity,channel_data,"
                    "created_at) VALUES ('nc-evt-1',:u,'signal','BTCUSDT LONG signal','1h · score 90.0','info',"
                    "CAST('{\"signal_id\":\"nc-1\"}' AS JSONB), NOW() AT TIME ZONE 'utc')"), {"u": uid})
                await conn.execute(text(
                    "INSERT INTO push_devices(push_device_id,user_id,provider,push_token_hash,encrypted_push_token,platform)"
                    " VALUES ('nc-dev-web',:u,'webpush','h1',:t,'web'), ('nc-dev-expo',:u,'expo','h2',:e,'android')"),
                    {"u": uid, "t": security.encrypt_secret(json.dumps(subscription)),
                     "e": security.encrypt_secret("ExponentPushToken[abc]")})
            http = _FakeHttp()
            first = await nc.dispatch_once(client=http)
            assert first["email_queued"] == 1 and first["push_sent"] == 1
            again = await nc.dispatch_once(client=http)
            assert again["events"] == 0  # each (notification, channel) at most once
            web = next(p for p in http.posts if p["url"] == subscription["endpoint"])
            message = json.loads(_decrypt(web["content"], receiver, auth))
            assert message["title"] == "BTCUSDT LONG signal" and message["url"] == "/app/signals/nc-1"
            assert web["headers"]["Authorization"].startswith("vapid t=")
            expo = next(p for p in http.posts if p["url"] == nc.EXPO_URL)
            assert expo["json"][0]["to"] == "ExponentPushToken[abc]"
            async with engine.connect() as conn:
                mail = (await conn.execute(text(
                    "SELECT subject, plain_body, recipient FROM email_outbox WHERE idempotency_key='notify:nc-evt-1:email'"
                ))).first()
            assert mail is not None and mail[2] == "notify.test@example.com" and "BTCUSDT" in mail[0]
            assert "76" in mail[1]  # VIP sees exact levels
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM email_outbox WHERE idempotency_key='notify:nc-evt-1:email'"))
                await conn.execute(text("DELETE FROM notification_channel_deliveries WHERE notification_id='nc-evt-1'"))
                await conn.execute(text("DELETE FROM notification_events WHERE notification_id='nc-evt-1'"))
                await conn.execute(text("DELETE FROM push_devices WHERE push_device_id IN ('nc-dev-web','nc-dev-expo')"))
                await conn.execute(text("DELETE FROM signals WHERE signal_id='nc-1'"))
                await conn.execute(text("DELETE FROM runtime_state WHERE key='web_push:vapid:v1'"))
                if uid is not None:
                    await conn.execute(text("DELETE FROM notification_preferences WHERE user_id=:u"), {"u": uid})
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    asyncio.run(scenario())


def test_installable_app_and_device_notifications_are_wired():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    manifest = (root / "frontend" / "src" / "app" / "manifest.ts").read_text("utf-8")
    sw = (root / "frontend" / "public" / "sw.js").read_text("utf-8")
    device = (root / "frontend" / "src" / "components" / "DeviceNotifications.tsx").read_text("utf-8")
    assert 'display: "standalone"' in manifest and "/brand/icon-512.png" in manifest
    assert 'addEventListener("push"' in sw and 'addEventListener("notificationclick"' in sw
    assert 'addEventListener("fetch"' not in sw  # never intercepts pages or API calls
    assert 'provider: "webpush"' in device and "/api/v1/platform/push/vapid-public-key" in device
    eas = (root / "mobile" / "eas.json").read_text("utf-8")
    assert '"buildType": "apk"' in eas
    worker = (root / "worker" / "worker.py").read_text("utf-8")
    assert '"notification_channels"' in worker
