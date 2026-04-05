from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.settings import Settings

ENV_EXAMPLE = REPO_ROOT / ".env.example"
OUT_DOC = REPO_ROOT / "docs" / "ENV_VARS.md"


def _read_env_example_vars() -> set[str]:
    if not ENV_EXAMPLE.exists():
        return set()
    names: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name = line.split("=", 1)[0].strip()
        if name:
            names.add(name)
    return names


def _settings_fields() -> list[tuple[str, str, str]]:
    fields = getattr(Settings, "model_fields", None) or getattr(Settings, "__fields__", {})
    out: list[tuple[str, str, str]] = []
    for name in sorted(fields.keys()):
        f = fields[name]
        annotation = getattr(f, "annotation", None) or getattr(f, "type_", None)
        annotation_name = getattr(annotation, "__name__", None) or str(annotation)
        default = getattr(f, "default", None)
        default_str = "" if default is None else str(default)
        out.append((name, annotation_name, default_str))
    return out


def _scan_usage(var_name: str) -> str:
    pat = re.compile(rf"\b{re.escape(var_name)}\b")
    hits: list[str] = []
    for p in REPO_ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "venv", "__pycache__"} for part in p.parts):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if pat.search(txt):
            rel = p.relative_to(REPO_ROOT).as_posix()
            hits.append(rel)
        if len(hits) >= 3:
            break
    return ", ".join(hits) if hits else "-"


def generate() -> tuple[str, list[str]]:
    env_vars = _read_env_example_vars()
    rows = _settings_fields()
    missing_from_example = [name for name, _, _ in rows if name not in env_vars]

    lines = [
        "# Environment Variables Index",
        "",
        "> Auto-generated from `core/settings.py` by `scripts/gen_env_index.py`.",
        "",
        "| Variable | Type | Default | Example present in `.env.example` | Used in files (sample) |",
        "|---|---|---|---|---|",
    ]
    for name, typ, default in rows:
        in_example = "yes" if name in env_vars else "no"
        usage = _scan_usage(name)
        lines.append(f"| `{name}` | `{typ}` | `{default}` | {in_example} | {usage} |")
    lines.append("")
    if missing_from_example:
        lines.append("## Missing in `.env.example`")
        lines.append("")
        for name in missing_from_example:
            lines.append(f"- `{name}`")
        lines.append("")
    return "\n".join(lines), missing_from_example


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate/check env var index.")
    parser.add_argument("--check", action="store_true", help="Fail if settings vars are missing in .env.example.")
    args = parser.parse_args()

    doc, missing = generate()
    OUT_DOC.write_text(doc, encoding="utf-8")
    if args.check and missing:
        print("Missing from .env.example:", ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
