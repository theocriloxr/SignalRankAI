from hashlib import sha256
from io import BytesIO

import pytest

from scripts import install_opengrep as installer


def test_install_verifies_download_before_exposing_executable(monkeypatch, tmp_path):
    payload = b"fixture-binary-bytes"
    monkeypatch.setattr(installer, "asset", lambda: ("fixture-asset", sha256(payload).hexdigest()))
    urls = []
    def download(url, timeout):
        urls.append((url, timeout))
        return BytesIO(payload)
    monkeypatch.setattr(installer, "urlopen", download)
    binary = installer.install(tmp_path)
    assert binary.read_bytes() == payload
    assert urls == [(f"https://github.com/opengrep/opengrep/releases/download/v{installer.VERSION}/fixture-asset", 120)]
    assert installer.install(tmp_path) == binary
    assert len(urls) == 1


def test_bad_download_never_becomes_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(installer, "asset", lambda: ("fixture", "0" * 64))
    monkeypatch.setattr(installer, "urlopen", lambda *a, **k: BytesIO(b"wrong bytes"))
    with pytest.raises(RuntimeError, match="checksum"):
        installer.install(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_existing_tampered_binary_is_rejected(monkeypatch, tmp_path):
    payload = b"original"
    monkeypatch.setattr(installer, "asset", lambda: ("fixture", sha256(payload).hexdigest()))
    monkeypatch.setattr(installer, "urlopen", lambda *a, **k: BytesIO(payload))
    binary = installer.install(tmp_path)
    binary.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="checksum"):
        installer.install(tmp_path)


def test_unknown_platform_does_not_download_unverified_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.platform, "system", lambda: "Unknown")
    with pytest.raises(RuntimeError, match="No approved"):
        installer.install(tmp_path)
