# SignalRankAI v1.3.2 Production Launch Gate

## Before deployment

- [ ] Railway environment name is `production` or `prod`.
- [ ] Full v1.3.2 archive replaces the previous source tree.
- [ ] Every `<...>` placeholder in Railway is replaced with a real secret/reference.
- [ ] `PUBLIC_TESTING_MODE=0`.
- [ ] `FULL_SYSTEM_STAGING_TEST_MODE=0`.
- [ ] `DELIVERY_AUDIENCE_ALLOWLIST` is empty.
- [ ] `RESEND_AUDIENCE_ALLOWLIST_ONLY=0`.
- [ ] `ENGINE_DELIVERY_ASYNC_FANOUT=1`.
- [ ] `RESEND_SKIP_WHEN_ENGINE_FANOUT_ACTIVE=0`.
- [ ] `RESEND_UNSENT_INTERVAL_SECONDS=30`.
- [ ] `RESEND_UNSENT_STARTUP_DELAY_SECONDS=15`.
- [ ] `SEND_OUTCOME_NOTIFICATIONS_ENABLED=1`.
- [ ] `OUTCOME_NOTIFICATION_INTERVAL_SECONDS=30`.
- [ ] `LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED=1`.
- [ ] `LIFECYCLE_TP_SL_NOTIFICATIONS_ENABLED=0` (canonical outcome dispatcher owns TP/SL).
- [ ] `MONITOR_REFRESH_INTERVAL_SECONDS=60`.
- [ ] `TELEGRAM_SEND_MAX_ATTEMPTS=3`.
- [ ] `TELEGRAM_RICH_MESSAGES_ENABLED=0` until separately certified.
- [ ] State Redis and delivery Redis are distinct production services.
- [ ] One application replica and one Uvicorn worker are used for the monolithic release.

## Required boot proof

- [ ] Log contains `[boot] SignalRankAI v1.3.2`.
- [ ] Log contains `release=v1.3.2-auto-delivery-callback-monitor-recovery-20260730`.
- [ ] Log contains `env=production`.
- [ ] No staging-mode or audience-allowlist warning appears.
- [ ] Scheduler registers `resend_unsent_signals_job`, `send_outcome_notifications`, and `refresh_monitor_snapshots_job`.
- [ ] Worker starts `RealtimeOutcomeTracker`.

## Required endpoint proof

- [ ] `/healthz` returns 200.
- [ ] `/livez` returns 200.
- [ ] `/readyz` returns 200.
- [ ] `/metrics/prometheus` returns 200.

## Telegram acceptance test

Use a normal non-owner user and a paid-tier user.

- [ ] `/start` and terms acceptance complete successfully.
- [ ] `/profile` reads and writes without timeout.
- [ ] A newly generated eligible signal arrives proactively; `/signals` is not required to discover it.
- [ ] Detailed signal card remains intact after Entry Triggered.
- [ ] Monitor opens as a separate reply/card.
- [ ] Refresh changes the `Updated` timestamp and current/best price.
- [ ] Highest/lowest price seen is numeric, never `None yet`.
- [ ] `Highest TP Reached` is independent from best price.
- [ ] Open Signal creates a fresh detailed card.
- [ ] Check Outcome returns a visible current or persisted status.
- [ ] TP/SL notification arrives automatically and contains only valid TP levels.
- [ ] Outcome/lifecycle notification buttons open the corresponding signal and monitor.

## Expected log markers

- `[send_signal_ok]`
- `[delivery_telegram_send_ok]`
- `[dispatch_sent_ok]`
- `[open_signal_send_ok]`
- `[monitor_refresh_ok]`
- `[lifecycle] ... event=...`
- `[outcome] ... sent...`

## Block launch if

- signal rows are stored but no Telegram send-success marker follows;
- detailed cards are edited into lifecycle summaries;
- callbacks produce no visible response;
- unsent recovery is skipped continuously;
- outcome notification rows remain pending/failed without retries;
- `/readyz` reports a delivery, migration, Redis, or production-cutover violation.
