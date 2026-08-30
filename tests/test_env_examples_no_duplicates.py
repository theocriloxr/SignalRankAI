from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _duplicate_keys(path: Path) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if not key or not key.replace("_", "").isalnum() or not key.upper() == key:
            continue
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return duplicates


def test_all_shipped_env_profiles_have_unique_keys() -> None:
    paths = [ROOT / ".env.example", ROOT / "RAILWAY_ENV_UPDATED.env.example"]
    paths.extend(sorted((ROOT / "configs" / "env").glob("*.env.example")))
    paths.extend(sorted((ROOT / "deploy" / "railway_roles").glob("*.env")))

    failures = {
        str(path.relative_to(ROOT)): sorted(_duplicate_keys(path))
        for path in paths
        if path.is_file() and _duplicate_keys(path)
    }
    assert failures == {}, f"duplicate environment keys: {failures}"
