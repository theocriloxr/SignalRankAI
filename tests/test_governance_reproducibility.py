import hashlib
import sys

from scripts import build_v7_governance as governance


def test_text_fingerprints_match_across_git_checkout_line_endings(tmp_path):
    source = tmp_path / "module.py"
    source.write_bytes(b"value = 1\nprint(value)\n")
    fingerprint = governance._sha256(source)
    source.write_bytes(b"value = 1\r\nprint(value)\r\n")
    assert governance._sha256(source) == fingerprint
    source.write_bytes(b"value = 2\r\nprint(value)\r\n")
    assert governance._sha256(source) != fingerprint


def test_binary_fingerprints_preserve_all_bytes(tmp_path):
    source = tmp_path / "image.png"
    raw = b"\x00\r\n\xff"
    source.write_bytes(raw)
    assert governance._sha256(source) == hashlib.sha256(raw).hexdigest()


def test_failed_check_preserves_stored_artifact(tmp_path, monkeypatch):
    output = tmp_path / "requirements"
    output.mkdir()
    artifact = output / "test.yaml"
    original = b'{"status":"old"}\n'
    artifact.write_bytes(original)
    monkeypatch.setattr(governance, "ROOT", tmp_path)
    monkeypatch.setattr(governance, "OUT", output)
    monkeypatch.setattr(governance, "generate", lambda: governance._write("test.yaml", {"status": "new"}))
    monkeypatch.setattr(sys, "argv", ["governance", "--check"])
    assert governance.main() == 1
    assert artifact.read_bytes() == original
    assert governance._CHECK_OUTPUT is None


def test_generated_artifact_always_uses_lf(tmp_path, monkeypatch):
    monkeypatch.setattr(governance, "OUT", tmp_path)
    governance._write("test.yaml", {"status": "new"})
    assert b"\r" not in (tmp_path / "test.yaml").read_bytes()
