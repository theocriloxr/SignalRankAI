"""Read-only, complete-ref reconciliation snapshot. Never merges or deploys."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def collect(baseline: str) -> dict:
    baseline = git("rev-parse", baseline)
    refs = git("for-each-ref", "--format=%(refname:short)|%(objectname)",
               "refs/heads", "refs/remotes/origin", "refs/tags").splitlines()
    cache = {}
    branches = []
    for line in refs:
        ref, sha = line.split("|", 1)
        if sha not in cache:
            left, right = map(int, git("rev-list", "--left-right", "--count", f"{baseline}...{sha}").split())
            unmatched = git("log", "--format=%H|%s", f"{baseline}..{sha}").splitlines()
            patches = git("cherry", baseline, sha).splitlines() if right else []
            patch_equivalent = [p[2:] for p in patches if p.startswith("-")]
            unique_patches = [p[2:] for p in patches if p.startswith("+")]
            cache[sha] = {
                "baseline_only_commits": left, "branch_only_commits": right,
                "disposition": "ANCESTOR_PRESERVED" if not right else
                    "PATCH_EQUIVALENT_OR_MERGE_ONLY" if not unique_patches else "DIVERGENT_REVIEW_REQUIRED",
                "branch_only_history": [dict(zip(("sha", "subject"), c.split("|", 1))) for c in unmatched],
                "patch_equivalent_commits": patch_equivalent, "unique_patch_commits": unique_patches,
                "tree_diff": git("diff", "--name-status", baseline, sha).splitlines() if right else [],
            }
        branches.append({"ref": ref, "sha": sha, **cache[sha]})
    unique = sorted({sha for row in branches for sha in row["unique_patch_commits"]})
    commits = [{"sha": sha, "subject": git("show", "-s", "--format=%s", sha),
                "files": git("diff-tree", "--no-commit-id", "--name-status", "-r", sha).splitlines()}
               for sha in unique]
    return {"baseline": baseline, "main": git("rev-parse", "origin/main"),
            "blueprint": git("rev-parse", "origin/implementation-of-master-blueprint"),
            "all_reachable_commit_count": int(git("rev-list", "--all", "--count")),
            "summary": dict(Counter(x["disposition"] for x in branches)),
            "refs": branches, "unique_commits": commits}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="HEAD")
    parser.add_argument("--output", default="docs/release/evidence/branch-audit.json")
    args = parser.parse_args()
    result = collect(args.baseline)
    (ROOT / args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": result["baseline"], "summary": result["summary"],
                      "unique_commits": len(result["unique_commits"])}))
