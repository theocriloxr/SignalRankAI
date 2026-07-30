-- SignalRankAI v1.3.0 production cutover verification (read-only)

SELECT version_num AS alembic_revision
FROM alembic_version;

SELECT COUNT(*) AS duplicate_outcome_signal_groups
FROM (
    SELECT signal_id
    FROM outcomes
    GROUP BY signal_id
    HAVING COUNT(*) > 1
) AS duplicate_groups;

SELECT COUNT(*) AS outcome_unique_guard_count
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = current_schema()
  AND tbl.relname = 'outcomes'
  AND idx.relname = 'uq_outcomes_signal_id'
  AND i.indisunique IS TRUE;

SELECT
    COUNT(*) FILTER (WHERE s.archived IS FALSE AND s.expired IS FALSE) AS unarchived_unexpired_signals,
    COUNT(*) FILTER (
        WHERE s.archived IS FALSE
          AND s.expired IS FALSE
          AND EXISTS (
              SELECT 1
              FROM signal_deliveries sd
              WHERE sd.signal_id = s.signal_id
                AND sd.sent_ok IS TRUE
                AND lower(COALESCE(sd.delivery_state, '')) IN ('sent','delivered','confirmed','reconciled')
                AND sd.telegram_chat_id IS NOT NULL
                AND sd.telegram_message_id IS NOT NULL
          )
    ) AS proof_backed_open_signals
FROM signals s;

SELECT
    lower(COALESCE(o.canonical_outcome, o.status, 'unknown')) AS outcome,
    COUNT(*) AS count
FROM outcomes o
GROUP BY 1
ORDER BY count DESC, outcome;

SELECT COUNT(*) AS terminal_outcomes_with_unarchived_signal
FROM outcomes o
JOIN signals s ON s.signal_id = o.signal_id
WHERE lower(COALESCE(o.status, '')) IN (
    'sl','tp','tp3','invalid','time_stop','partial_win_be','missed_entry','expired'
)
AND s.archived IS FALSE;
