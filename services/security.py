"""
services/security.py - Fernet symmetric encryption for sensitive credentials.

Usage:
    from services.security import encrypt_secret, decrypt_secret

    ciphertext = encrypt_secret("my_mt5_password")
    plain = decrypt_secret(ciphertext)  # -> "my_mt5_password"

Environment:
    ENCRYPTION_KEY  - 32-byte URL-safe base64 key generated with:
                      `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
"""
from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore


def _get_fernet() -> Optional["Fernet"]:
    """Build Fernet instance from ENCRYPTION_KEY env var."""
    if not _CRYPTO_AVAILABLE:
        logger.warning("[security] cryptography package not installed; encryption disabled")
        return None
    key = (os.getenv("ENCRYPTION_KEY") or "").strip()
    if not key:
        logger.warning("[security] ENCRYPTION_KEY not set; encryption disabled")
        return None
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        logger.error("[security] Invalid ENCRYPTION_KEY: %s", exc)
        return None


def encrypt_secret(plaintext: str) -> Optional[str]:
    """Encrypt a plaintext secret string.

    Returns a URL-safe base64 ciphertext string, or None if encryption
    is unavailable (missing key or library).
    """
    fernet = _get_fernet()
    if fernet is None:
        return None
    try:
        token = fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")
    except Exception as exc:
        logger.error("[security] encrypt_secret failed: %s", exc)
        return None


def decrypt_secret(ciphertext: str) -> Optional[str]:
    """Decrypt a ciphertext string back to plaintext.

    Returns plaintext, or None on failure (bad key / tampered token).
    """
    fernet = _get_fernet()
    if fernet is None:
        return None
    try:
        plain = fernet.decrypt(ciphertext.encode("utf-8"))
        return plain.decode("utf-8")
    except InvalidToken:
        logger.warning("[security] decrypt_secret: invalid or tampered token")
        return None
    except Exception as exc:
        logger.error("[security] decrypt_secret failed: %s", exc)
        return None


def is_encryption_available() -> bool:
    """Return True if encryption is properly configured."""
    return _get_fernet() is not None
