# SignalRankAI v1.2.9 Artifact Manifest

Date: 2026-07-30
Release fingerprint: `v1.2.9-lifecycle-profile-observability-hotfix-20260730`

## Primary artifact

- `SignalRankAI_v1.2.9_LIFECYCLE_PROFILE_OBSERVABILITY_HOTFIX_RELEASE.zip`

## Supporting artifacts

- `SignalRankAI_v1.2.9_Lifecycle_Profile_Observability_Hotfix.patch`
- `SignalRankAI_v1.2.9_Lifecycle_Profile_Observability_Hotfix_Release_Notes.md`
- `SignalRankAI_v1.2.9_Certification_Report_2026-07-30.md`
- `SignalRankAI_v1.2.9_Production_Launch_Gate_Checklist.md`
- `SignalRankAI_v1.2.9_Railway_Full_System_Live_Paystack_Staging.env.example`
- `SignalRankAI_v1.2.9_Railway_Production_Launch.env.example`
- `SignalRankAI_v1.2.9_SHA256SUMS.txt`

## Code changes

- lifecycle SQL function scope repair;
- profile nested-session deadlock removal;
- explicit profile DB labels and timeout;
- timezone prompt reuse of preloaded user state;
- auxiliary-loop pool inventory fallback;
- DB health foreground timeout;
- atomic rolling-deploy ready-notification dedupe;
- v1.2.9 version, profiles, verifier and regression tests.

## Certification summary

- 751 Python files compiled, 0 failures
- 46 focused tests passed
- 210 broad selected tests passed, 3 dependency-bound assertions deselected
- 9/9 readiness checks passed
- schema, architecture, DB session, secret and governance checks passed
- no new migration; head remains `0027_launch_paper_trading`
