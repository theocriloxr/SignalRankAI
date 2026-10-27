"""Complete a reviewed Telegram/web account merge without losing history.

``complete_telegram_link_request`` never auto-merges: when a web account links a
Telegram identity that already has its own bot account, it records a
``pending_review`` row in ``account_merge_records``. Until now nothing completed
that review, so the person's bot subscription, deliveries, paper trading,
watchlists and preferences stayed on a separate account and the Telegram link
never finished.

``plan_account_merge`` is read-only and reports exactly what would move.
``apply_account_merge`` performs it in the caller's transaction:

* Ownership is discovered from the live schema (every single-column foreign key
  to ``users.id``), so tables added later are covered automatically.
* A row moves only when it cannot collide with a unique index on the kept
  account, and only when every user-owned parent row it references (paper
  account, broker connection, delivery, ...) already belongs to the kept
  account. Rows that cannot move stay on the archived account, are counted in
  the evidence and are never deleted.
* Credentials and security history never move: passwords, sessions, MFA,
  recovery codes, API tokens/keys, security events. The archived account's
  sessions are revoked and it can no longer sign in.
* Execution consent stored outside these tables is not transferred; the person
  opts in again on the kept account.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from core.tier_policy import tier_rank

# Credentials, audit history and the merge bookkeeping itself stay with the
# account they were created for.
NEVER_MOVED = frozenset({
    "user_sessions", "password_credentials", "login_challenges", "account_recovery_codes",
    "user_mfa_totp", "api_tokens", "api_keys", "api_usage_ledger", "security_events",
    "account_link_requests", "account_merge_records",
})
# Only the Telegram identity moves; email/password logins stay with their account.
ROW_FILTERS = {"auth_identities": "provider = 'telegram'"}
# Copied onto the kept account only where it has no value of its own.
FILL_IF_EMPTY = ("display_name", "country", "timezone", "locale", "primary_phone", "referred_by",
                 "paystack_customer_code")


class MergeRefused(Exception):
    """The merge record or accounts are not in a state that can be merged."""


@dataclass
class MergePlan:
    merge_id: str
    canonical_user_id: int
    merged_user_id: int
    telegram_user_id: int | None
    movable: dict[str, int] = field(default_factory=dict)
    kept: dict[str, int] = field(default_factory=dict)
    never_moved: dict[str, int] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    account_changes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "merge_id": self.merge_id,
            "canonical_user_id": self.canonical_user_id,
            "merged_user_id": self.merged_user_id,
            "telegram_user_id": self.telegram_user_id,
            "movable": dict(sorted(self.movable.items())),
            "kept_on_archived_account": dict(sorted(self.kept.items())),
            "never_moved": dict(sorted(self.never_moved.items())),
            "failed": dict(sorted(self.failed.items())),
            "account_changes": self.account_changes,
        }


def _ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


async def _user_references(session: Any) -> list[tuple[str, str]]:
    rows = await session.execute(text(
        "SELECT c.conrelid::regclass::text, a.attname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
        "WHERE c.contype = 'f' AND c.confrelid = 'users'::regclass AND array_length(c.conkey, 1) = 1 "
        "AND c.conrelid <> 'users'::regclass ORDER BY 1, 2"
    ))
    return [(str(table), str(column)) for table, column in rows.all()]


async def _unique_column_sets(session: Any, table: str) -> list[tuple[list[str], bool]]:
    """Unique indexes and primary keys as (columns, simple); expression/partial ones are not simple."""
    rows = await session.execute(text(
        "SELECT ARRAY(SELECT a.attname FROM unnest(i.indkey) WITH ORDINALITY k(attnum, ord) "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum ORDER BY k.ord), "
        "(i.indexprs IS NULL AND i.indpred IS NULL) "
        "FROM pg_index i WHERE i.indrelid = CAST(:table AS regclass) AND i.indisunique"
    ), {"table": table})
    return [(list(columns or []), bool(simple)) for columns, simple in rows.all()]


async def _owned_parents(session: Any, table: str, owners: dict[str, str]) -> list[tuple[str, str, str]]:
    """(child column, parent table, parent key) for FKs into other user-owned tables."""
    rows = await session.execute(text(
        "SELECT a.attname, c.confrelid::regclass::text, pa.attname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
        "JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = c.confkey[1] "
        "WHERE c.contype = 'f' AND c.conrelid = CAST(:table AS regclass) AND array_length(c.conkey, 1) = 1 "
        "AND c.confrelid <> 'users'::regclass AND c.confrelid <> c.conrelid"
    ), {"table": table})
    return [(str(col), str(parent), str(key)) for col, parent, key in rows.all() if str(parent) in owners]


def _order(owners: dict[str, str], parents: dict[str, list[tuple[str, str, str]]]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(table: str, stack: tuple[str, ...]) -> None:
        if table in seen or table in stack:
            return
        for _, parent, _ in parents.get(table, []):
            visit(parent, stack + (table,))
        seen.add(table)
        ordered.append(table)

    for table in sorted(owners):
        visit(table, ())
    return ordered


async def _load(session: Any, merge_id: str, *, lock: bool) -> tuple[dict, dict, dict]:
    suffix = " FOR UPDATE" if lock else ""
    record = (await session.execute(text(
        "SELECT merge_id, canonical_user_id, merged_user_id, status, evidence FROM account_merge_records "
        "WHERE merge_id = :merge_id" + suffix
    ), {"merge_id": str(merge_id)})).mappings().first()
    if not record:
        raise MergeRefused("merge_not_found")
    if str(record["status"]) != "pending_review":
        raise MergeRefused("merge_not_pending")
    canonical_id, merged_id = int(record["canonical_user_id"]), int(record["merged_user_id"])
    if canonical_id == merged_id:
        raise MergeRefused("merge_same_account")
    users = {}
    for user_id in sorted((canonical_id, merged_id)):  # stable lock order
        row = (await session.execute(text(
            "SELECT id, telegram_user_id, account_status, tier, premium_until, auto_renew, "
            "paystack_subscription_code, " + ", ".join(FILL_IF_EMPTY) + " FROM users WHERE id = :uid" + suffix
        ), {"uid": user_id})).mappings().first()
        if not row:
            raise MergeRefused("merge_account_missing")
        users[user_id] = dict(row)
    canonical, merged = users[canonical_id], users[merged_id]
    if str(canonical.get("account_status") or "active") != "active":
        raise MergeRefused("canonical_account_not_active")
    if canonical.get("telegram_user_id") not in (None, merged.get("telegram_user_id")):
        raise MergeRefused("canonical_has_other_telegram")
    return dict(record), canonical, merged


def _account_changes(canonical: dict, merged: dict) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if tier_rank(merged.get("tier")) > tier_rank(canonical.get("tier")):
        changes["tier"] = merged.get("tier")
    if merged.get("premium_until") and (
        not canonical.get("premium_until") or merged["premium_until"] > canonical["premium_until"]
    ):
        changes["premium_until"] = merged["premium_until"]
    if merged.get("paystack_subscription_code") and not canonical.get("paystack_subscription_code"):
        # The renewing subscription follows the person; keep its renewal choice with it.
        changes["paystack_subscription_code"] = merged["paystack_subscription_code"]
        changes["auto_renew"] = bool(merged.get("auto_renew"))
    for column in FILL_IF_EMPTY:
        if merged.get(column) not in (None, "") and canonical.get(column) in (None, ""):
            if column == "referred_by" and merged.get(column) in (canonical.get("id"), merged.get("id")):
                continue
            changes[column] = merged[column]
    return changes


async def _plan(session: Any, merge_id: str, *, lock: bool) -> tuple[MergePlan, dict[str, str], list]:
    record, canonical, merged = await _load(session, merge_id, lock=lock)
    plan = MergePlan(str(record["merge_id"]), int(canonical["id"]), int(merged["id"]),
                     merged.get("telegram_user_id") if merged.get("telegram_user_id") is not None
                     else (record.get("evidence") or {}).get("telegram_user_id"))
    references = await _user_references(session)
    owners: dict[str, str] = {}
    for table, column in references:
        owners.setdefault(table, "user_id" if (table, "user_id") in references else column)
    parents = {table: await _owned_parents(session, table, owners) for table in owners}
    by_table: dict[str, list[str]] = {}
    for table, column in references:
        by_table.setdefault(table, []).append(column)
    steps = []
    for table in _order(owners, parents):
        for column in by_table[table]:
            key = f"{table}.{column}"
            count = int((await session.execute(text(
                f"SELECT COUNT(*) FROM {_ident(table)} WHERE {_ident(column)} = :merged"
            ), {"merged": plan.merged_user_id})).scalar_one())
            if not count:
                continue
            if table in NEVER_MOVED:
                plan.never_moved[key] = count
                continue
            steps.append((table, column, count, [c for c in by_table[table] if c != column],
                          parents[table] if column == owners[table] else []))
    plan.account_changes = _account_changes(canonical, merged)
    return plan, owners, steps


def _move_sql(table: str, column: str, others: list[str], parent_refs: list[tuple[str, str, str]],
              uniques: list[tuple[list[str], bool]], owners: dict[str, str]) -> str:
    t, c = _ident(table), _ident(column)
    predicates = [f"t.{c} = :merged"]
    if table in ROW_FILTERS:
        predicates.append(ROW_FILTERS[table])
    for other in others:  # never turn a relationship between the two accounts into a self-reference
        predicates.append(f"t.{_ident(other)} IS DISTINCT FROM :canonical")
    for child_col, parent, key in parent_refs:
        owner = owners[parent]
        predicates.append(
            f"(t.{_ident(child_col)} IS NULL OR EXISTS (SELECT 1 FROM {_ident(parent)} p "
            f"WHERE p.{_ident(key)} = t.{_ident(child_col)} AND p.{_ident(owner)} = :canonical))"
        )
    for columns, simple in uniques:
        if column not in columns or not simple:
            continue  # partial/expression indexes are enforced by PostgreSQL row by row
        matches = " AND ".join(
            f"o.{_ident(col)} = :canonical" if col == column else f"o.{_ident(col)} IS NOT DISTINCT FROM t.{_ident(col)}"
            for col in columns
        )
        predicates.append(f"NOT EXISTS (SELECT 1 FROM {t} o WHERE {matches})")
    return f"UPDATE {t} AS t SET {c} = :canonical WHERE " + " AND ".join(predicates)


async def _move_rows_individually(session: Any, sql: str, params: dict[str, Any]) -> int:
    """Re-run a move one row at a time so a single collision keeps only that row."""
    head, predicates = sql.split(" WHERE ", 1)
    table = head.split(" AS t SET ", 1)[0][len("UPDATE "):]
    rows = (await session.execute(text(f"SELECT t.ctid::text FROM {table} AS t WHERE {predicates}"), params)).all()
    moved = 0
    for (ctid,) in rows:
        nested = await session.begin_nested()
        try:
            # Compare as text: asyncpg would otherwise type the parameter as tid and reject a string.
            moved += (await session.execute(text(sql + " AND t.ctid::text = :row_ctid"),
                                            {**params, "row_ctid": ctid})).rowcount or 0
            await nested.commit()
        except Exception:
            await nested.rollback()
    return moved


async def plan_account_merge(session: Any, merge_id: str) -> dict[str, Any]:
    """Read-only preview: rows per table/column that reference the archived account."""
    plan, _, steps = await _plan(session, merge_id, lock=False)
    for table, column, count, _, _ in steps:
        plan.movable[f"{table}.{column}"] = count
    return plan.as_dict()


async def apply_account_merge(session: Any, merge_id: str, *, reviewer_user_id: int) -> dict[str, Any]:
    """Merge the archived account into the kept one inside the caller's transaction."""
    from services.platform.identity import record_security_event

    plan, owners, steps = await _plan(session, merge_id, lock=True)
    params = {"merged": plan.merged_user_id, "canonical": plan.canonical_user_id}

    # The Telegram identity is unique per account: release it before moving it.
    telegram_id = plan.telegram_user_id
    await session.execute(text("UPDATE users SET telegram_user_id = NULL, updated_at = NOW() WHERE id = :merged"), params)

    for table, column, count, others, parent_refs in steps:
        key = f"{table}.{column}"
        sql = _move_sql(table, column, others, parent_refs, await _unique_column_sets(session, table), owners)
        nested = await session.begin_nested()
        try:
            moved = (await session.execute(text(sql), params)).rowcount or 0
            await nested.commit()
        except Exception as exc:
            # A partial unique index refused at least one row: move the rest one by one.
            await nested.rollback()
            moved = await _move_rows_individually(session, sql, params)
            if moved == 0:
                plan.failed[key] = type(exc).__name__
        plan.movable[key] = int(moved)
        if count - int(moved) > 0:
            plan.kept[key] = count - int(moved)

    changes = dict(plan.account_changes)
    if telegram_id is not None:
        changes["telegram_user_id"] = int(telegram_id)
    if changes:
        assignments = ", ".join(f"{_ident(col)} = :{col}" for col in changes)
        await session.execute(text(f"UPDATE users SET {assignments}, updated_at = NOW() WHERE id = :canonical"),
                              {**changes, **params})
    if telegram_id is not None:
        await session.execute(text(
            "INSERT INTO auth_identities(identity_id,user_id,provider,provider_subject_id,verified,verified_at,metadata) "
            "VALUES(gen_random_uuid()::text,:canonical,'telegram',:subject,TRUE,NOW(),CAST(:metadata AS JSONB)) "
            "ON CONFLICT(provider,provider_subject_id) DO UPDATE SET user_id=EXCLUDED.user_id,verified=TRUE,"
            "verified_at=NOW(),disabled_at=NULL"
        ), {**params, "subject": str(int(telegram_id)),
            "metadata": json.dumps({"linked_via": "reviewed_merge", "merge_id": plan.merge_id}, separators=(",", ":"))})

    await session.execute(text(
        "UPDATE users SET account_status = 'merged', notification_suppressed = TRUE, updated_at = NOW() WHERE id = :merged"
    ), params)
    await session.execute(text(
        "UPDATE user_sessions SET revoked_at = NOW(), revoke_reason = 'account_merged' "
        "WHERE user_id = :merged AND revoked_at IS NULL"
    ), params)
    evidence = {**plan.as_dict(), "reviewer_user_id": int(reviewer_user_id)}
    await session.execute(text(
        "UPDATE account_merge_records SET status = 'completed', evidence = evidence || CAST(:evidence AS JSONB) "
        "WHERE merge_id = :merge_id"
    ), {"merge_id": plan.merge_id, "evidence": json.dumps({"completion": evidence}, default=str)})
    await session.execute(text(
        "UPDATE account_link_requests SET status = 'completed', completed_at = NOW() "
        "WHERE requesting_user_id = :canonical AND provider = 'telegram' AND status = 'merge_review'"
    ), params)
    for user_id, event in ((plan.canonical_user_id, "account.merge_completed"),
                           (plan.merged_user_id, "account.merged_into_other")):
        await record_security_event(session, user_id=user_id, event_type=event, severity="warning",
                                    metadata={"merge_id": plan.merge_id, "reviewer_user_id": int(reviewer_user_id)})
    return evidence


__all__ = ["MergeRefused", "apply_account_merge", "plan_account_merge"]
