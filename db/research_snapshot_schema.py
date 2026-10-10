"""Shared admission check for canonical research snapshot mutation guards."""

RESEARCH_SNAPSHOT_SCHEMA_VALID_SQL = """
    (to_regclass('public.research_dataset_snapshots') IS NOT NULL
     AND (SELECT COUNT(*)=2 FROM pg_trigger AS guard
       JOIN (VALUES
         ('research_dataset_snapshots_immutable',27),
         ('research_dataset_snapshots_no_truncate',34)
       ) AS required(trigger_name,event_type)
         ON guard.tgrelid=to_regclass('public.research_dataset_snapshots')
        AND guard.tgname=required.trigger_name
        AND guard.tgtype=required.event_type
       WHERE NOT guard.tgisinternal
         AND guard.tgfoid=to_regprocedure('public.reject_research_evidence_mutation()')
         AND guard.tgenabled IN ('O','A')))
"""
