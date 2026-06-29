# Living Architecture Decision Record

Last updated: 2026-06-29
Owner: Architecture/Engineering

## ADR-001: Preserve Target Implementations During Reference Merge

Status: Accepted
Date: 2026-06-29

Problem: The sibling projects shared many paths but contained divergent
implementations. Bulk overwriting would risk destroying SignalRankAI1 fixes.

Alternatives considered:

- Replace target files wholesale with reference versions.
- Keep target files and ignore reference improvements.
- Review subsystem by subsystem and port compatible capabilities.

Decision: Preserve target implementations and port missing APIs, helpers, tests,
and behavior intentionally.

Consequences: Content diffs remain in same-path files, but owned file parity and
Python symbol parity are verified.

Future considerations: Use knowledge graph impact analysis before large refactors.

## ADR-002: Deterministic News Intelligence First

Status: Accepted
Date: 2026-06-29

Problem: News intelligence must not hallucinate live facts or silently invent
context.

Alternatives considered:

- Fetch and summarize live news directly inside the intelligence layer.
- Require callers to pass evidence and keep the layer deterministic.

Decision: `services/news_intelligence.py` accepts caller-provided stories and
returns normalized, scored evidence without fetching live sources.

Consequences: The layer is testable and safe, but provider ingestion and
historical learning remain separate work.

Future considerations: Add a provider aggregation layer and historical event
learning behind explicit provenance.

## ADR-003: Living Governance As Source Artifacts

Status: Accepted
Date: 2026-06-29

Problem: Governance requests can become stale prose if they are not part of the
repository and test suite.

Alternatives considered:

- Keep governance only in the audit report.
- Create living docs and validate their presence/schema in tests.

Decision: Add living registers under `docs/` and validate them through
`scripts/validate_governance_docs.py` and pytest.

Consequences: Future work has a documented maintenance burden, but drift is
easier to detect.

Future considerations: Generate parts of the feature and knowledge graph from
static analysis.

## ADR-004: Enrich Existing Decision Logs Instead Of Replacing Them

Status: Accepted
Date: 2026-06-29

Problem: The production engine already writes compact decision logs from many
branches. Replacing that flow would be risky before launch, but every decision
needs structured explainability.

Alternatives considered:

- Replace all decision logging call sites with a new decision service.
- Keep existing logging untouched and defer integration.
- Enrich `_log_decision()` so all existing call sites gain structured records.

Decision: Keep `persist_decision_log()` and the existing `_log_decision()`
surface, but enrich metadata with `decision_intelligence` and validation output.

Consequences: Backward compatibility is preserved and decision records become
available immediately. Some branches may still need richer inputs for Gemini,
news, shadow, liquidity, and historical analog sections.

Future considerations: Gradually pass richer subsystem payloads into
`_log_decision()` and add analytics over `decision_intelligence` metadata.
