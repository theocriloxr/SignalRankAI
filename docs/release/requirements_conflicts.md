# Current source precedence decisions

The owner-supplied 16 October cross-chat contract and recovery/AI addendum refine
the older sources. Original documents stay private and unchanged. These are
policy decisions, not proof that every affected runtime path conforms.
Stable private source anchors and hashes are in crosschat_source_index.json.
The current contract is `bundle/START_HERE_MASTER_CODEX_PROMPT.md` in that index.

| Conflict | Controlling instruction | Disposition and remaining verification |
| --- | --- | --- |
| Broad discovery versus active scans | Current contract lines 36–37; SR-XCHAT-SEED-0012, 0026 | New scans/entries use 10 preferred core plus up to five qualified optional instruments per class. Preserve discovery/research and management of existing positions outside that set. Candidate lists do not establish qualification. All paths still require review. |
| Gemini versus OpenAI primary | Current contract line 37; SR-XCHAT-SEED-0078–0081 | Prefer OpenAI with configured Gemini review/failover and deterministic controls. Verify actual account model access before changing defaults. No provider probe or model change has occurred in this continuation. |
| 60/70/75 percent objectives | Current contract line 38; SR-XCHAT-SEED-0095 | Treat as research aspirations. Do not claim measured performance or lower gates to achieve a quota. |
| FREE/PREMIUM/VIP versus ELITE and roadmap tiers | Current contract line 39; SR-XCHAT-SEED-0159–0160 | Existing customers and schema require reconciliation. No invented price or new tier. ADMIN/OWNER are roles. Product decision and current billing evidence remain open. |
| Real payment keys in staging | Current contract line 40; SR-XCHAT-SEED-0161, 0227 | Separate test keys and test payments are required. Production webhook ownership and live funds stay unchanged. |
| Earlier enable-all requests versus money authority | Current contract line 41; SR-XCHAT-SEED-0124, 0213–0214 | Connection or historical feature request never authorizes orders, mirroring, withdrawals or payouts. Account-level approval and demo certification remain mandatory. |
| Green local checks versus protected release | Current contract line 42; SR-XCHAT-SEED-0220, 0231–0232 | Local execution can supply scoped evidence, but cannot impersonate hosted checks or independent last-push approval. No merge/deploy while gates are red. |
| Literal source preservation versus private conversations | Current contract lines 16–28 and package README | Keep exact wording in ignored local intake and originals; publish only hashes/anchors and reviewed sanitized dispositions. Repository source text already tracked remains referenced, without republishing the private package. |
| Existing six-state register versus latest eight dispositions | Current contract completeness mechanism and latest user request | Keep historical statuses intact in the older register. New universe uses the eight requested dispositions and a separate applicability/review field. INCOMPLETE with UNREVIEWED means unfinished review, not absent implementation. |
| Historical completed/PASS reports versus current acceptance | Current contract line 10 and regression ledger | Preserve reports and exact revisions as history. No automatic conversion into current verified requirements; current receipts must cover the specific clause. |
| Historical per-timeframe cooldowns (15m 10 min, 1h 20 min, 4h 90 min, 1d 6 h) versus current behavior | **Owner decision 24 Oct 2026: keep current behavior.** CX-FACT-18 | Current semantics stay: 600/1800/5400/21600 s act as maximum signal age (`core/production_integrity.py`), generation leases 15m 1 h / 1h 2 h / 4h 4 h / 1d 6 h (`engine/signal_lock.py`), 4 h per-user same-asset delivery cooldown. Locked by `tests/test_owner_decisions_20261024.py`. |
| Entry fingerprint 3 decimals versus 0.1 % relative bucket | **Owner decision 24 Oct 2026: keep current duplicate detection.** CX-FACT-18 | Effective suppression stays: 0.3 % logarithmic thesis band and 0.3 % semantic entry tolerance at persistence (`core/production_integrity.py`). Finding: the engine-local Redis pre-filter `engine/signal_deduplicator._entry_bucket` computes its bucket from the entry itself, so for prices ≥ 1 it is effectively an exact-match key (the same constant-ratio defect already fixed in `_entry_band`). Kept as-is by this decision; aligning it with `_entry_band` is a recommended, owner-approved-only change. Locked by the same test, no fingerprint migration. |
| XAUTUSDT session policy | **Owner decision 24 Oct 2026: keep current handling.** CX-FACT-24 | Registered as `tokenised_commodity` on the `crypto_24_7` calendar because the token trades continuously; gold's exchange sessions are not applied. Locked by the same test. |
| News blackout when no calendar source is available (block versus allow) | **Owner decision 30 Oct 2026: keep fail-open.** CX-RISK-01 | When no live or cached calendar source has event times, the 60-minute blackout around high-impact USD events does not block signals; the gate logs a warning at most every 10 minutes and `calendar_status()` reports `fallback: true`. With event times the blackout applies. Locked by `tests/test_owner_decisions_20261030.py`. |

The absence of `indexes/blueprint_modules.csv` is an unavailable-source item,
not permission to fabricate a 129-row module mapping from headings. The supplied
1,586-heading index was checked in source order. Unsupplied ChatGPT transcripts
remain SOURCE_NOT_AVAILABLE. All remaining semantic conflicts require individual
source anchors, a controlling instruction and a reviewed disposition.
