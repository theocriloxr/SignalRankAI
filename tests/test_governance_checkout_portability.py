"""Governance hashes must survive Git's text checkout conversion."""
from scripts.build_v7_governance import _source_bytes, _sha256


def test_esmodule_inventory_survives_lf_crlf_checkout(tmp_path):
    source = tmp_path / "verification.mjs"
    source.write_bytes(b"import assert from 'node:assert';\nassert.ok(true);\n")
    canonical = _sha256(source)
    source.write_bytes(b"import assert from 'node:assert';\r\nassert.ok(true);\r\n")
    assert _sha256(source) == canonical
    source.write_bytes(b"import assert from 'node:assert';\nassert.ok(false);\n")
    assert _sha256(source) != canonical


def test_commonjs_checkout_is_normalized(tmp_path):
    source = tmp_path / "verification.cjs"
    source.write_bytes(b"module.exports = 1;\r\n")
    assert _source_bytes(source) == b"module.exports = 1;\n"


def test_binary_inventory_preserves_all_bytes(tmp_path):
    source = tmp_path / "logo.png"
    payload = b"\x89PNG\r\n\x1a\n\xff\xfe"
    source.write_bytes(payload)
    assert _source_bytes(source) == payload


def test_dependency_lock_inventory_survives_windows_to_linux_checkout(tmp_path, monkeypatch):
    from scripts import build_v7_governance as governance
    source = tmp_path / "requirements-market-data-sdk.lock"
    monkeypatch.setattr(governance, "ROOT", tmp_path)
    monkeypatch.setattr(governance, "OUT", tmp_path / "requirements")
    monkeypatch.setattr(governance, "PROMPT_PATH", tmp_path / "docs/specs/master.md")
    monkeypatch.setattr(governance.subprocess, "check_output", lambda *a, **kw: b"requirements-market-data-sdk.lock\0")
    original = b"httpx==0.28.1 \\\n    --hash=sha256:abc\n"
    source.write_bytes(original)
    linux = governance.build_legacy_disposition()["files"][0]
    source.write_bytes(original.replace(b"\n", b"\r\n"))
    windows = governance.build_legacy_disposition()["files"][0]
    assert windows == linux
    assert windows["line_count"] == 2
    source.write_bytes(original.replace(b"0.28.1", b"0.28.2"))
    assert governance.build_legacy_disposition()["files"][0]["sha256"] != linux["sha256"]
