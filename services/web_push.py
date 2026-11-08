"""Standard Web Push (RFC 8030 / 8291 aes128gcm / RFC 8292 VAPID) without a new dependency.

Owner request, 8 Nov 2026: notifications on desktops and phones where the web
app is installed. Browsers hand the site a subscription (endpoint + p256dh +
auth); the server encrypts each payload to that subscription and signs a VAPID
token. Only ``cryptography`` (already locked) and ``httpx`` are used.

The VAPID key pair is generated once and stored encrypted in ``runtime_state``
(``web_push:vapid:v1``), or taken from ``WEB_PUSH_VAPID_PRIVATE_KEY`` (PEM)
when set, so there is nothing for the owner to configure.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import time
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

VAPID_STATE_KEY = "web_push:vapid:v1"
RECORD_SIZE = 4096


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64u_decode(text: str) -> bytes:
    text = str(text or "").strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def public_bytes(key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey) -> bytes:
    pub = key.public_key() if isinstance(key, ec.EllipticCurvePrivateKey) else key
    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def encrypt_payload(payload: bytes, p256dh_b64: str, auth_b64: str, *,
                    sender: ec.EllipticCurvePrivateKey | None = None, salt: bytes | None = None) -> bytes:
    """aes128gcm body for one push message (RFC 8291 section 3.4, single record)."""
    receiver_pub_bytes = b64u_decode(p256dh_b64)
    auth_secret = b64u_decode(auth_b64)
    receiver_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), receiver_pub_bytes)
    sender = sender or ec.generate_private_key(ec.SECP256R1())
    sender_pub_bytes = public_bytes(sender)
    shared = sender.exchange(ec.ECDH(), receiver_pub)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + receiver_pub_bytes + sender_pub_bytes, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    if len(payload) > RECORD_SIZE - 17 - 86:
        raise ValueError("web_push_payload_too_large")
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!I", RECORD_SIZE) + bytes([len(sender_pub_bytes)]) + sender_pub_bytes
    return header + ciphertext


def vapid_authorization(endpoint: str, private_key: ec.EllipticCurvePrivateKey, subject: str,
                        *, now: float | None = None) -> str:
    parts = urlsplit(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int((now or time.time()) + 12 * 3600), "sub": subject}
    header = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}".encode()
    r, s = decode_dss_signature(private_key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    token = f"{header}.{body}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={token}, k={b64u(public_bytes(private_key))}"


# ---------------------------------------------------------------------------
# key management
# ---------------------------------------------------------------------------

_cached_key: ec.EllipticCurvePrivateKey | None = None


def _key_from_pem(pem: str) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("vapid_key_not_ec")
    return key


async def vapid_private_key(session) -> ec.EllipticCurvePrivateKey:
    """The server's VAPID key: env, else stored (encrypted) in runtime_state, else generated once."""
    global _cached_key
    if _cached_key is not None:
        return _cached_key
    pem = os.getenv("WEB_PUSH_VAPID_PRIVATE_KEY") or ""
    if pem.strip():
        _cached_key = _key_from_pem(pem)
        return _cached_key
    from sqlalchemy import text

    from services.security import decrypt_secret, encrypt_secret

    stored = (await session.execute(text("SELECT value FROM runtime_state WHERE key=:k"),
                                    {"k": VAPID_STATE_KEY})).scalar_one_or_none()
    if isinstance(stored, str):
        stored = json.loads(stored)
    if isinstance(stored, dict) and stored.get("encrypted_pem"):
        decrypted = decrypt_secret(str(stored["encrypted_pem"]))
        if decrypted:
            _cached_key = _key_from_pem(decrypted)
            return _cached_key
    key = ec.generate_private_key(ec.SECP256R1())
    pem_text = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption()).decode()
    encrypted = encrypt_secret(pem_text)
    if not encrypted:
        raise RuntimeError("web_push_requires_encryption_key")
    await session.execute(
        text("INSERT INTO runtime_state(key, value, expires_at, updated_at) VALUES (:k, CAST(:v AS JSONB), NULL, NOW()) "
             "ON CONFLICT (key) DO NOTHING"),
        {"k": VAPID_STATE_KEY, "v": json.dumps({"encrypted_pem": encrypted, "public_key": b64u(public_bytes(key))})},
    )
    await session.commit()
    # Another process may have won the insert: read back the stored key.
    _cached_key = None
    stored = (await session.execute(text("SELECT value FROM runtime_state WHERE key=:k"),
                                    {"k": VAPID_STATE_KEY})).scalar_one()
    stored = json.loads(stored) if isinstance(stored, str) else stored
    _cached_key = _key_from_pem(decrypt_secret(str(stored["encrypted_pem"])) or pem_text)
    return _cached_key


async def vapid_public_key(session) -> str:
    return b64u(public_bytes(await vapid_private_key(session)))


def vapid_subject() -> str:
    return os.getenv("WEB_PUSH_VAPID_SUBJECT") or "mailto:support@criloxsolutions.com"


async def send_web_push(subscription: dict[str, Any], message: dict[str, Any], private_key,
                        *, client=None) -> tuple[bool, str]:
    """Send one message. Returns (ok, reason); reason 'gone' means the subscription should be deactivated."""
    import httpx

    endpoint = str(subscription.get("endpoint") or "")
    keys = subscription.get("keys") or {}
    if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        return False, "invalid_subscription"
    body = encrypt_payload(json.dumps(message, separators=(",", ":")).encode(), keys["p256dh"], keys["auth"])
    headers = {"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": "3600",
               "Urgency": "high", "Authorization": vapid_authorization(endpoint, private_key, vapid_subject())}
    owns = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        response = await client.post(endpoint, content=body, headers=headers)
    finally:
        if owns:
            await client.aclose()
    if response.status_code in (404, 410):
        return False, "gone"
    return (200 <= response.status_code < 300), f"http_{response.status_code}"
