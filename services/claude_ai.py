"""Claude (Anthropic) as an AI signal reviewer (owner request, 8 Nov 2026).

OpenAI is unavailable, so Claude joins the provider chain
(``AI_PROVIDER_ORDER``, default ``openai,claude,gemini,local``). It receives the
same instructions and the same secret-free evidence as the other reviewers
(``services.openai_ai.SIGNAL_REVIEW_SYSTEM`` / ``_signal_context``) and returns
the same JSON shape, so the router, consensus and the engine treat it like
any other provider. It is advisory only: deterministic freshness, risk,
exposure and execution gates are applied by the engine regardless.

Configuration (all optional except the key):
  ANTHROPIC_API_KEY             enables the provider
  CLAUDE_AI_ENABLED             default true
  CLAUDE_REVIEW_MODEL           default claude-opus-5-5
  CLAUDE_REVIEW_EFFORT          default low (low|medium|high|xhigh|max)
  CLAUDE_REVIEW_MAX_CALLS_PER_HOUR  default 120 (0 disables the provider)
  CLAUDE_REVIEW_TIMEOUT_SECONDS default 30
  CLAUDE_REVIEW_FALLBACKS       default true: server-side refusal fallback
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

PROVIDER = "claude"
DEFAULT_MODEL = "claude-opus-5-5"
_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_LOCK = threading.Lock()
_WINDOW_STARTED = 0.0
_WINDOW_CALLS = 0
_CIRCUIT_UNTIL = 0.0
_CIRCUIT_REASON = ""
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_client = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 0, maximum: int = 100000) -> int:
    try:
        value = int(float(os.getenv(name, str(default)) or default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _api_key() -> str:
    return str(os.getenv("ANTHROPIC_API_KEY") or "").strip()


def claude_available() -> bool:
    return bool(_api_key() and _env_bool("CLAUDE_AI_ENABLED", True)
                and _env_int("CLAUDE_REVIEW_MAX_CALLS_PER_HOUR", 120) > 0)


def model() -> str:
    return str(os.getenv("CLAUDE_REVIEW_MODEL") or DEFAULT_MODEL).strip()


def _effort() -> str:
    value = str(os.getenv("CLAUDE_REVIEW_EFFORT") or "low").strip().lower()
    return value if value in _EFFORTS else "low"


def _schema_for_claude(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Drop numeric bounds; the router clamps scores and confidences itself."""
    def walk(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {k: walk(v) for k, v in node.items() if k not in {"minimum", "maximum"}}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(schema)


def _admit() -> tuple[bool, str]:
    global _WINDOW_STARTED, _WINDOW_CALLS
    now = time.monotonic()
    with _LOCK:
        if _CIRCUIT_UNTIL and now < _CIRCUIT_UNTIL:
            return False, f"circuit_open_{_CIRCUIT_REASON or 'provider'}"
        if not _WINDOW_STARTED or now - _WINDOW_STARTED > 3600:
            _WINDOW_STARTED, _WINDOW_CALLS = now, 0
        if _WINDOW_CALLS >= _env_int("CLAUDE_REVIEW_MAX_CALLS_PER_HOUR", 120):
            return False, "budget_hourly_calls"
        _WINDOW_CALLS += 1
    return True, ""


def _open_circuit(reason: str, seconds: int) -> None:
    global _CIRCUIT_UNTIL, _CIRCUIT_REASON
    with _LOCK:
        _CIRCUIT_UNTIL = time.monotonic() + max(1, seconds)
        _CIRCUIT_REASON = reason[:60]


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.AsyncAnthropic(
            api_key=_api_key(),
            timeout=float(_env_int("CLAUDE_REVIEW_TIMEOUT_SECONDS", 30, minimum=5, maximum=600)),
            max_retries=1,
        )
    return _client


def _usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    out: dict[str, Any] = {}
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, (int, float)):
            out[key] = value
    return out


async def structured_call(*, task: str, system: str, payload: Mapping[str, Any],
                          schema: Mapping[str, Any], max_tokens: int = 4000,
                          cache_seconds: int = 600) -> dict[str, Any]:
    """One structured Claude request. Never raises; failures come back as ``ok: False``."""
    name = model()
    if not claude_available():
        return {"ok": False, "provider": PROVIDER, "model": name, "error": "not_available"}
    body = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))[:24000]
    cache_key = f"{task}:{name}:{hash(body)}"
    hit = _CACHE.get(cache_key)
    if hit and time.monotonic() - hit[0] < cache_seconds:
        return {**hit[1], "cache_hit": True}
    admitted, reason = _admit()
    if not admitted:
        return {"ok": False, "provider": PROVIDER, "model": name, "error": reason}

    import anthropic

    from services import ai_cost_ledger

    # Reserve worst-case spend first; an exhausted budget skips this advisory step.
    admission = await ai_cost_ledger.admit(
        provider=PROVIDER, model=name, task=task,
        estimated_prompt_tokens=ai_cost_ledger.estimate_tokens(system + body),
        max_output_tokens=max_tokens,
    )
    if not admission.admitted:
        return admission.refusal()
    started = time.perf_counter()

    async def settle(outcome: str, *, usage: Mapping[str, Any] | None = None, billable: bool = True,
                     error: str | None = None) -> None:
        prompt_tokens, completion_tokens = ai_cost_ledger.claude_usage_tokens(usage)
        await ai_cost_ledger.settle(admission, outcome=outcome, prompt_tokens=prompt_tokens,
                                    completion_tokens=completion_tokens,
                                    latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
                                    error=error, billable=billable)

    params: dict[str, Any] = {
        "model": name,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": body}],
        "output_config": {"effort": _effort(),
                          "format": {"type": "json_schema", "schema": _schema_for_claude(schema)}},
    }
    try:
        client = _get_client()
        if _env_bool("CLAUDE_REVIEW_FALLBACKS", True):
            response = await client.beta.messages.create(betas=[_FALLBACK_BETA], fallbacks="default", **params)
        else:
            response = await client.messages.create(**params)
    except anthropic.AuthenticationError:
        _open_circuit("auth", 1800)
        await settle("error", billable=False, error="auth")
        return {"ok": False, "provider": PROVIDER, "model": name, "error": "auth"}
    except anthropic.PermissionDeniedError:
        _open_circuit("permission", 1800)
        await settle("error", billable=False, error="permission")
        return {"ok": False, "provider": PROVIDER, "model": name, "error": "permission"}
    except anthropic.RateLimitError:
        _open_circuit("rate_limit", 120)
        await settle("error", billable=False, error="rate_limit")
        return {"ok": False, "provider": PROVIDER, "model": name, "error": "rate_limit"}
    except anthropic.BadRequestError as exc:
        logger.warning("[claude_ai] task=%s bad request status=%s", task, getattr(exc, "status_code", "?"))
        _open_circuit("bad_request", 600)
        await settle("error", billable=False, error="bad_request")
        return {"ok": False, "provider": PROVIDER, "model": name, "error": "bad_request"}
    except anthropic.APITimeoutError:
        await settle("timeout", error="timeout")  # may still be billed
        return {"ok": False, "provider": PROVIDER, "model": name, "error": "timeout"}
    except anthropic.APIStatusError as exc:
        status = int(getattr(exc, "status_code", 0) or 0)
        if status >= 500:
            _open_circuit("server", 60)
        await settle("error", billable=False, error=f"provider_http_{status}")
        return {"ok": False, "provider": PROVIDER, "model": name, "error": f"provider_http_{status}"}
    except anthropic.APIConnectionError:
        await settle("error", error="connection")
        return {"ok": False, "provider": PROVIDER, "model": name, "error": "connection"}
    except Exception as exc:  # never break the signal pipeline
        logger.warning("[claude_ai] task=%s failed error=%s", task, type(exc).__name__)
        await settle("error", error=type(exc).__name__)
        return {"ok": False, "provider": PROVIDER, "model": name, "error": type(exc).__name__}

    served = str(getattr(response, "model", "") or name)
    usage = _usage(response)
    await settle("ok" if getattr(response, "stop_reason", None) not in {"refusal", "max_tokens"} else "error",
                 usage=usage, error=None)
    if getattr(response, "stop_reason", None) == "refusal":
        return {"ok": False, "provider": PROVIDER, "model": served, "error": "refusal"}
    if getattr(response, "stop_reason", None) == "max_tokens":
        return {"ok": False, "provider": PROVIDER, "model": served, "error": "max_tokens"}
    text = next((getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text"), "")
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {"ok": False, "provider": PROVIDER, "model": served, "error": "invalid_json"}
    if not isinstance(data, dict):
        return {"ok": False, "provider": PROVIDER, "model": served, "error": "invalid_json"}
    result = {
        "ok": True,
        "provider": PROVIDER,
        "model": served,
        "task": task,
        "data": data,
        "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "response_id": str(getattr(response, "id", "") or "")[:128],
        "usage": usage,
        "cache_hit": False,
    }
    _CACHE[cache_key] = (time.monotonic(), result)
    if len(_CACHE) > 512:
        for key in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:128]:
            _CACHE.pop(key, None)
    return result


async def review_signal(signal: Mapping[str, Any], candles: Sequence[Mapping[str, Any]] | None = None,
                        news_sentiment: float | None = None) -> dict[str, Any]:
    from services.openai_ai import _SIGNAL_REVIEW_SCHEMA, SIGNAL_REVIEW_SYSTEM, _signal_context

    return await structured_call(task="signalrank_trade_review", system=SIGNAL_REVIEW_SYSTEM,
                                 payload=_signal_context(signal, candles, news_sentiment),
                                 schema=_SIGNAL_REVIEW_SCHEMA)


async def choose_direction(asset: str, timeframe: str, long_candidates: Sequence[Mapping[str, Any]],
                           short_candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    from services.openai_ai import DIRECTION_SYSTEM, direction_payload

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "winner": {"type": "string", "enum": ["long", "short", "none"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["winner", "confidence", "reason"],
    }
    return await structured_call(task="signalrank_direction_arbitration", system=DIRECTION_SYSTEM,
                                 payload=direction_payload(asset, timeframe, long_candidates, short_candidates),
                                 schema=schema)


def provider_status() -> dict[str, Any]:
    """Secret-free configuration and circuit state for the owner pulse."""
    now = time.monotonic()
    with _LOCK:
        circuit = max(0.0, _CIRCUIT_UNTIL - now)
        calls = _WINDOW_CALLS
    return {
        "provider": PROVIDER,
        "configured": bool(_api_key()),
        "available": claude_available(),
        "model": model(),
        "effort": _effort(),
        "calls_this_hour": calls,
        "max_calls_per_hour": _env_int("CLAUDE_REVIEW_MAX_CALLS_PER_HOUR", 120),
        "circuit_open_seconds": round(circuit, 1),
        "circuit_reason": _CIRCUIT_REASON if circuit else "",
    }
