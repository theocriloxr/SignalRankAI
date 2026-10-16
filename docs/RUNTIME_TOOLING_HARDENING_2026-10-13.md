# Runtime tooling hardening

The backend root-filesystem scan identified vulnerable vendored code in the
base image's setuptools installation and in both virtual environments' pip
installations. Updating application urllib3/msgpack did not update the copies
inside pip. A credential-free container probe confirmed the embedded
`pip/_vendor/bom.cdx.json` manifests and physical vendored module directories.
Those findings were retained as real inventory, without suppressing advisories.

Canonical backend images now keep package installation in their builder stage.
The final filesystem removes pip from both runtime environments and removes
the unused base interpreter's pip, setuptools, wheel and ensurepip. Patched
setuptools/wheel dependencies required by either virtual environment remain.
OS package metadata remains available to the root-filesystem scanner. A clean
final image copies the stripped filesystem and keeps the existing non-root
UID, entrypoint, Python paths, native libraries and application permissions.

`SIGNALRANK_IMMUTABLE_RUNTIME=1` makes `INSTALL_AT_BOOT=true` fail before Python
or the application starts. Changing dependency bytes requires rebuilding and
accepting another image. Development environments retain their explicit boot
installation option when the immutable runtime flag is absent.

Deployment diagnostics use installed distribution metadata and packaging's
requirement/marker rules to check runtime dependency compatibility without an
installer. Missing dependencies, incompatible versions, conflicting installed
versions and malformed dependency metadata fail validation. Diagnostics omit
raw requirement URLs, credentials and exception messages. This check verifies
compatibility; image integrity and vulnerability acceptance are separate gates.

Both dependency environments, native ML/database imports and installed vendor
SDK parser/transport tests run after the Docker runtime stripping step. Actual
deployed root-filesystem scanning and application startup still require fresh
evidence for the new SHA. These changes do not close the outstanding OS or
mobile advisories, broker acceptance, financial activation or full soak gates.
