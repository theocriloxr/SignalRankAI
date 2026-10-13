# Minimal backend runtime qualification

The backend candidate assembles a smaller filesystem from the same pinned
Debian/Python builder and patched stable libraries. It copies Python, both locked
virtual environments, the application, certificates, timezone data, POSIX dash,
and the complete detected native-library dependency closure. OpenSSL, iconv,
SASL, Kerberos and NSS modules receive explicit treatment for dynamic loading.

Every retained Debian payload keeps its original package/version/source record.
Generated CA bundles are attributed to ca-certificates. The image records file
hashes and package ownership in `/etc/signalrank-runtime-manifest.json` and keeps
the original package licences. This does not change vulnerability definitions,
suppress advisories or import unstable Debian packages. The published rootfs
must be scanned before any finding is marked closed.

The image omits Bash and unused administrative utility families, including
util-linux, Perl and systemd. The canonical startup script uses POSIX `sh`;
release-source checks, guarded migration ownership, schema admission, quiescent
certification, authentication checks and single-process role selection remain.
The previous sed pipelines are replaced by a bounded-command Python diagnostic
helper. Current deployment configuration uses `sh start.sh`. Any service with an
explicit old `bash start.sh` override needs that command updated with the image.
Backup jobs using their separate PostgreSQL image are outside this change.

Optional CPython `_curses`, `readline` and `_uuid` native extensions are omitted.
They are not application requirements; Python's documented uuid fallback still
supports UUID generation with OS randomness. Interactive terminal editing is not
part of the runtime contract. The native import, UUID and SDK checks execute
inside the assembled filesystem, together with actual startup guard tests.

Qualification requires a new rootfs scan, native/SDK build checks, isolated
database/Redis startup, backend regression and static gates. Runtime payload
minimization alone does not certify providers, signal delivery, brokers,
financial execution, hosted CI or a completed full staging soak.
