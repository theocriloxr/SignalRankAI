# Container security acceptance, 11 October 2026

The isolated Railway staging runtime for commit
`1cc4e556004e81614c8afe5befee0afc12304be8` was scanned with checksum-verified
Trivy 0.75.0 against its actual Debian 13.7 package inventory. The scan covered
Debian OS packages and reported 48 HIGH package/advisory rows. It did not certify
Python dependencies, native applications, broker behavior, or live execution.

Both application Dockerfiles now explicitly install the Debian security versions
of OpenSSL (`3.5.7-1~deb13u3`) and PCRE2 (`10.46-1~deb13u3`) in both stages.
The base-image digest and non-root runtime identity remain pinned. The replacement
image must be built and rescanned before these four fixable rows can be closed.

Primary references:

- [OpenSSL / DSA-6531-1](https://security-tracker.debian.org/tracker/CVE-2026-84782)
- [PCRE2 / DSA-6530-1](https://security-tracker.debian.org/tracker/CVE-2026-103111)

The original scan also reported unfixed stable-Debian findings in util-linux,
ACL, ncurses, systemd and Perl packages. Debian currently classifies several as
minor issues or postponed updates. Those classifications do not erase the
scanner findings or establish application-level non-exploitability. Do not mix
unstable Debian packages into the production runtime to force a clean scan.

The corresponding acceptance remains **BLOCKED**, with no vulnerability
suppression or fabricated fixed versions. An advisory-only source deployment,
if explicitly performed, must retain this limitation in its evidence and keep
financial execution disabled. It is not a security or live-money certification.
The mobile dependency audit separately retains four HIGH rows, including
node-forge; native release acceptance also remains blocked.

The hosted CI retry for the preceding commit did not start because GitHub
reported a billing lock. Independent local checks and Railway image build checks
are separate evidence; neither may be reported as a passing hosted CI run.
