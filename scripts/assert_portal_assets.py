"""Validate that the public portal and its offline shell use one cache generation."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("styles.css", "app.js", "icon.svg", "logo.svg")


def validate_shell_assets(root: Path = ROOT, *, minimum_version: int = 38) -> int:
    portal = root / "web/platform_app"
    worker = (portal / "service-worker.js").read_text(encoding="utf-8")
    html = (portal / "index.html").read_text(encoding="utf-8")
    match = re.search(r"const CACHE=['\"]signalrank-shell-v(\d+)['\"]", worker)
    if not match or int(match.group(1)) < minimum_version:
        raise ValueError("portal_cache_generation_missing_or_obsolete")
    version = int(match.group(1))
    for asset in ASSETS:
        if not (portal / asset).is_file():
            raise ValueError(f"portal_asset_missing:{asset}")
        references = re.findall(r"/app-assets/" + re.escape(asset) + r"\?v=(\d+)", html)
        if not references or any(int(value) != version for value in references):
            raise ValueError(f"portal_html_cache_generation_mismatch:{asset}")
        if f"/app-assets/{asset}?v={version}" not in worker:
            raise ValueError(f"portal_worker_cache_generation_mismatch:{asset}")
    return version


if __name__ == "__main__":
    print(f"PORTAL_ASSETS_PASS cache_version={validate_shell_assets(minimum_version=39)}")
