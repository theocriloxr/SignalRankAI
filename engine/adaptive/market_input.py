"""Immutable captured component inputs; historical publication truth stays unknown.

This captures the normalized MarketContext actually supplied to components. It
does not certify the provider's historical revisions, universe or trading calendar.
No mutable candle-table reread can substitute for a missing captured input.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence
from types import MappingProxyType

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from .types import DataQualityReport, MarketContext
from engine.universe_observation import validate_universe_membership

FORMAT_VERSION = 1
MAX_INPUT_BYTES = 512 * 1024
MAX_CANDLES = 2000
MAX_AUDIT_INPUTS = 2048
MAX_AUDIT_BYTES = 64 * 1024 * 1024
_UNVERIFIED = {"publication_vintages": "UNVERIFIED", "historical_universe": "UNVERIFIED",
               "calendar_rules": "UNVERIFIED"}


def _json(value: Any) -> str:
    chunks: list[str] = []
    size = 0
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(value):
        size += len(chunk.encode("utf-8"))
        if size > MAX_INPUT_BYTES:
            raise ValueError("market_input_byte_budget_exceeded")
        chunks.append(chunk)
    return "".join(chunks)


def _materialize(value: Any, depth: int = 0, budget: list[int] | None = None) -> Any:
    budget = [100000] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0 or depth > 12:
        raise ValueError("market_input_structure_budget_exceeded")
    if isinstance(value, Mapping):
        if len(value) > 256:
            raise ValueError("market_input_mapping_budget_exceeded")
        return {key: _materialize(item, depth + 1, budget) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > 10000:
            raise ValueError("market_input_sequence_budget_exceeded")
        return [_materialize(item, depth + 1, budget) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _instant(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("market_input_timestamp_invalid") from None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("market_input_timestamp_must_be_aware")
    return value.astimezone(timezone.utc)


def _validate_tree(value: Any, depth: int = 0, budget: list[int] | None = None) -> None:
    budget = [100000] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0 or depth > 12:
        raise ValueError("market_input_structure_budget_exceeded")
    if isinstance(value, dict):
        if len(value) > 256:
            raise ValueError("market_input_mapping_budget_exceeded")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise ValueError("market_input_key_invalid")
            if re.search(r"secret|password|credential|api.?key|auth.?token|access.?token|private.?key", key, re.I):
                raise ValueError("market_input_sensitive_field_rejected")
            _validate_tree(item, depth + 1, budget)
    elif isinstance(value, (list, tuple)):
        if len(value) > 10000:
            raise ValueError("market_input_sequence_budget_exceeded")
        for item in value:
            _validate_tree(item, depth + 1, budget)
    elif isinstance(value, str):
        if len(value) > 4096 or len(value.encode("utf-8")) > 4096:
            raise ValueError("market_input_string_budget_exceeded")
    elif type(value) in {int, float}:
        if (type(value) is int and value.bit_length() > 128) or not math.isfinite(value):
            raise ValueError("market_input_nonfinite_value")
    elif value is not None and type(value) is not bool:
        raise ValueError("market_input_unsupported_value")


@dataclass(frozen=True, slots=True)
class MarketInputSnapshot:
    content_hash: str
    payload: str
    candle_count: int
    captured_at: datetime


def capture_market_input(
    context: MarketContext, *, timestamp_convention: str,
    captured_at: datetime | None = None,
    universe_observation: Mapping[str, Any] | None = None,
) -> MarketInputSnapshot:
    if len(context.candles) > MAX_CANDLES:
        raise ValueError("market_input_candle_budget_exceeded")
    inputs = {f.name: getattr(context, f.name) for f in fields(MarketContext)}
    inputs["data_quality"] = asdict(context.data_quality)
    value = {"format_version": FORMAT_VERSION, "context": _materialize(inputs),
             "captured_at": _instant(captured_at or datetime.now(timezone.utc)).isoformat(),
             "timestamp_convention": timestamp_convention, "source_history": dict(_UNVERIFIED)}
    if universe_observation is not None:
        observation = validate_universe_membership(universe_observation, asset=context.asset,
            decision_time=_instant(value["captured_at"]))
        value["universe_observation"] = observation.envelope()
    _validate_tree(value)
    encoded = _json(value)
    if len(encoded.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("market_input_byte_budget_exceeded")
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    # Decode before use so the captured representation and component input have
    # the same value semantics, without relying on mutable source dictionaries.
    restore_market_input(value, content_hash=digest)
    return MarketInputSnapshot(digest, encoded, len(context.candles), _instant(value["captured_at"]))


def restore_market_input(payload: Mapping[str, Any], *, content_hash: str) -> MarketContext:
    required = {
        "format_version", "context", "captured_at", "timestamp_convention", "source_history",
    }
    if not isinstance(payload, dict) or set(payload) not in (required, required | {"universe_observation"}):
        raise ValueError("market_input_payload_invalid")
    _validate_tree(payload)
    encoded = _json(payload)
    if len(encoded.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("market_input_byte_budget_exceeded")
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash) or hashlib.sha256(encoded.encode()).hexdigest() != content_hash:
        raise ValueError("market_input_content_hash_mismatch")
    if type(payload["format_version"]) is not int or payload["format_version"] != FORMAT_VERSION:
        raise ValueError("market_input_format_unsupported")
    if payload["source_history"] != _UNVERIFIED or payload["timestamp_convention"] not in {"bar_open", "unverified"}:
        raise ValueError("market_input_provenance_invalid")
    captured = _instant(payload["captured_at"])
    if captured.isoformat() != payload["captured_at"]:
        raise ValueError("market_input_timestamp_noncanonical")
    context = payload["context"]
    if not isinstance(context, dict) or set(context) != {f.name for f in fields(MarketContext)}:
        raise ValueError("market_input_context_invalid")
    for key in ("asset", "asset_class", "timeframe", "regime", "session", "provider"):
        if not isinstance(context[key], str) or not 1 <= len(context[key]) <= 128:
            raise ValueError("market_input_scope_invalid")
    if len(context["provider"]) > 64 or len(context["timeframe"]) > 8:
        raise ValueError("market_input_reference_scope_too_long")
    if context["higher_timeframe_bias"] not in {None, "LONG", "SHORT"}:
        raise ValueError("market_input_bias_invalid")
    candles = context["candles"]
    if not isinstance(candles, (list, tuple)) or len(candles) > MAX_CANDLES or any(not isinstance(c, dict) for c in candles):
        raise ValueError("market_input_candles_invalid")
    for key in ("indicators", "news_context", "macro_context"):
        if not isinstance(context[key], dict):
            raise ValueError("market_input_features_invalid")
    quality = context["data_quality"]
    if not isinstance(quality, dict) or set(quality) != {f.name for f in fields(DataQualityReport)}:
        raise ValueError("market_input_quality_invalid")
    if type(quality["usable"]) is not bool or type(quality["candle_count"]) is not int or quality["candle_count"] != len(candles):
        raise ValueError("market_input_quality_invalid")
    if (type(quality["stale"]) is not bool or type(quality["score"]) not in {int, float}
        or not 0 <= quality["score"] <= 1 or quality["provider"] != context["provider"]):
        raise ValueError("market_input_quality_invalid")
    if any(type(quality[key]) is not int or quality[key] < 0
           for key in ("duplicate_count", "gap_count", "impossible_count", "missing_count")):
        raise ValueError("market_input_quality_invalid")
    if not isinstance(quality["reasons"], (list, tuple)) or any(not isinstance(r, str) for r in quality["reasons"]):
        raise ValueError("market_input_quality_invalid")
    values = {key: _freeze(value) for key, value in context.items()}
    values.update({"candles": tuple(_freeze(c) for c in candles),
                   "data_quality": DataQualityReport(**{**quality, "reasons": tuple(quality["reasons"])})})
    result = MarketContext(**values)
    if "universe_observation" in payload:
        validate_universe_membership(payload["universe_observation"], asset=result.asset, decision_time=captured)
    return result


async def persist_market_inputs(session: AsyncSession, snapshots: Sequence[MarketInputSnapshot]) -> None:
    if len(snapshots) > 8:
        raise ValueError("market_input_capture_batch_budget_exceeded")
    distinct = {item.content_hash: item for item in snapshots}
    if any(distinct[item.content_hash] != item for item in snapshots):
        raise ValueError("conflicting_market_input_capture_batch")
    if not distinct:
        return
    records = []
    for item in distinct.values():
        payload = json.loads(item.payload)
        context = restore_market_input(payload, content_hash=item.content_hash)
        if item.candle_count != len(context.candles) or item.captured_at != _instant(payload["captured_at"]):
            raise ValueError("market_input_header_mismatch")
        records.append({"hash": item.content_hash, "format": FORMAT_VERSION, "asset": context.asset,
                        "timeframe": context.timeframe, "count": item.candle_count,
                        "captured": item.captured_at, "payload": item.payload})
    # Sorted ownership order avoids deadlocks when two signals share a capture.
    records.sort(key=lambda r: r["hash"])
    await session.execute(text("""
        INSERT INTO research_market_inputs(content_hash,format_version,asset,timeframe,candle_count,captured_at,payload)
        VALUES(:hash,:format,:asset,:timeframe,:count,:captured,CAST(:payload AS JSONB))
        ON CONFLICT(content_hash) DO NOTHING
    """), records)
    loaded = await _load_inputs(session, sorted(distinct))
    if set(loaded) != set(distinct) or any(loaded[key].payload != distinct[key].payload for key in loaded):
        raise ValueError("conflicting_immutable_market_input")


async def _load_inputs(session: AsyncSession, hashes: Sequence[str]) -> dict[str, MarketInputSnapshot]:
    statement = text("""SELECT content_hash,format_version,asset,timeframe,candle_count,captured_at,payload
        FROM research_market_inputs WHERE content_hash IN :hashes""").bindparams(bindparam("hashes", expanding=True))
    result: dict[str, MarketInputSnapshot] = {}
    for offset in range(0, len(hashes), 16):
        records = (await session.execute(statement, {"hashes": list(hashes[offset:offset + 16])})).mappings()
        for row in records:
            context = restore_market_input(row["payload"], content_hash=row["content_hash"])
            captured = _instant(row["payload"]["captured_at"])
            if (row["format_version"] != FORMAT_VERSION or row["asset"] != context.asset
                or row["timeframe"] != context.timeframe or row["candle_count"] != len(context.candles)
                or row["captured_at"] != captured):
                raise ValueError("market_input_stored_identity_mismatch")
            result[row["content_hash"]] = MarketInputSnapshot(row["content_hash"], _json(row["payload"]), len(context.candles), captured)
    return result


async def load_market_input(session: AsyncSession, content_hash: str) -> MarketContext:
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise ValueError("market_input_hash_invalid")
    loaded = await _load_inputs(session, [content_hash])
    if content_hash not in loaded:
        raise ValueError("market_input_unavailable")
    return restore_market_input(json.loads(loaded[content_hash].payload), content_hash=content_hash)


async def audit_captured_inputs(session: AsyncSession, rows: Sequence[Any]) -> dict[str, Any]:
    references: dict[str, list[tuple[Any, dict[str, Any]]]] = {}
    hashes: set[str] = set()
    missing = 0
    for row in rows:
        if not row.sequence_provenance:
            missing += 1
        for raw in row.sequence_provenance:
            ref = json.loads(raw)
            digest = ref.get("market_input_hash")
            if digest is None:
                missing += 1
                continue
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("market_input_hash_invalid")
            hashes.add(digest)
            if len(hashes) > MAX_AUDIT_INPUTS:
                raise ValueError("market_input_audit_count_budget_exceeded")
            references.setdefault(digest, []).append((row, ref))
    if len(hashes) > MAX_AUDIT_INPUTS:
        raise ValueError("market_input_audit_count_budget_exceeded")
    verified = 0
    universe_verified = 0
    total_bytes = 0
    # Decode bounded chunks, rather than materializing a year's input history.
    ordered = sorted(hashes)
    for offset in range(0, len(ordered), 16):
        loaded = await _load_inputs(session, ordered[offset:offset + 16])
        missing += len(set(ordered[offset:offset + 16]) - set(loaded))
        for digest, item in loaded.items():
            total_bytes += len(item.payload.encode())
            if total_bytes > MAX_AUDIT_BYTES:
                raise ValueError("market_input_audit_byte_budget_exceeded")
            payload = json.loads(item.payload)
            context = restore_market_input(payload, content_hash=digest)
            for row, ref in references[digest]:
                if (context.asset != row.asset or context.asset != ref["asset"] or context.timeframe != ref["timeframe"]
                    or context.provider != ref["provider"] or item.captured_at > _instant(row.decision_time)
                    or payload["captured_at"] != ref.get("captured_at")
                    or payload["timestamp_convention"] != ref.get("timestamp_convention")):
                    raise ValueError("market_input_reference_scope_or_time_mismatch")
                observation = payload.get("universe_observation")
                if ref.get("universe_observation_hash") != (observation or {}).get("content_hash"):
                    raise ValueError("market_input_universe_reference_mismatch")
                if observation is not None:
                    validate_universe_membership(observation, asset=row.asset, decision_time=_instant(row.decision_time))
                    universe_verified += 1
                count = ref["candle_count"]
                if type(count) is not int or not 1 <= count <= len(context.candles):
                    raise ValueError("market_input_reference_count_mismatch")
                suffix = [{key: c.get(key) for key in ("open_time_ms", "open", "high", "low", "close", "volume")}
                          for c in context.candles[-count:]]
                if hashlib.sha256(_json(suffix).encode()).hexdigest() != ref["sequence_hash"]:
                    raise ValueError("market_input_sequence_hash_mismatch")
                verified += 1
    expected = sum(len(items) for items in references.values())
    return {"status": "PASS" if rows and references and not missing and verified == expected else "UNVERIFIED",
            "scope": "captured_normalized_component_inputs_only", "verified_references": verified,
            "missing_references": missing, "unique_inputs": len(hashes), "materialized_bytes": total_bytes,
            "observed_universe": {"status": "PASS" if rows and references and not missing and universe_verified == expected else "UNVERIFIED",
                "verified_references": universe_verified, "scope": "observed_engine_selection_only",
                "historical_membership": "UNVERIFIED"},
            "source_history": dict(_UNVERIFIED), "complete_point_in_time_replay": False}
