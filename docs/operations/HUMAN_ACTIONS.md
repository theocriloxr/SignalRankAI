# Human Actions

Updated: 2026-08-23. All independent repository, schema, registry, configuration, deployment, and structural work is complete.

## STAGING_REVIEW_REQUIRED — SRA-V81-HUMAN-001

- Environment/service: Railway staging bot on `bountiful-miracle`.
- Reason: post-fix proof has nine confirmed delivery receipts, but all recovered deliveries were correctly rejected as stale and no fresh resulting paper position exists.
- Minimum action: open the configured staging bot from a Telegram account that has pressed Start, run `/start`, select paper mode, and enable auto-paper.
- Expected result: one fresh qualified staging signal is delivered exactly once with a stable signal ID and exactly one eligible paper position opens.
- Verification: Codex reruns the strict runtime certifier and checks chat/message IDs, paper ledger, lifecycle monotonicity, and duplicate counts.
- Security: do not paste any token, secret, key, database URL, or Redis URL into chat.
- Resume: confirm only that the staging bot was started and the test user selected auto-paper mode.

## CREDENTIAL_REQUIRED — SRA-V81-HUMAN-002

- Secret/environment: `APP_AUTH_SECRET`, Railway staging.
- Reason: absent on all three application roles during the redacted inventory.
- Minimum action: place one strong staging-only value in Railway's staging secret store for all roles; it must differ from production.
- Verification: Codex checks presence only and reruns readiness/security gates.
- Security: never send or commit the value.

## PRODUCTION_APPROVAL_REQUIRED — SRA-V81-HUMAN-003

Production remains untouched. Approval is not currently requested because runtime, Paystack test, backup/restore, and 24-hour soak gates are incomplete. When all gates pass, the only valid production instruction is `PROMOTE_TO_PRODUCTION`.
