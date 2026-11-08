"""Re-label shadow outcomes that a stale ``market_ticks`` price may have decided.

Background (production, 4 Nov 2026; fixed for new rows in ``bec9a5f``):
``engine.stale_signal_validator._get_live_price_async`` tried Binance, then
``market_ticks``, then yfinance. Nothing had written ``market_ticks`` since
July, so for every symbol Binance does not list (forex, metals, oil, indices,
stocks) the shadow tracker compared setups with July prices. EURGBP 15m longs
were labelled ``tp1`` five minutes after rejection while the 5m candles never
left the range; forex longs read 85 % TP1-or-better and shorts 20 %. Those
labels feed the setup-evidence filter (60 days), the strategy scorecard, the
expectancy shadow and retraining.

Rows labelled before this fix do not record whether candles or a live price
decided them, so this script re-applies the tracker's candle rule
(``engine.shadow_outcome_worker.label_from_candles``) to stored
``market_candles``:

- candles reach a terminal label: that label is kept (``unchanged``) or written
  (``relabelled``);
- candles do not cover the setup, or never reach a stop or target:
  ``unverifiable`` (excluded by every consumer, which read only tp*/sl).

Every change is audited on the row: ``meta.label_correction`` keeps the
previous label (and ``shadow_r``), the reason, the script name and the time.
Linked ``ml_shadow_predictions`` rows (``meta.rejection_id``) get the same label.
Rows that already carry ``outcome_label_source`` (written after this change)
or a ``label_correction`` are skipped, so the script is safe to re-run.

Default is a dry run that only counts. ``--apply`` writes, in short
transactions of ``--batch`` rows. Run it against production only with the
owner's approval, after a backup; AGENTS.md forbids test suites, not audited
corrections, against production.

    python scripts/correct_stale_tick_shadow_labels.py --until 2026-11-04T07:00:00
    python scripts/correct_stale_tick_shadow_labels.py --until 2026-11-04T07:00:00 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORRECTED_BY = "scripts/correct_stale_tick_shadow_labels.py"
REASON = "stale_market_ticks_live_price"
LABELS = ("sl", "tp", "tp1", "tp2", "tp3")
# Binance lists these quote assets; their live price came from Binance REST,
# not from market_ticks.
CRYPTO_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")
HORIZON = timedelta(days=14)
MAX_CANDLES_PER_SERIES = 20_000


def is_binance_symbol(asset: Any) -> bool:
    return str(asset or "").upper().endswith(CRYPTO_QUOTES)


def _naive_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def _meta(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def candidate_row(record: dict[str, Any], *, since: datetime, until: datetime, all_assets: bool) -> bool:
    """Whether a decision_log row is in scope for the correction."""
    meta = record["meta"]
    if str(record.get("decision") or "") != "rejected":
        return False
    if meta.get("outcome_label_source") or meta.get("label_correction"):
        return False
    if str(meta.get("actual_outcome") or "").lower() not in LABELS:
        return False
    tracked = _naive_utc(meta.get("outcome_tracked_at"))
    if tracked is None or not (since <= tracked < until):
        return False
    return all_assets or not is_binance_symbol(record.get("asset"))


def relabel(record: dict[str, Any], candles: list[dict[str, Any]]) -> str:
    """The tracker's candle label for one row, or ``unverifiable``."""
    from engine.shadow_outcome_worker import UNVERIFIABLE_OUTCOME, label_from_candles

    meta = record["meta"]
    row = {
        "created_at": record["created_at"],
        "timeframe": record.get("timeframe"),
        "direction": meta.get("direction"),
        "entry": meta.get("entry"),
        "stop_loss": meta.get("stop_loss"),
        "take_profit": meta.get("take_profit"),
    }
    try:
        label = label_from_candles(row, candles) if candles else None
    except (TypeError, ValueError):
        label = None
    if label is None:
        return UNVERIFIABLE_OUTCOME
    return str(label)


def corrected_meta(record: dict[str, Any], new_label: str, layer: str, now: datetime) -> dict[str, Any]:
    meta = dict(record["meta"])
    previous = {"actual_outcome": meta.get("actual_outcome")}
    if "shadow_r" in meta:
        previous["shadow_r"] = meta.get("shadow_r")
    meta["actual_outcome"] = new_label[:32]
    if layer != "ml":
        from engine.expectancy_shadow import realized_r

        # Same call as the tracker's expectancy branch.
        meta["shadow_r"] = realized_r(meta.get("direction"), meta.get("entry"), meta.get("stop_loss"),
                                      meta.get("take_profit"), new_label)
    meta["label_correction"] = {
        "previous": previous,
        "reason": REASON,
        "corrected_by": CORRECTED_BY,
        "corrected_at": now.isoformat(),
    }
    meta["outcome_label_source"] = "candles_correction"
    return meta


def _candle_dict(row: Any) -> dict[str, Any]:
    return {"timestamp": int(row[0]), "high": float(row[1]), "low": float(row[2])}


async def _first_id_after(conn: Any, cutoff: datetime) -> int:
    from sqlalchemy import text

    max_id = int((await conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM decision_log"))).scalar() or 0)
    low, high = 0, max_id
    while low < high:
        mid = (low + high) // 2
        row = (await conn.execute(
            text("SELECT id, created_at FROM decision_log WHERE id >= :mid ORDER BY id LIMIT 1"), {"mid": mid}
        )).first()
        if row is None or _naive_utc(row[1]) >= cutoff:
            high = mid
        else:
            low = int(row[0]) + 1
    return low


async def _load_candles(conn: Any, asset: str, timeframe: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    from sqlalchemy import text

    start_ms = int(start.replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(end.replace(tzinfo=timezone.utc).timestamp() * 1000)
    rows = (await conn.execute(
        text("SELECT open_time_ms, high, low FROM market_candles WHERE symbol = :s AND timeframe = :tf "
             "AND open_time_ms >= :a AND open_time_ms <= :b ORDER BY open_time_ms LIMIT :n"),
        {"s": str(asset).upper()[:32], "tf": str(timeframe).lower()[:8], "a": start_ms, "b": end_ms,
         "n": MAX_CANDLES_PER_SERIES},
    )).all()
    return [_candle_dict(r) for r in rows]


async def run(dsn: str, *, since: datetime, until: datetime, apply: bool, batch: int, id_window: int,
              all_assets: bool, out=print, pause_seconds: float = 0.0) -> Counter:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url
    from engine.shadow_outcome_worker import _timeframe_seconds

    engine = create_async_engine(_normalize_database_url(dsn, async_driver=True))
    counts: Counter = Counter()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        async with engine.connect() as conn:
            # A label tracked at or after `since` belongs to a row created at most
            # the tracker's lag earlier; 30 days covers every backlog seen.
            start_id = await _first_id_after(conn, since - timedelta(days=30))
            end_id = int((await conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM decision_log"))).scalar() or 0)
        out(f"[correct_shadow] scan ids {start_id}..{end_id} since={since.isoformat()} until={until.isoformat()} "
            f"apply={apply}")
        cursor = start_id
        while cursor <= end_id:
            upper = cursor + id_window
            async with engine.connect() as conn:
                rows = (await conn.execute(
                    text("SELECT id, decision, asset, timeframe, created_at, meta FROM decision_log "
                         "WHERE id >= :a AND id < :b AND decision = 'rejected' "
                         "AND meta::jsonb ? 'outcome_tracked_at' AND NOT (meta::jsonb ? 'outcome_label_source') "
                         "ORDER BY id"),
                    {"a": cursor, "b": upper},
                )).mappings().all()
            cursor = upper
            if pause_seconds > 0:
                await asyncio.sleep(pause_seconds)  # gentle on a shared production database
            records = []
            for r in rows:
                record = dict(r)
                record["meta"] = _meta(record["meta"])
                record["created_at"] = _naive_utc(record["created_at"])
                if record["created_at"] and candidate_row(record, since=since, until=until, all_assets=all_assets):
                    records.append(record)
            for offset in range(0, len(records), batch):
                chunk = records[offset: offset + batch]
                series: dict[tuple[str, str], list[dict[str, Any]]] = {}
                async with engine.connect() as conn:
                    for key in {(str(r["asset"]), str(r.get("timeframe") or "1h")) for r in chunk}:
                        times = [r["created_at"] for r in chunk if (str(r["asset"]), str(r.get("timeframe") or "1h")) == key]
                        bar = timedelta(seconds=_timeframe_seconds(key[1]))
                        series[key] = await _load_candles(conn, key[0], key[1], min(times) - bar, max(times) + HORIZON)
                updates = []
                for record in chunk:
                    key = (str(record["asset"]), str(record.get("timeframe") or "1h"))
                    created = record["created_at"]
                    candles = [c for c in series.get(key, [])
                               if created - timedelta(seconds=_timeframe_seconds(key[1])) <= datetime.fromtimestamp(
                                   c["timestamp"] / 1000, tz=timezone.utc).replace(tzinfo=None) <= created + HORIZON]
                    new_label = relabel(record, candles)
                    old_label = str(record["meta"].get("actual_outcome") or "").lower()
                    layer = str(record["meta"].get("layer") or "ml")
                    counts["scanned"] += 1
                    if new_label == old_label:
                        counts["unchanged"] += 1
                        continue
                    counts["unverifiable" if new_label == "unverifiable" else "relabelled"] += 1
                    counts[f"{old_label}->{new_label}"] += 1
                    updates.append((record, corrected_meta(record, new_label, layer, now), new_label))
                if apply and updates:
                    async with engine.begin() as conn:
                        for record, meta, new_label in updates:
                            await conn.execute(
                                text("UPDATE decision_log SET meta = CAST(:m AS json) WHERE id = :id "
                                     "AND NOT (meta::jsonb ? 'label_correction')"),
                                {"m": json.dumps(meta, default=str), "id": int(record["id"])},
                            )
                            result = await conn.execute(
                                text("UPDATE ml_shadow_predictions SET meta = CAST("
                                     "jsonb_set(jsonb_set(meta::jsonb, '{actual_outcome}', to_jsonb(CAST(:o AS text))), "
                                     "'{label_correction}', CAST(:c AS jsonb)) AS json) "
                                     "WHERE meta::jsonb->>'rejection_id' = :rid"),
                                {"o": new_label, "c": json.dumps(meta["label_correction"]), "rid": str(record["id"])},
                            )
                            counts["ml_shadow_predictions_updated"] += int(result.rowcount or 0)
                    counts["written"] += len(updates)
        out("[correct_shadow] " + json.dumps(dict(sorted(counts.items())), sort_keys=True))
        return counts
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--since", help="earliest outcome_tracked_at (default: 60 days before --until)")
    parser.add_argument("--until", required=True,
                        help="first time production ran bec9a5f (stale ticks refused), UTC ISO timestamp")
    parser.add_argument("--apply", action="store_true", help="write the corrections (default: dry run)")
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--id-window", type=int, default=50_000)
    parser.add_argument("--all-assets", action="store_true",
                        help="include Binance symbols (their live price came from Binance, not market_ticks)")
    args = parser.parse_args(argv)
    dsn = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PRIVATE_URL") or ""
    if not dsn:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    until = _naive_utc(args.until)
    since = _naive_utc(args.since) if args.since else (until - timedelta(days=60) if until else None)
    if until is None or since is None or since >= until:
        print("--since must be before --until (ISO timestamps)", file=sys.stderr)
        return 2
    asyncio.run(run(dsn, since=since, until=until, apply=args.apply, batch=max(1, args.batch),
                    id_window=max(1000, args.id_window), all_assets=args.all_assets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
