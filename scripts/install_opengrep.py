#!/usr/bin/env python3
"""Install the checksum-pinned OpenGrep engine from its official release."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import platform
import tempfile
from urllib.request import urlopen

VERSION = "1.30.0"
ASSETS = {
    ("Linux", "x86_64"): ("opengrep_manylinux_x86", "35779bdd72e92129c8df2a77f0c55e8c08356801ea92591ef32108d6b28d564c"),
    ("Linux", "aarch64"): ("opengrep_manylinux_aarch64", "a5d5a4a58ba5d46ff51e921663da1c2bba38f4b03987f4aeec87f16c6ad3ecae"),
    ("Windows", "AMD64"): ("opengrep_windows_x86.exe", "b5cf4f8fe9f44e030aab2d579d96bd395c139db1f1ba66633676ff4d5ebc7c39"),
}


def asset():
    key = (platform.system(), platform.machine())
    if key not in ASSETS:
        raise RuntimeError(f"No approved OpenGrep binary for platform {key}")
    return ASSETS[key]


def verify_binary(path: Path) -> None:
    _, expected = asset()
    with path.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError("OpenGrep binary checksum does not match the approved release")


def install(directory: Path) -> Path:
    name, _ = asset()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ("opengrep.exe" if platform.system() == "Windows" else "opengrep")
    if destination.exists():
        verify_binary(destination)
        return destination
    url = f"https://github.com/opengrep/opengrep/releases/download/v{VERSION}/{name}"
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
            staged = Path(output.name)
            with urlopen(url, timeout=120) as response:  # nosec B310 -- fixed official HTTPS release
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        verify_binary(staged)
        staged.chmod(0o755)
        os.replace(staged, destination)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    print(f"Installed verified OpenGrep {VERSION}: {install(args.directory)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
