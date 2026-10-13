"""Build a closed, auditable Debian/Python application filesystem.

Run as root only inside the Docker intermediate stage. This is file selection,
not vulnerability filtering: every retained Debian payload keeps its original
package record and licence. Unexpected native dependencies fail the build.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


DESTINATION = Path("/signalrank-runtime")
# These optional CPython extensions serve interactive terminals or libuuid.
# uuid.py supplies its standard, OS-random-backed pure-Python implementation.
OPTIONAL_EXTENSIONS = ("_curses", "readline.", "_uuid.")
ABSENT_PACKAGES = {
    "bash", "bsdutils", "libacl1", "libblkid1", "liblastlog2-2", "libmount1",
    "libncursesw6", "libsmartcols1", "libsystemd0", "libtinfo6", "libudev1",
    "libuuid1", "login", "mount", "ncurses-base", "ncurses-bin", "perl-base",
    "util-linux",
}


def canonical(path: Path) -> str:
    """Debian merged-/usr names refer to the same physical payload."""
    return str(path.resolve(strict=True))


def parse_status(text: str) -> dict[str, str]:
    records = {}
    for stanza in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in stanza.splitlines()
                      if ": " in line and not line.startswith(" "))
        if fields.get("Status") != "install ok installed":
            continue
        key = fields["Package"] + ":" + fields["Architecture"]
        records[key] = stanza + "\n"
    return records


def parse_ldd(output: str, returncode: int) -> set[Path]:
    if "not found" in output:
        raise RuntimeError("unresolved native dependency")
    if returncode:
        # Statically linked executables have no dynamic library closure.
        if "not a dynamic executable" in output or "statically linked" in output:
            return set()
        raise RuntimeError("native dependency inspection failed")
    return {Path(value) for value in re.findall(r"(?:=>\s+|^\s*)(/[^\s]+)\s+\(", output, re.M)}


def assemble(destination: Path = DESTINATION) -> None:
    set_owner = getattr(os, "chown", None)
    if destination != DESTINATION or destination.exists() or getattr(os, "geteuid", lambda: -1)() != 0 or not callable(set_owner):
        raise RuntimeError("requires an empty fixed Docker build destination and root")
    destination.mkdir()
    sources: dict[str, str] = {}

    def payload(source: Path) -> None:
        if not source.is_file():
            raise RuntimeError(f"required runtime file absent: {source}")
        target = destination / source.relative_to("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=True)
        sources[str(source)] = canonical(source)

    def tree(source: Path, *, optional_python: bool = False) -> None:
        if not source.is_dir():
            raise RuntimeError(f"required runtime directory absent: {source}")
        # Dereference file links (including CA certificates); preserve no host
        # absolute symlinks that could escape the destination during assembly.
        for item in sorted(source.rglob("*")):
            if item.is_dir():
                (destination / item.relative_to("/")).mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                if optional_python and item.parent.name == "lib-dynload" and item.name.startswith(OPTIONAL_EXTENSIONS):
                    continue
                payload(item)

    tree(Path("/usr/local"), optional_python=True)
    tree(Path("/opt/venv"))
    tree(Path("/opt/market-data-sdk"))
    tree(Path("/app"))
    payload(Path("/usr/bin/dash"))
    payload(Path("/etc/os-release"))
    payload(Path("/etc/debian_version"))
    tree(Path("/etc/ssl/certs"))
    payload(Path("/etc/ssl/openssl.cnf"))
    tree(Path("/usr/share/zoneinfo"))
    # OpenSSL providers and iconv/SASL/Kerberos modules can be loaded via dlopen
    # and are not necessarily named in an executable's DT_NEEDED table.
    for directory in ("ossl-modules", "gconv", "sasl2", "krb5/plugins"):
        for base in Path("/usr/lib").glob("*-linux-gnu"):
            path = base / directory
            if path.is_dir():
                tree(path)
    for pattern in ("libnss_dns.so*", "libnss_files.so*"):
        for path in Path("/usr/lib").glob("*-linux-gnu/" + pattern):
            payload(path)

    inspected: set[str] = set()
    while True:
        pending = sorted(set(sources.values()) - inspected)
        if not pending:
            break
        for name in pending:
            inspected.add(name)
            path = Path(name)
            with path.open("rb") as stream:
                if stream.read(4) != b"\x7fELF":
                    continue
            result = subprocess.run(["/usr/bin/ldd", name], capture_output=True, text=True, check=False)
            for dependency in sorted(parse_ldd(result.stdout + result.stderr, result.returncode)):
                if str(dependency) not in sources:
                    payload(dependency)

    # Keep original OS package records for ALL selected Debian files, including
    # libraries. Never derive the inventory from a vulnerability allowlist.
    records = parse_status(Path("/var/lib/dpkg/status").read_text())
    owners: dict[str, str] = {}
    for listing in Path("/var/lib/dpkg/info").glob("*.list"):
        package = listing.name[:-5]
        if package not in records:
            matches = [key for key in records if key.split(":")[0] == package]
            if len(matches) != 1:
                continue
            package = matches[0]
        for filename in listing.read_text().splitlines():
            path = Path(filename)
            if path.is_file():
                owners[canonical(path)] = package
    selected: dict[str, list[str]] = {}
    for name, resolved in sorted(sources.items()):
        if name.startswith(("/usr/local/", "/opt/", "/app/")):
            continue
        owner = owners.get(resolved)
        if name == "/etc/ssl/certs/ca-certificates.crt":
            # update-ca-certificates generates this from that package's inputs.
            owner = "ca-certificates:all"
            owners[resolved] = owner
        if not owner:
            raise RuntimeError(f"unattributed OS runtime payload: {name}")
        selected.setdefault(owner, []).append(name)
    unexpected = ABSENT_PACKAGES.intersection(key.split(":")[0] for key in selected)
    if unexpected:
        raise RuntimeError("unexpected OS dependency: " + ", ".join(sorted(unexpected)))
    inventory = destination / "var/lib/dpkg"
    (inventory / "info").mkdir(parents=True)
    (inventory / "status").write_text("\n".join(records[key] for key in sorted(selected)))
    for package, files in sorted(selected.items()):
        (inventory / "info" / (package + ".list")).write_text("\n".join(files) + "\n")
        copyright_file = Path("/usr/share/doc") / package.split(":")[0] / "copyright"
        if copyright_file.is_file():
            payload(copyright_file)

    (destination / "bin").mkdir(exist_ok=True)
    (destination / "bin/sh").symlink_to("/usr/bin/dash")
    (destination / "usr/bin/sh").symlink_to("dash")
    for directory in ("tmp", "run", "dev", "proc", "sys", "home/signalrank"):
        (destination / directory).mkdir(parents=True, exist_ok=True)
    (destination / "tmp").chmod(0o1777)
    set_owner(destination / "home/signalrank", 10001, 10001)
    for path in (destination / "app").rglob("*"):
        set_owner(path, 10001, 10001)
    set_owner(destination / "app", 10001, 10001)
    (destination / "etc/passwd").write_text("root:x:0:0:root:/root:/usr/sbin/nologin\nsignalrank:x:10001:10001:SignalRankAI:/home/signalrank:/usr/sbin/nologin\n")
    (destination / "etc/group").write_text("root:x:0:\nsignalrank:x:10001:\n")
    (destination / "etc/nsswitch.conf").write_text("passwd: files\ngroup: files\nhosts: files dns\n")
    (destination / "etc/ld.so.conf").write_text("/usr/local/lib\n/usr/lib/x86_64-linux-gnu\n/lib/x86_64-linux-gnu\n")
    subprocess.run(["/sbin/ldconfig", "-r", str(destination)], check=True)
    manifest = {
        "format_version": 1,
        "scope": "minimal-runtime-payload",
        "os_packages": sorted(selected),
        "optional_python_extensions_omitted": list(OPTIONAL_EXTENSIONS),
        "files": [{"path": name, "sha256": hashlib.sha256((destination / name.lstrip("/")).read_bytes()).hexdigest(),
                   "os_package": owners.get(resolved)} for name, resolved in sorted(sources.items())],
    }
    (destination / "etc/signalrank-runtime-manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    print(json.dumps({"runtime_files": len(sources), "os_packages": sorted(selected)}))


if __name__ == "__main__":
    if sys.argv[1:] != ["--docker-build"]:
        raise SystemExit("only --docker-build is supported")
    assemble()
