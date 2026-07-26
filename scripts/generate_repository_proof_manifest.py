#!/usr/bin/env python3
"""Generate a deterministic, secret-safe repository proof manifest."""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache", "artifacts", ".pytest-tmp"}
SKIP_FILES = {
    "docs/REPOSITORY_PROOF_MANIFEST.json",
    "docs/REPOSITORY_PROOF_MANIFEST.md",
}
ENV_RE = re.compile(r"(?:os\.getenv|os\.environ\.get)\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]")


@dataclass(slots=True)
class FileProof:
    path: str
    category: str
    size_bytes: int
    sha256: str
    line_count: int | None
    public_symbols: list[str]
    env_variables: list[str]
    test_references: list[str]
    parse_status: str


def _category(path: Path) -> str:
    first = path.parts[0] if path.parts else ""
    if first == "tests":
        return "test"
    if first in {"docs"}:
        return "documentation"
    if first in {"migrations", "alembic", "alembic_migrations"}:
        return "migration"
    if first in {"scripts"}:
        return "script"
    if first in {"configs", "deploy"} or path.name in {"Dockerfile", "Dockerfile.prod", "Procfile", "railway.json", "nixpacks.toml", "start.sh"}:
        return "deployment_configuration"
    if path.suffix == ".py":
        return "production_runtime"
    return "project_asset"


def _python_metadata(text: str) -> tuple[list[str], list[str], str]:
    envs = sorted(set(ENV_RE.findall(text)))
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], envs, f"syntax_error:{exc.lineno}"
    public = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            public.append(node.name)
    return sorted(public), envs, "ok"


def generate(root: Path = ROOT) -> dict[str, Any]:
    tests: dict[str, str] = {}
    for test_path in sorted((root / "tests").glob("test_*.py")):
        tests[str(test_path.relative_to(root))] = test_path.read_text(encoding="utf-8-sig", errors="replace")

    records: list[FileProof] = []
    for path in sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and str(p.relative_to(root)).replace("\\", "/") not in SKIP_FILES
        and not any(part in SKIP_PARTS for part in p.relative_to(root).parts)
    ):
        rel = path.relative_to(root)
        raw = path.read_bytes()
        text: str | None = None
        line_count: int | None = None
        public: list[str] = []
        envs: list[str] = []
        parse_status = "not_applicable"
        if path.suffix in {".py", ".md", ".txt", ".toml", ".json", ".yml", ".yaml", ".sh", ".env", ".example"} or path.name in {"Dockerfile", "Procfile"}:
            text = raw.decode("utf-8-sig", errors="replace")
            line_count = len(text.splitlines())
        if path.suffix == ".py" and text is not None:
            public, envs, parse_status = _python_metadata(text)

        module_tokens = {path.stem, str(rel.with_suffix("")).replace("/", ".")}
        references = [
            test_name
            for test_name, test_text in tests.items()
            if any(token and token in test_text for token in module_tokens)
        ]
        records.append(
            FileProof(
                path=str(rel),
                category=_category(rel),
                size_bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                line_count=line_count,
                public_symbols=public,
                env_variables=envs,
                test_references=references[:100],
                parse_status=parse_status,
            )
        )

    categories: dict[str, int] = {}
    for record in records:
        categories[record.category] = categories.get(record.category, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "file_count": len(records),
        "categories": dict(sorted(categories.items())),
        "files": [asdict(record) for record in records],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="docs/REPOSITORY_PROOF_MANIFEST.json")
    parser.add_argument("--summary", default="docs/REPOSITORY_PROOF_MANIFEST.md")
    args = parser.parse_args()

    report = generate()
    json_path = ROOT / args.json
    md_path = ROOT / args.summary
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    untested_runtime = [
        item for item in report["files"]
        if item["category"] == "production_runtime" and not item["test_references"]
    ]
    syntax_errors = [item for item in report["files"] if str(item["parse_status"]).startswith("syntax_error")]
    lines = [
        "# Repository Proof Manifest",
        "",
        f"Generated: {report['generated_at']}",
        f"Files inventoried: **{report['file_count']}**",
        "",
        "## Categories",
        "",
    ]
    for category, count in report["categories"].items():
        lines.append(f"- `{category}`: {count}")
    lines.extend(
        [
            "",
            "## Static traceability observations",
            "",
            f"- Python syntax errors detected: **{len(syntax_errors)}**",
            f"- Production-runtime files with no direct lexical test reference: **{len(untested_runtime)}**",
            "- Absence of a lexical reference does not necessarily mean absence of transitive coverage; it marks files for manual/coverage review.",
            "- The JSON manifest contains SHA-256, public symbols, environment reads and test references for every file.",
            "",
        ]
    )
    if syntax_errors:
        lines.append("## Syntax errors")
        lines.extend(f"- `{item['path']}`: {item['parse_status']}" for item in syntax_errors)
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"manifest={json_path} summary={md_path} files={report['file_count']}")
    return 1 if syntax_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
