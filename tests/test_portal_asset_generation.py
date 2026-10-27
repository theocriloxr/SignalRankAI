from pathlib import Path
import pytest

from scripts.assert_portal_assets import ASSETS, ROOT, validate_shell_assets


def test_current_portal_assets_share_the_service_worker_generation():
    assert validate_shell_assets(ROOT, minimum_version=39) >= 39


@pytest.mark.parametrize("mismatch", ["html", "worker", "obsolete", "missing"])
def test_mixed_or_incomplete_offline_releases_are_rejected(tmp_path: Path, mismatch: str):
    portal = tmp_path / "web/platform_app"
    portal.mkdir(parents=True)
    for asset in ASSETS:
        (portal / asset).write_text("public fixture", encoding="utf-8")
    html = " ".join(f"/app-assets/{asset}?v=40" for asset in ASSETS)
    worker = "const CACHE='signalrank-shell-v40';\n" + html
    if mismatch == "html": html = html.replace("styles.css?v=40", "styles.css?v=39")
    if mismatch == "worker": worker = worker.replace("app.js?v=40", "app.js?v=39")
    if mismatch == "obsolete": worker = worker.replace("shell-v40", "shell-v1")
    if mismatch == "missing": (portal / "icon.svg").unlink()
    (portal / "index.html").write_text(html, encoding="utf-8")
    (portal / "service-worker.js").write_text(worker, encoding="utf-8")
    with pytest.raises(ValueError): validate_shell_assets(tmp_path)
