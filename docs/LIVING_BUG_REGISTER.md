# Living Bug Register

Last updated: 2026-06-29
Owner: Engineering

Track every discovered bug with root cause, reproduction, severity, affected
files, resolution, verification tests, and regression prevention.

| ID | Title | Root Cause | Reproduction Steps | Severity | Affected Files | Resolution | Verification Tests | Regression Prevention | Status | Date Opened | Date Resolved |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BUG-C001 | Signal action keyboard emitted dead callback without signal id | Callback payload defaulted to `mt5_trade` when no `signal_id` existed. | Build `_build_signal_action_keyboard({"asset": "BTCUSDT"})` and inspect first-row callbacks. | Medium | `signalrank_telegram/commands.py` | Removed trade callback unless a signal id exists. | `tests/test_command_contracts.py` | Contract test asserts no dead callback. | Closed | 2026-06-29 | 2026-06-29 |
| BUG-C002 | Gemini audit command imported missing helper | `services.gemini_ml.audit_recent` was referenced but absent. | Run `/gemini_audit` path or import helper. | Medium | `services/gemini_ml.py`, `signalrank_telegram/commands.py` | Added DB-backed `audit_recent()` and command session usage. | `tests/test_command_contracts.py` | Command contract mocks session/helper. | Closed | 2026-06-29 | 2026-06-29 |
| BUG-C003 | TP parser ignored dict `tp` entries | Parser handled numeric/list values but not all dict target keys. | Call `_parse_tp_levels([{"tp": "102.5"}])`. | Low | `engine/realtime_outcome_tracker.py` | Added `price`, `tp`, `target`, and `value` dict support. | `tests/test_time_stop_outcome_persistence.py` | Parser contract test. | Closed | 2026-06-29 | 2026-06-29 |
| BUG-001 | Live Telegram workflow coverage gap | Not a code defect; E2E coverage is incomplete. | Run suite without Bot API sandbox and observe no full workflow send. | High | `signalrank_telegram/*` | Pending. | Planned sandbox E2E tests | Add gated E2E workflow suite. | Open | 2026-06-29 |  |
