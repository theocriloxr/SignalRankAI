# Container inputs and update procedure

All repository Dockerfile base images use immutable SHA-256 digests.
`Dockerfile.prod` deliberately matches `Dockerfile`: both enforce the image
release manifest, use the locked Python runtime with `pip check`, install the
runtime libpq library, and run the application as UID/GID 10001. Do not introduce
an alternate production build that skips these checks or runs as root.

Python build tools are pinned in `requirements-build-tools.txt`. Verification
images use the same file, including the separate security-tool environment.
Direct apt/apk package versions are pinned, and the previous DL3008 suppressions
have been removed. No Docker lint exception is needed for these package pins.

Versions were checked against the official indexes on 2026-10-04. The pinned
Python image's verified base layer is Debian 13 (trixie); the pinned PostgreSQL
Alpine image's verified base layer is Alpine 3.24.2. Package choices are:

| Image family | Packages |
| --- | --- |
| Debian Python builder | gcc 4:14.2.0-1; libpq-dev 17.11-0+deb13u1 |
| Debian Python runtime | libpq5 17.11-0+deb13u1; ca-certificates 20250419 |
| Backend verifier | redis-server 5:8.0.2-3+deb13u3, including the current Debian security revision |
| Static verifier | shellcheck 0.10.0-1 |
| Alpine restore drill | python3 3.14.8-r0; bash 5.3.9-r1; ca-certificates 20260909-r0 |

Sources: [Debian packages](https://packages.debian.org/trixie/),
[Debian security package index](https://deb.debian.org/debian-security/dists/trixie-security/main/binary-amd64/Packages.xz),
[Alpine package index](https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/APKINDEX.tar.gz).

For a security update, refresh the appropriate image digest and direct package
pins together. Check the actual base OS and repository availability, run Hadolint
on every Dockerfile, and rebuild the affected images. Run the release manifest
and dependency/security gates on the resulting exact commit before promotion.
A missing pinned package must fail the build rather than fall back to an
unreviewed version.

These pins do not establish bit-for-bit reproducibility of all transitive OS
packages: distro repositories can change and Python security-tool transitive
dependencies still resolve during installation. Nor does clean Docker lint
establish a vulnerability-free image. Retain image/SBOM auditing and the separate
runtime, dependency, SAST and deployment gates.
