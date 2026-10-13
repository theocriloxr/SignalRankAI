"""Validate installed dependencies without shipping a package installer."""
from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import Distribution, distributions
import json

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


def dependency_findings(installed: Iterable[Distribution]) -> list[dict[str, str]]:
    inventory = list(installed)
    versions: dict[str, str] = {}
    findings: list[dict[str, str]] = []
    for distribution in inventory:
        name = canonicalize_name(distribution.metadata["Name"] or "")
        if not name:
            findings.append({"package": "unknown", "reason": "missing_package_name"})
            continue
        version = distribution.version
        try:
            Version(version)
        except InvalidVersion:
            findings.append({"package": name, "reason": "invalid_installed_version"})
            continue
        if name in versions and versions[name] != version:
            findings.append({"package": name, "reason": "conflicting_installed_versions"})
        versions[name] = version
    for distribution in inventory:
        name = canonicalize_name(distribution.metadata["Name"] or "unknown")
        for raw in distribution.requires or ():
            try:
                requirement = Requirement(raw)
                if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                    continue
            except (InvalidRequirement, ValueError):
                findings.append({"package": name, "reason": "invalid_dependency_metadata"})
                continue
            dependency = canonicalize_name(requirement.name)
            actual = versions.get(dependency)
            if actual is None:
                findings.append({"package": name, "dependency": dependency, "reason": "missing_dependency"})
            elif not requirement.specifier.contains(actual, prereleases=True):
                findings.append({"package": name, "dependency": dependency, "reason": "incompatible_dependency_version"})
    # Never print raw requirements, URLs, paths or metadata exception messages.
    return sorted(findings, key=lambda row: (row["package"], row.get("dependency", ""), row["reason"]))


def main() -> int:
    findings = dependency_findings(distributions())
    print(json.dumps({"status": "FAIL" if findings else "PASS", "findings": findings}, sort_keys=True))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
