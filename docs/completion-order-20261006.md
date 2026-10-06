# Ordered completion record — 6 October 2026

This record preserves the user's requested order. An implemented component is
not a claim that its entire directive, deployment, financial certification or
required observation window is complete. The source prompts remain in
`docs/specs/20261005/`; the newer attachments were verified byte-for-byte against
those saved sources.

| Order | Work | Current state |
| --- | --- | --- |
| 1 | Research, backtesting, statistical validation, strategy health | In progress. The research ledger, label-availability purge, conservative legacy replay, optimizer recorder and canonical research UI are implemented in the candidate. Full instrument-specific stress, portfolio validation, approved health baselines and broader health/promotion UI remain unfinished. |
| 2 | Customer UX, personalization, broker execution experience | Queued after directive 1. The second copy of this attachment is identical and does not introduce another directive. Existing Telegram identity/return-flow fixes must be retained and deployed. |
| 3 | Complete web and mobile design | Queued. Existing authentication and transport foundations do not constitute finished product screens or native-device verification. |
| 4 | Repository gaps and multi-broker routing | Queued. Durable execution-plan routing and actual broker evidence still require closure. |
| 5 | Sections 126–363: completion, resilience, no placeholders | Queued after preceding attached prompts, as explicitly requested. |
| 6 | Earlier production repair, release and launch requirements | Continue verification throughout; do not waive hosted CI, provider/account certification, immutable release identity or soak requirements. |
| 7 | Self-improving research ecosystem | Queued after all preceding work: generated ideas, tested variants, failure analysis, persistent experiment memory and subsequent per-asset/per-class candidates. The ledger is a reusable foundation, not a completed autonomous strategy generator. |

## Evidence boundaries

- The Google Doc referenced by directive 1 remains inaccessible. Its independent
  review is unverified until readable source content is available.
- The published branch and production release must be reported separately from
  the isolated research candidates. Published `2c67a93e` passed 2,940 local tests
  and its five browser checks. Hosted CI passed both backend Python versions and
  the research browser job, but failed critical typing and frontend/mobile
  security. Those failures are retained. The next candidate corrects the type
  boundaries and adds independently scheduled health monitoring, lifecycle
  serialization, expiring cache approvals and worker supervision.
- A restricted Windows process environment prevented Pyright from discovering
  installed runtime packages, producing an incomplete local result. Verification
  now permits interpreter discovery and checks the actual locked runtime; a
  zero-error result with missing package resolution is not equivalent evidence.
- The health candidate `2cd31a7e` passed all 2,972 local tests, five owned browser
  checks, critical typing and source/governance checks. Its identical source
  tree was published as `6a720660`; hosted gates on that exact release commit
  remain required. The next candidate removes invented no-loss profit factors
  and hardens the existing spot-unit sizing helper without claiming venue or
  account-policy certification.
- The original production availability monitor continues. As of 02:13 UTC on
  6 October, it had 919 samples over 45.90 hours and status `DEGRADED`, observing
  `8f8583933a853a54ba1b3585610ee466903c08fc`, schema 0045. It is not the new
  candidate's clean 72-hour financial readiness certificate.
- Live execution remains disabled and the global kill switch remains enabled.
- No completion percentage, strategy profitability, broker fill, device test,
  full audit or soak pass may be manufactured to satisfy a target score.

## Release blockers carried forward

Published `13ad9f61` has the same source tree as immutable candidate `32d04b68`,
which passed 2,997 local tests with no skips. Hosted `d76ccc26` passed both
backend Python versions, the browser gate, critical typing, the legacy typing
budget, Python dependency audit and OpenGrep: zero findings/errors, 494 scanned
files with coverage/detection probes. Frontend/mobile audits still failed and
production approval was skipped. The upstream npm registry and reviewed
advisories still list no patched release for braces or node-forge on 6 October.
Their audit failures remain blockers; no package renaming, ignored advisory or
scan exclusion has been used to manufacture a pass.

The next health candidate removes heuristic-confidence Brier scores, validates
persisted calibrated evidence, evaluates calibration versions separately and
bounds each profile's outcome query in PostgreSQL. Its diagnosis remains signal
delivery evidence, not broker fills or approved per-instrument baseline proof.
The existing availability monitor has a retained 43,745-second observation gap
and is DEGRADED; elapsed hours cannot certify a clean release soak.

The following ledger repair records handled adaptive-evaluation failures after
rolling back an aborted transaction. It preserves closed results on retries and
records duplicate-profile trials as REJECTED. Actual PostgreSQL checks cover an
objective exception, a division-by-zero transaction failure and unavailable
failure recording. Pending crash/outage definitions remain visible and counted.

Hosted `6a720660` passed critical typing (zero errors), the legacy typing budget,
Ruff, Bandit and the browser gate. Python dependency scanning then found
Werkzeug CVE-2026-102598; the next security refresh pins the official patched
3.1.9 release. Frontend/mobile dependency security gates still fail.
The refreshed Python lock passed `pip-audit` with no known vulnerabilities.
The official PyPI wheel digest was verified and the Windows device-name
reproducer rejected `NUL:`, `CON:`, `COM1:` and `LPT9:` while accepting a normal
filename. This is dependency evidence, not a complete application security audit.
Upstream source: https://github.com/pallets/werkzeug/security/advisories/GHSA-g6x2-hccm-hh4m.
Provider coverage outside crypto and actual demo/funded-prop account rules and
fills remain incomplete. A final candidate must pass required CI, deploy to
every production application service using one approved immutable commit,
pass runtime/schema checks and complete a new observation window. Two complete
audits with no new material gaps are still required.
