# Container lint dispositions

SignalRankAI treats container lint warnings as release-blocking unless they are
either fixed or narrowly documented here.

## DL3008 — Debian package version pinning

The production Dockerfile intentionally does not hard-pin the exact Debian
versions of `gcc`, `libpq-dev`, `libpq5`, or `ca-certificates`.

The Python base image itself is pinned by immutable digest. During each image
build, `apt-get update` and `apt-get install --no-install-recommends` resolve
the security-maintained packages available for that exact Debian base. Hard
coding point-release package versions without pinning a Debian snapshot can
make security updates unavailable or leave builds stuck on stale vulnerable
package revisions.

Controls that make this exception narrow:

- only the two production `apt-get install` statements ignore DL3008;
- the base image is digest-pinned;
- package lists are removed from the final layers;
- compilers and headers exist only in the builder stage;
- the runtime stage contains only `libpq5` and `ca-certificates` from this
  exception;
- image vulnerability scanning and SBOM/provenance remain mandatory release
  evidence and can still block promotion.

## DL3013 — Python bootstrap tools

No exception is granted. `pip`, `setuptools`, and `wheel` are pinned in
`requirements-build-tools.txt`; application dependencies remain pinned by
`requirements.lock`.

Any new Hadolint warning is a release failure until it is fixed or separately
reviewed and documented.
