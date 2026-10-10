"""Shared physical-index identity for migration and startup admission."""
from typing import Any, Mapping

PROFILE_HEALTH_INDEX_NAME = "ix_adaptive_evidence_profile_signal"
STRATEGY_HEALTH_SCHEMA_VALID_SQL = """
    (to_regclass('public.strategy_health_baselines') IS NOT NULL
     AND to_regclass('public.strategy_health_events') IS NOT NULL
     AND (SELECT COUNT(*)=4 FROM pg_trigger AS guard
       JOIN (VALUES
         ('public.strategy_health_baselines','strategy_health_baselines_immutable'),
         ('public.strategy_health_baselines','strategy_health_baselines_no_truncate'),
         ('public.strategy_health_events','strategy_health_events_immutable'),
         ('public.strategy_health_events','strategy_health_events_no_truncate')
       ) AS required(table_name,trigger_name)
         ON guard.tgrelid=to_regclass(required.table_name) AND guard.tgname=required.trigger_name
       WHERE NOT guard.tgisinternal
         AND guard.tgfoid=to_regprocedure('public.reject_research_evidence_mutation()')
         AND guard.tgenabled IN ('O','A')))
"""
_CATALOG_SQL = """
    SELECT c.relkind::text AS relkind,i.indisvalid,i.indisready,i.indisunique,a.amname,
           i.indrelid=to_regclass('public.adaptive_signal_evidence') AS expected_relation,
           i.indpred IS NULL AND i.indexprs IS NULL AND i.indnatts=2 AS simple_index,
           ARRAY(SELECT pg_get_indexdef(i.indexrelid,n,TRUE)
                 FROM generate_series(1,i.indnkeyatts) n) AS columns
    FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
    LEFT JOIN pg_index i ON i.indexrelid=c.oid
    LEFT JOIN pg_am a ON a.oid=c.relam
    WHERE ns.nspname='public' AND c.relname='ix_adaptive_evidence_profile_signal'
"""


# Fixed catalogue SQL shared by migration, synchronous startup and async runtime
# admission. No identifiers or criteria come from request/environment input.
_DEFINITION_SQL = """
    relkind='i' AND expected_relation AND simple_index AND amname='btree'
    AND NOT indisunique AND columns=ARRAY['profile_id','signal_id']::text[]
"""
PROFILE_HEALTH_INDEX_SQL = f"""
    SELECT index_state.*, ({_DEFINITION_SQL}) AS definition_matches,
           ({_DEFINITION_SQL} AND indisvalid AND indisready) AS valid
    FROM ({_CATALOG_SQL}) AS index_state
"""
PROFILE_HEALTH_INDEX_VALID_SQL = f"""
    EXISTS (SELECT 1 FROM ({PROFILE_HEALTH_INDEX_SQL}) AS index_state WHERE valid)
"""


def profile_health_index_definition_matches(row: Mapping[str, Any] | None) -> bool:
    return bool(row is not None and row.get("definition_matches") is True)


def profile_health_index_valid(row: Mapping[str, Any] | None) -> bool:
    return bool(profile_health_index_definition_matches(row) and row is not None
                and row.get("valid") is True)
