from __future__ import annotations

from pathlib import Path


def test_broker_credential_inventory_is_counts_only() -> None:
    source = Path("scripts/broker_credential_inventory.py").read_text(encoding="utf-8")

    assert "COUNT(*)" in source
    assert "GROUP BY 1" in source
    assert "ready_for_live_money_credentials" in source
    assert "canonical_legacy_fernet_rows" in source
    assert "rows_with_password_ciphertext" in source
    assert "rows_without_canonical_envelope" in source

    # The inventory may use these columns only inside predicates/counts. It must
    # never select or emit their values.
    forbidden_selects = (
        "SELECT secret_encrypted",
        "SELECT password_encrypted",
        "SELECT credential_key_id",
        "SELECT mt5_login",
        "SELECT server",
        "SELECT external_account_id",
        "SELECT account_ref",
    )
    for marker in forbidden_selects:
        assert marker not in source

    for output_key in (
        '"secret_encrypted"',
        '"password_encrypted"',
        '"credential_key_id"',
        '"mt5_login"',
        '"server"',
        '"external_account_id"',
        '"account_ref"',
    ):
        assert output_key not in source


def test_inventory_never_imports_credential_decryption() -> None:
    source = Path("scripts/broker_credential_inventory.py").read_text(encoding="utf-8")
    assert "decrypt_" not in source
    assert "Fernet" not in source
    assert "broker_credentials" not in source
