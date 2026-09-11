from services.performance_ledger import _unresolved_dead_letter_count


def test_dead_letter_count_excludes_resolved_audit_records() -> None:
    records = [
        {"internal_user_id": 1},
        {"internal_user_id": 2, "resolved_at": "2026-09-02T10:00:00"},
        {"internal_user_id": 3, "resolved_at": ""},
    ]

    assert _unresolved_dead_letter_count(records) == 2
