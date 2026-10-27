#!/usr/bin/env python3
"""Generate release documentation from provenance artifacts."""

import json
import argparse
from pathlib import Path


def generate_docs(provenance_path: Path, output_path: Path):
    if not provenance_path.exists():
        print(f"Provenance file not found at {provenance_path}")
        return

    data = json.loads(provenance_path.read_text(encoding="utf-8"))

    release = data.get("release", {})
    inputs = data.get("inputs", {})
    artifacts = data.get("artifacts", {})

    doc = []
    doc.append(f"# SignalRankAI Release Notes: {release.get('semver', 'Unknown')}")
    doc.append(f"**Build Time**: {release.get('build_time', 'Unknown')}")
    doc.append(f"**Commit**: {release.get('git_commit', 'Unknown')} (Branch: {release.get('git_branch', 'Unknown')})")
    doc.append(f"**Schema Head (Alembic)**: {release.get('alembic_head', 'Unknown')}")
    doc.append("")
    doc.append("## Provenance Artifacts")
    doc.append("| Artifact | Format | SHA256 |")
    doc.append("|---|---|---|")
    for name, info in artifacts.items():
        doc.append(f"| {name} | {info.get('format', 'Unknown')} | `{info.get('sha256', 'Unknown')}` |")
    doc.append("")
    doc.append("## Verified Inputs")
    for name, info in inputs.items():
        doc.append(f"- **{name}**: `{info.get('sha256', 'Unknown')}`")

    output_path.write_text("\n".join(doc), encoding="utf-8")
    print(f"Release documentation generated at {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provenance", default="/tmp/signalrank-build-provenance/release-provenance.json")
    parser.add_argument("--output", default="RELEASE_NOTES.md")
    args = parser.parse_args()

    generate_docs(Path(args.provenance), Path(args.output))
