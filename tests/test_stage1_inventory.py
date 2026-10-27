import json
import gzip
import hashlib
from pathlib import Path

from scripts import build_release_inventory as inventory


ROOT = Path(__file__).resolve().parents[1]


def test_inventory_preserves_all_original_sections_and_interface_kinds():
    result = inventory.build()
    originals = json.loads((ROOT / "certification/completion_matrix.json").read_text("utf-8"))["entries"]
    recovered = {row["historical_id"]: row for row in result["requirements"] if row["kind"] == "PRESERVED"}
    assert set(recovered) == {row["id"] for row in originals}
    for original in originals:
        assert recovered[original["id"]]["text"] == original["text"]
        assert recovered[original["id"]]["subrequirements"] == original["subrequirements"]
    assert {r["kind"] for r in result["interfaces"]} >= {
        "ENDPOINT", "API", "WEB", "MOBILE", "COMMAND", "CALLBACK", "BROKER", "PROVIDER", "STRATEGY", "TIMEFRAME"}
    for row in result["requirements"] + result["interfaces"]:
        assert row["status"] in inventory.STATUSES - {"VERIFIED"}
        for field in ("id", "source", "current_implementation", "responsible_component", "verification_method", "associated_commit"):
            assert row[field]
        assert isinstance(row["test_evidence"], list)


def test_root_page_and_every_openapi_operation_have_trace_rows():
    routes = inventory.client_interfaces(inventory.tracked())
    assert any(r["source"] == "frontend/src/app/page.tsx" and r["route"] == "/" for r in routes)
    operations = inventory.effective_endpoints()
    actual = {(r["method"].lower(), r["endpoint"]) for r in operations}
    schema = json.loads((ROOT / "openapi.json").read_text("utf-8"))
    expected = {(method, path) for path, methods in schema["paths"].items() for method in methods if method in inventory.HTTP_METHODS}
    assert actual == expected


def test_every_snapshot_ref_has_an_explicit_non_destructive_disposition():
    audit = json.loads((ROOT / "docs/release/evidence/branch-audit.json").read_text("utf-8"))
    reviewed = json.loads((ROOT / "docs/release/branch_dispositions.json").read_text("utf-8"))
    assert {(r["ref"], r["sha"]) for r in audit["refs"]} == {(r["ref"], r["sha"]) for r in reviewed["refs"]}
    assert all(r["reason"] and r["evidence"] and r["action"] != "DIVERGENT_REVIEW_REQUIRED" for r in reviewed["refs"])


def test_catch_all_files_expand_to_concrete_product_routes():
    rows = inventory.client_interfaces(inventory.tracked())
    routes = {r["route"] for r in rows if r["kind"] == "WEB"}
    assert routes >= {"/pricing", "/product", "/privacy", "/strategies", "/status",
                      "/app/watchlists", "/app/settings", "/app/operations",
                      "/app/signals/{signal_id}"}
    assert len([r for r in rows if r.get("route_kind") == "EXPANDED_ALLOWLIST"]) == 31
    assert {r["requirement"] for r in rows if r["kind"] == "MOBILE"} >= {"overview", "research", "account"}


def test_all_historical_documentation_versions_are_retrievable_and_hash_bound():
    index = json.loads((ROOT / "docs/release/evidence/historical-documentation-index.json").read_text("utf-8"))
    archive = ROOT / index["archive"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == index["archive_sha256"]
    with gzip.open(archive, "rt", encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream]
    actual = {(r["path"],r["git_blob"]):r for r in records}
    assert set(actual) == {(r["path"],r["git_blob"]) for r in index["versions"]}
    for r in index["versions"]:
        assert hashlib.sha256(actual[(r["path"],r["git_blob"])]["text"].encode()).hexdigest() == r["archived_text_sha256"]
