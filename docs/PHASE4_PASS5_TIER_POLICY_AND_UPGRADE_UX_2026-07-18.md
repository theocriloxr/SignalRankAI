# Phase 4 Pass 5 — Tier Policy and Upgrade UX

Date: 2026-07-18  
Baseline: Phase 4 Pass 4 canonical replacement (`ebad5d2`)  
Status: Complete

## Objective

Make tier entitlements, quotas, command/button access, signal depth, and upgrade
reasons consistent without allowing any subscription or internal tier to bypass
freshness, provider, market, risk, consent, evidence, feature-flag, or kill-switch
controls.

## Implemented

- Added `core/tier_policy.py` as the canonical server-side tier contract.
  - Free: 3/day, delayed educational preview, TP1 depth.
  - Premium: 15/day, exact risk context, lifecycle/paper/analytics workflow,
    TP1–TP2 depth.
  - VIP: 30/day, priority workflow, TP1–TP3 depth, execution preflight.
  - Admin and Owner remain non-purchasable internal roles with distinct ranks.
- Made `core/tier_constants.py`, `services/tier_policy.py`, Telegram command
  access, delivery policy, and tier feature projections delegate to the
  canonical contract.
- Added a canonical command matrix and callback/button feature matrix.
- Split Admin and Owner help pages so Owner-only controls are not presented as
  Admin entitlements.
- Added best-effort, non-blocking `upgrade_intent` events containing action,
  source, current/required tier, feature, decision code, and policy version.
- Replaced pressure/FOMO upgrade copy with explicit product value, transparent
  quotas, unchanged safety requirements, and no-guarantee language.
- Made the Free signal an educational proof preview without exact entry or stop
  loss; Premium receives TP1–TP2; VIP receives TP1–TP3.
- Limited the Telegram execution-preflight button to VIP while leaving actual
  automation disabled in the tier capability adapter.
- Enforced canonical daily quotas for every tier and canonical target depth in
  outcome formatting.
- Gated lifecycle monitoring through the same server-side button policy used by
  the rest of the tier surface.

## Safety invariants

Tier evaluation cannot bypass these gates, including for Admin and Owner:

- fresh quote
- trusted provider
- market open
- risk policy
- user consent
- kill switch
- evidence gate
- global feature flag

The tier contract grants eligibility and presentation only. It does not enable
live or copy trading, payments, webhooks, or rich Telegram messages.

## Verification

Focused and adjacent contract suite:

```text
python -m pytest tests/test_phase4_pass5_tier_policy_and_upgrade_ux.py tests/test_command_tier_contract.py tests/test_delivery_limit_guard.py tests/test_realtime_outcome_tp_tiers.py tests/test_realtime_outcome_delivery_tier_gates.py tests/test_formatter_delivery_pressure.py -q

38 passed, 2 warnings in 14.80s
```

Deterministic repository suite, excluding the same inherited collection blocker
used in Passes 2–4:

```powershell
$testFiles = @(rg --files tests -g 'test_*.py' | Where-Object { $_ -notlike '*test_broker_permission_validation.py' } | Sort-Object)
python -m pytest @testFiles -q --tb=no --disable-warnings

485 passed, 28 failed, 2 errors, 34 warnings in 54.68s
```

The delta from the Pass 4 baseline is **+15 passing tests, no new failures, and
no new errors**. The 28 failures and two Windows temporary-directory ACL errors
are inherited. The excluded collection blocker remains
`tests/test_broker_permission_validation.py`, which imports the missing
`verify_api_key` compatibility export from `web.app`; Pass 6 owns that API and
security boundary.

## Exit assessment

Pass 5 exit criteria are satisfied:

- all enumerated commands and buttons have cross-tier contract coverage;
- tier quotas, depths, capabilities, and formatting share one policy source;
- denied actions produce value-led, auditable upgrade intent data;
- no tier, including Owner, bypasses a safety gate;
- live execution activation remains out of scope and disabled pending Pass 6.
