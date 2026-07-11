# Phase 4 Pass 1 — Live Validation, Queue-Age Gate, and Production Addendum

## Scope

This pass implements the approved Phase 3 refinements and starts Phase 4 with the live-price validation/stale-signal blocking track.

## Addendum injected into the master plan

1. **Weekend / off-market throttling**
   - `ENGINE_OFF_MARKET_THROTTLE_ENABLED=1`
   - If all non-crypto markets are closed and no crypto assets are open in the selected universe, the engine sleeps for `ENGINE_OFF_MARKET_SLEEP_SECONDS` instead of repeatedly polling dead FX/commodity/stock providers.

2. **Live migration safety**
   - New production indexes are added through Alembic revision `0017_concurrent_signal_delivery_indexes.py`.
   - PostgreSQL uses `CREATE INDEX CONCURRENTLY IF NOT EXISTS` and drops with `DROP INDEX CONCURRENTLY IF EXISTS` to avoid blocking active `signals`, `signal_deliveries`, and `active_signal_messages` tables.

3. **Time-to-Telegraph queue gate**
   - `engine.delivery_freshness.evaluate_time_to_telegraph()` now blocks signals that sit too long between generation and outbound Telegram send.
   - Block reason: `expired_in_queue:<age>s><budget>s`.
   - The returned freshness state is `EXPIRED_IN_QUEUE`.

4. **Telegram Bot API 10.1 Rich Messages support**
   - Added `signalrank_telegram/rich_messages.py`.
   - Rich-message support is optional and fail-safe behind `TELEGRAM_RICH_MESSAGES_ENABLED=0` by default.
   - Existing HTML text delivery remains the fallback.
   - Rich HTML uses heading/table/details patterns for TP/SL and AI explanation once production-tested.

5. **Prompt decoupling and versioning**
   - Added `configs/prompts/gemini_prompts.json`.
   - Added `services/prompt_registry.py`.
   - Key Gemini prompts now load from versioned config instead of hardcoded Python-only strings.
   - Runtime prompt version: `gemini_prompts_v1_2026_07_11`.

## Files changed

- `engine/delivery_freshness.py`
- `data/get_live_price.py`
- `engine/off_market.py`
- `engine/core.py`
- `signalrank_telegram/rich_messages.py`
- `signalrank_telegram/bot.py`
- `services/prompt_registry.py`
- `services/gemini_ml.py`
- `configs/prompts/gemini_prompts.json`
- `.env.production.template`
- `alembic/versions/0017_concurrent_signal_delivery_indexes.py`

## Important production notes

- Keep `TELEGRAM_RICH_MESSAGES_ENABLED=0` until one private canary chat proves `sendRichMessage` works with your deployed Telegram library/raw Bot API path.
- Do not run standard blocking index migrations on active tables. Use the supplied concurrent migration.
- If signal volume drops after this patch, inspect logs for `EXPIRED_IN_QUEUE`, `final_entry_drift`, `tp1_already_hit_before_send`, and `final_live_price_unavailable`. Those are protective blocks, not delivery bugs.

## Expected log markers

Good blocks:

```text
[delivery] blocked stale signal ... reason=expired_in_queue:...
[delivery] blocked stale signal ... reason=final_entry_drift:...
[delivery] blocked stale signal ... reason=tp1_already_hit_before_send
```

Good sends:

```text
[delivery_freshness] live_quote symbol=... price=... provider=... latency_ms=...
[telegram_send_ok]
[delivery_proof_write] sent_ok=True
[dispatch_sent_ok]
```

Optional rich canary:

```text
[telegram_rich_send_ok]
```

Fallback if unsupported:

```text
[telegram_rich_send_fallback] ... falling_back_to_send_message
```
