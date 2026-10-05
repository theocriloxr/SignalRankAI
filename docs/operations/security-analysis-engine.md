# Complete security analysis

The required `security-semgrep` release gate runs the existing `p/default` and
`p/security-audit` rule packs with OpenGrep 1.30.0. Its stable gate ID is retained
for release evidence continuity. Semgrep 1.179.0 remains installed for comparison
and is selectable with `--engine semgrep`.

Semgrep reported no findings but repeatedly left taint analysis incomplete on
this application, including its hardcoded AWS-token rule. Raising its ordinary
file timeout did not resolve the internal fixpoint timeouts. Zero findings from
that incomplete scan do not pass certification.

The replacement was checked against the same frozen rule-pack bytes and source:
both engines detected the same six findings in unsafe Python/TypeScript fixtures
and no findings in the safe fixture. OpenGrep then completed 474 effective rules
across 484 files on candidate `4068dd9741edcefa20e173c52b8903f2b4d318bd`, with zero
findings and scan errors. This is evidence for the defined SAST surface, not a
claim of complete application security or resolution of dependency advisories.

CI and the static cleanroom install the official release asset using the fixed
SHA-256 in `scripts/install_opengrep.py`. The gate verifies the executable digest
again before invoking it. Unsupported platforms and mismatched downloads fail;
the installer never exposes an unverified download as the installed executable.

Every OpenGrep gate execution scans unsafe and safe fixtures first. It must
detect hardcoded credentials and Python/TypeScript code injection, reject unsafe
code with the expected exit status, scan all fixtures, report no analysis
errors/timeouts and leave the safe fixture clean. These fixture files are never
executed. Probe evidence is saved beside the application report as
`semgrep.probe.json`; its expected findings are not application findings.

The application scan retains the prior rule packs, targets, existing exclusions,
strict error handling, timeout settings and minimum scanned-file threshold.
Application findings, malformed reports, tool errors and incomplete analysis
still fail the release. No vulnerability advisory allowlist was added.

Upstream references: [OpenGrep release](https://github.com/opengrep/opengrep/releases/tag/v1.30.0)
and [analyzer changes](https://github.com/opengrep/opengrep/blob/main/CHANGELOG.md).
