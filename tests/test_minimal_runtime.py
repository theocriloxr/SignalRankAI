"""Native dependency and OS attribution fail closed in the runtime builder."""
from pathlib import Path

import pytest

from scripts.build_minimal_runtime import parse_ldd, parse_status


def test_missing_native_library_cannot_be_published():
    with pytest.raises(RuntimeError, match="unresolved"):
        parse_ldd("libneeded.so => not found\n", 0)
    with pytest.raises(RuntimeError, match="inspection failed"):
        parse_ldd("permission denied", 1)


def test_loader_and_transitive_libraries_are_copied():
    assert parse_ldd("\tlinux-vdso.so.1 (0x123)\n\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x123)\n\t/lib64/ld-linux-x86-64.so.2 (0x456)\n", 0) == {
        Path("/lib/x86_64-linux-gnu/libc.so.6"), Path("/lib64/ld-linux-x86-64.so.2")}
    assert parse_ldd("statically linked", 0) == set()


def test_original_source_and_version_records_survive_unchanged():
    installed = "Package: fixture\nStatus: install ok installed\nArchitecture: amd64\nSource: source-fixture (2.1)\nVersion: 2.1+b1\nDescription: example\n continuation"
    removed = "Package: unused\nStatus: deinstall ok config-files\nArchitecture: all\nVersion: 1"
    assert parse_status(installed + "\n\n" + removed) == {"fixture:amd64": installed + "\n"}
