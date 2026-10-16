from scripts.build_master_requirement_registry import SOURCE, inventory


def test_master_inventory_covers_all_incidents_release_gates_routes_and_checkboxes():
    text = SOURCE.read_text("utf-8")
    entries = inventory(text)
    ids = [entry["requirement_id"] for entry in entries]
    assert len(ids) == len(set(ids))
    assert {f"G{index:02d}" for index in range(1, 33)}.issubset(ids)
    assert {f"P0-SIG-{index:03d}" for index in range(1, 11)}.issubset(ids)
    assert sum(line.strip().startswith("\u2610") for line in text.splitlines()) <= len(entries)
    assert sum(entry["section"] == "16" for entry in entries) == 27
    assert sum(entry["section"] == "appendix-C" for entry in entries) == 25
    assert all(entry["status"] != "IMPLEMENTED_VERIFIED" for entry in entries)
