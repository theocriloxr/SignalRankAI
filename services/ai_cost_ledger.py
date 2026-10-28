"""Append-only AI usage/cost ledger with fail-closed spend budgets.

Every OpenAI and Gemini call goes through :func:`admit` before the provider is
contacted and :func:`settle` afterwards:

- ``admit`` reserves the call's worst-case cost (estimated prompt tokens plus
  the full output-token cap). When a budget applies it does so under one
  PostgreSQL advisory lock, so concurrent calls cannot jointly overrun it.
  A refused call is written as ``skipped`` and the caller must skip the AI step.
- ``settle`` records the estimated actual cost. Definite provider rejections
  cost nothing; ambiguous failures (timeouts, transport errors) keep the
  reserved estimate, because the provider may still bill them.

Spend for a period is every settlement plus every reservation that never
settled. Budgets come from the environment (see :func:`parse_budget_limits`);
an unparseable limit becomes zero and when any budget applies but spend cannot
be read the call is refused. Without budgets the ledger records but never blocks.

Prices are not guessed: ``AI_MODEL_PRICING_JSON`` holds contract prices per
million tokens. A model without a configured price is costed at a deliberately
high fallback so budgets over-count rather than under-count.

The AI steps this guards are advisory. Skipping one never approves anything:
callers fall back to their existing degraded path (deterministic review).
"""

from __future__ import annotations

import contextvars
import json
import logging
import math
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Sequence
from uuid import uuid4

logger = logging.getLogger("AICostLedger")

PERIODS = ("daily", "monthly")
PROVIDERS = ("openai", "gemini")
DEFAULT_ALERT_THRESHOLDS = (0.5, 0.8, 1.0)
# Unpriced models are costed high on purpose: over-counting trips a budget
# early, under-counting would let real spend pass it.
DEFAULT_UNPRICED_INPUT_PER_1M = 15.0
DEFAULT_UNPRICED_OUTPUT_PER_1M = 75.0
# pg_advisory_xact_lock key shared by every budgeted admission.
_BUDGET_LOCK_KEY = 0x5A1C0571

_TASK_WORKLOADS = {
    "signalrank_trade_review": "signal_review",
    "signalrank_direction_arbitration": "signal_review",
    "signalrank_risk_review": "signal_review",
    "signalrank_news_sentiment": "market_context",
    "signalrank_market_regime": "market_context",
    "signalrank_signal_explanation": "explanation",
    "signalrank_operator_question": "chat",
    "signalrank_performance_review": "research",
    "signalrank_evolution_proposal": "research",
    "signalrank_threshold_recommendation": "research",
    "signalrank_provider_connectivity": "diagnostics",
}
_WORKLOAD_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_LIMIT_RE = re.compile(r"^AI_BUDGET_(?:(WORKLOAD)_([A-Z0-9_]+)_|(OPENAI|GEMINI)_|(PER_USER)_)?(DAILY|MONTHLY)_USD$")

_ATTRIBUTION: contextvars.ContextVar["Attribution | None"] = contextvars.ContextVar(
    "signalrank_ai_usage_attribution", default=None
)
_LAST_UNAVAILABLE_LOG = 0.0


class AIBudgetExhausted(RuntimeError):
    """Raised by call wrappers whose callers only understand exceptions."""

    def __init__(self, reason: str, scope: str | None = None) -> None:
        super().__init__(f"{reason}:{scope}" if scope else reason)
        self.reason = reason
        self.scope = scope


@dataclass(frozen=True, slots=True)
class Attribution:
    user_id: int | None = None
    telegram_user_id: int | None = None
    workload: str | None = None


@dataclass(frozen=True, slots=True)
class BudgetLimit:
    kind: str  # global | provider | workload | per_user
    value: str | None
    period: str
    limit_usd: float
    valid: bool = True
    source: str = ""

    def scope(self, user_id: int | None = None) -> str:
        if self.kind == "global":
            return "global"
        if self.kind == "per_user":
            return f"user:{user_id}"
        return f"{self.kind}:{self.value}"


@dataclass(frozen=True, slots=True)
class BudgetAlert:
    scope: str
    period: str
    threshold: float
    spend_usd: float
    limit_usd: float
    exhausted: bool = False


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    admitted: bool
    exhausted_scope: str | None = None
    exhausted_period: str | None = None
    alerts: tuple[BudgetAlert, ...] = ()


@dataclass(frozen=True, slots=True)
class Admission:
    admitted: bool
    call_id: str
    provider: str
    model: str
    workload: str
    task: str
    reason: str = ""
    scope: str | None = None
    recorded: bool = False
    user_id: int | None = None
    telegram_user_id: int | None = None
    reserved_prompt_tokens: int = 0
    reserved_completion_tokens: int = 0
    reserved_usd: float = 0.0
    pricing_source: str = ""
    alerts: tuple[BudgetAlert, ...] = field(default_factory=tuple)

    def refusal(self) -> dict[str, Any]:
        """Provider-result shape for a call that was not made."""
        return {
            "ok": False,
            "provider": self.provider,
            "model": self.model,
            "error": self.reason or "budget_exhausted",
            "budget_scope": self.scope,
            "skipped": True,
        }


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def ledger_enabled() -> bool:
    return _env_bool("AI_COST_LEDGER_ENABLED", True)


def normalize_workload(value: str | None) -> str:
    cleaned = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")[:48]
    return cleaned if _WORKLOAD_RE.match(cleaned or "") else "unclassified"


def workload_for_task(task: str) -> str:
    return _TASK_WORKLOADS.get(str(task or ""), "unclassified")


@contextmanager
def ai_usage_attribution(
    *,
    user_id: int | None = None,
    telegram_user_id: int | None = None,
    workload: str | None = None,
) -> Iterator[Attribution]:
    """Attribute AI calls made inside this block to a user and/or workload."""
    attribution = Attribution(
        user_id=int(user_id) if user_id is not None else None,
        telegram_user_id=int(telegram_user_id) if telegram_user_id is not None else None,
        workload=normalize_workload(workload) if workload else None,
    )
    token = _ATTRIBUTION.set(attribution)
    try:
        yield attribution
    finally:
        _ATTRIBUTION.reset(token)


def current_attribution() -> Attribution:
    return _ATTRIBUTION.get() or Attribution()


def estimate_tokens(text: str | None) -> int:
    """Rough prompt size (about three characters per token, rounded up)."""
    return int(math.ceil(len(str(text or "")) / 3.0))


def _pricing_table(env: Mapping[str, str]) -> dict[str, tuple[float, float]]:
    raw = str(env.get("AI_MODEL_PRICING_JSON") or "").strip()
    if not raw:
        return {}
    try:
        document = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("[ai_cost] AI_MODEL_PRICING_JSON is not valid JSON; every model uses the fallback price")
        return {}
    table: dict[str, tuple[float, float]] = {}
    if not isinstance(document, Mapping):
        return table
    for key, prices in document.items():
        if not isinstance(prices, Mapping):
            continue
        try:
            input_price = float(prices.get("input_per_1m"))
            output_price = float(prices.get("output_per_1m"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(input_price) and math.isfinite(output_price) and input_price >= 0 and output_price >= 0:
            table[str(key).strip().lower()] = (input_price, output_price)
    return table


def _fallback_price(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        value = float(env.get(name) or default)
    except (TypeError, ValueError):
        return default
    # A fallback below the default would make unknown models look cheap.
    return value if math.isfinite(value) and value >= default else default


def price_for(provider: str, model: str, env: Mapping[str, str] | None = None) -> tuple[float, float, str]:
    """Return (input USD per 1M tokens, output USD per 1M tokens, pricing source)."""
    env = os.environ if env is None else env
    table = _pricing_table(env)
    provider = str(provider or "").strip().lower()
    model = str(model or "").strip().lower()
    for key in (f"{provider}:{model}", f"{provider}:*"):
        if key in table:
            return table[key][0], table[key][1], "configured"
    return (
        _fallback_price(env, "AI_UNPRICED_INPUT_PER_1M", DEFAULT_UNPRICED_INPUT_PER_1M),
        _fallback_price(env, "AI_UNPRICED_OUTPUT_PER_1M", DEFAULT_UNPRICED_OUTPUT_PER_1M),
        "unpriced_conservative",
    )


def estimate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    env: Mapping[str, str] | None = None,
) -> tuple[float, str]:
    input_price, output_price, source = price_for(provider, model, env)
    cost = (max(0, int(prompt_tokens)) * input_price + max(0, int(completion_tokens)) * output_price) / 1_000_000.0
    return round(cost, 6), source


def parse_budget_limits(env: Mapping[str, str] | None = None) -> list[BudgetLimit]:
    """Read every ``AI_BUDGET_*_USD`` limit.

    ``AI_BUDGET_DAILY_USD`` / ``AI_BUDGET_MONTHLY_USD`` cap all AI spend;
    ``AI_BUDGET_OPENAI_*`` / ``AI_BUDGET_GEMINI_*`` cap one provider;
    ``AI_BUDGET_WORKLOAD_<NAME>_*`` caps one workload (``signal_review``,
    ``market_context``, ``explanation``, ``chat``, ``research``, ...);
    ``AI_BUDGET_PER_USER_*`` caps each attributed user separately.
    A blank value means no limit; anything else that is not a finite,
    non-negative number becomes a zero limit (fail closed).
    """
    env = os.environ if env is None else env
    limits: list[BudgetLimit] = []
    for name in sorted(env):
        match = _LIMIT_RE.match(str(name))
        if not match:
            continue
        raw = str(env.get(name) or "").strip()
        if not raw:
            continue
        workload_flag, workload_name, provider, per_user, period = match.groups()
        if workload_flag:
            kind, value = "workload", normalize_workload(workload_name)
        elif provider:
            kind, value = "provider", provider.lower()
        elif per_user:
            kind, value = "per_user", None
        else:
            kind, value = "global", None
        try:
            limit = float(raw)
            valid = math.isfinite(limit) and limit >= 0
        except ValueError:
            limit, valid = 0.0, False
        limits.append(
            BudgetLimit(kind, value, period.lower(), limit if valid else 0.0, valid=valid, source=str(name))
        )
    return limits


def applicable_limits(
    limits: Sequence[BudgetLimit],
    *,
    provider: str,
    workload: str,
    user_id: int | None,
) -> list[BudgetLimit]:
    selected: list[BudgetLimit] = []
    for limit in limits:
        if limit.kind == "global":
            selected.append(limit)
        elif limit.kind == "provider" and limit.value == provider:
            selected.append(limit)
        elif limit.kind == "workload" and limit.value == workload:
            selected.append(limit)
        elif limit.kind == "per_user" and user_id is not None:
            selected.append(limit)
    return selected


def alert_thresholds(env: Mapping[str, str] | None = None) -> tuple[float, ...]:
    env = os.environ if env is None else env
    raw = str(env.get("AI_BUDGET_ALERT_THRESHOLDS") or "").strip()
    if not raw:
        return DEFAULT_ALERT_THRESHOLDS
    values: set[float] = set()
    for item in raw.split(","):
        try:
            value = float(item.strip())
        except ValueError:
            continue
        if math.isfinite(value) and 0 < value <= 1:
            values.add(round(value, 4))
    values.add(1.0)
    return tuple(sorted(values))


def evaluate_budgets(
    limits: Sequence[BudgetLimit],
    spend: Mapping[tuple[str, str], float],
    reservation_usd: float,
    *,
    user_id: int | None = None,
    thresholds: Sequence[float] = DEFAULT_ALERT_THRESHOLDS,
) -> BudgetDecision:
    """Decide one admission from current spend per (scope, period).

    The call is refused when, for any applicable limit, current spend plus this
    call's reservation would exceed the limit. Alerts fire for every threshold
    the projected spend reaches (deduplicated by the caller's storage).
    """
    alerts: list[BudgetAlert] = []
    refused: BudgetLimit | None = None
    for limit in limits:
        scope = limit.scope(user_id)
        current = max(0.0, float(spend.get((scope, limit.period), 0.0)))
        projected = current + max(0.0, float(reservation_usd))
        if not limit.valid or projected > limit.limit_usd + 1e-9:
            if refused is None:
                refused = limit
            alerts.append(BudgetAlert(scope, limit.period, 1.0, round(current, 6), limit.limit_usd, exhausted=True))
            continue
        if limit.limit_usd <= 0:
            continue
        ratio = projected / limit.limit_usd
        for threshold in thresholds:
            if ratio + 1e-12 >= float(threshold):
                alerts.append(BudgetAlert(scope, limit.period, float(threshold), round(projected, 6), limit.limit_usd))
    if refused is not None:
        return BudgetDecision(False, refused.scope(user_id), refused.period, tuple(alerts))
    return BudgetDecision(True, None, None, tuple(alerts))


_LIVE_SPEND_CTE = """
    WITH live AS (
        SELECT l.provider, l.workload, l.user_id, l.cost_usd, l.created_at
        FROM ai_usage_ledger l
        WHERE l.created_at >= date_trunc('month', timezone('utc', now()))
          AND (l.entry_kind = 'settlement'
               OR (l.entry_kind = 'reservation' AND NOT EXISTS (
                   SELECT 1 FROM ai_usage_ledger s
                   WHERE s.call_id = l.call_id AND s.entry_kind = 'settlement')))
    )
"""

_ADMISSION_SPEND_SQL = _LIVE_SPEND_CTE + """
    SELECT
        date_trunc('day', timezone('utc', now())) AS day_start,
        date_trunc('month', timezone('utc', now())) AS month_start,
        COALESCE(SUM(cost_usd) FILTER (WHERE created_at >= date_trunc('day', timezone('utc', now()))), 0) AS global_daily,
        COALESCE(SUM(cost_usd), 0) AS global_monthly,
        COALESCE(SUM(cost_usd) FILTER (WHERE provider = :provider
            AND created_at >= date_trunc('day', timezone('utc', now()))), 0) AS provider_daily,
        COALESCE(SUM(cost_usd) FILTER (WHERE provider = :provider), 0) AS provider_monthly,
        COALESCE(SUM(cost_usd) FILTER (WHERE workload = :workload
            AND created_at >= date_trunc('day', timezone('utc', now()))), 0) AS workload_daily,
        COALESCE(SUM(cost_usd) FILTER (WHERE workload = :workload), 0) AS workload_monthly,
        COALESCE(SUM(cost_usd) FILTER (WHERE user_id = :user_id
            AND created_at >= date_trunc('day', timezone('utc', now()))), 0) AS user_daily,
        COALESCE(SUM(cost_usd) FILTER (WHERE user_id = :user_id), 0) AS user_monthly
    FROM live
"""

_INSERT_SQL = """
    INSERT INTO ai_usage_ledger (
        call_id, entry_kind, provider, model, workload, task, user_id, telegram_user_id,
        prompt_tokens, completion_tokens, tokens_estimated, cost_usd, pricing_source,
        latency_ms, outcome, error, budget_scope
    ) VALUES (
        :call_id, :entry_kind, :provider, :model, :workload, :task, :user_id, :telegram_user_id,
        :prompt_tokens, :completion_tokens, :tokens_estimated, :cost_usd, :pricing_source,
        :latency_ms, :outcome, :error, :budget_scope
    )
"""

_ALERT_SQL = """
    INSERT INTO ai_budget_alerts (scope, period, period_start, threshold, spend_usd, limit_usd, exhausted)
    VALUES (:scope, :period, :period_start, :threshold, :spend_usd, :limit_usd, :exhausted)
    ON CONFLICT (scope, period, period_start, threshold) DO NOTHING
    RETURNING id
"""


def _log_unavailable(error: str) -> None:
    global _LAST_UNAVAILABLE_LOG
    now = time.monotonic()
    if now - _LAST_UNAVAILABLE_LOG > 300:
        _LAST_UNAVAILABLE_LOG = now
        logger.warning("[ai_cost] ledger unavailable error=%s; unbudgeted AI calls are not being recorded", error)


def _database_configured() -> bool:
    try:
        from db.session import get_database_url_or_none

        return bool(get_database_url_or_none())
    except Exception:
        return False


def _timeout() -> float:
    try:
        return max(0.5, min(10.0, float(os.getenv("AI_COST_LEDGER_TIMEOUT_SECONDS") or 3.0)))
    except ValueError:
        return 3.0


def _row(admission: Admission, **values: Any) -> dict[str, Any]:
    row = {
        "call_id": admission.call_id,
        "provider": admission.provider,
        "model": admission.model[:128],
        "workload": admission.workload,
        "task": admission.task[:96] if admission.task else None,
        "user_id": admission.user_id,
        "telegram_user_id": admission.telegram_user_id,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "tokens_estimated": False,
        "cost_usd": 0.0,
        "pricing_source": admission.pricing_source,
        "latency_ms": None,
        "error": None,
        "budget_scope": None,
    }
    row.update(values)
    return row


async def _record_alerts(session: Any, alerts: Sequence[BudgetAlert], day_start: Any, month_start: Any) -> None:
    from sqlalchemy import text

    for alert in alerts:
        inserted = (
            await session.execute(
                text(_ALERT_SQL),
                {
                    "scope": alert.scope[:160],
                    "period": alert.period,
                    "period_start": day_start if alert.period == "daily" else month_start,
                    "threshold": alert.threshold,
                    "spend_usd": alert.spend_usd,
                    "limit_usd": alert.limit_usd,
                    "exhausted": alert.exhausted,
                },
            )
        ).scalar_one_or_none()
        if inserted is not None:
            logger.warning(
                "[ai_cost] AI spend alert scope=%s period=%s threshold=%.0f%% spend_usd=%.4f limit_usd=%.4f exhausted=%s",
                alert.scope,
                alert.period,
                alert.threshold * 100,
                alert.spend_usd,
                alert.limit_usd,
                alert.exhausted,
            )


async def admit(
    *,
    provider: str,
    model: str,
    task: str,
    workload: str | None = None,
    estimated_prompt_tokens: int = 0,
    max_output_tokens: int = 0,
) -> Admission:
    """Reserve one AI call, or refuse it when a budget is exhausted."""
    attribution = current_attribution()
    provider = str(provider or "unknown").strip().lower()[:32]
    model = str(model or "unknown").strip()[:128] or "unknown"
    resolved_workload = normalize_workload(attribution.workload or workload or workload_for_task(task))
    prompt_tokens = max(0, int(estimated_prompt_tokens or 0))
    completion_tokens = max(0, int(max_output_tokens or 0))
    reserved_usd, pricing_source = estimate_cost(provider, model, prompt_tokens, completion_tokens)
    limits = applicable_limits(
        parse_budget_limits(),
        provider=provider,
        workload=resolved_workload,
        user_id=attribution.user_id,
    )
    base = Admission(
        admitted=True,
        call_id=uuid4().hex,
        provider=provider,
        model=model,
        workload=resolved_workload,
        task=str(task or "")[:96],
        user_id=attribution.user_id,
        telegram_user_id=attribution.telegram_user_id,
        reserved_prompt_tokens=prompt_tokens,
        reserved_completion_tokens=completion_tokens,
        reserved_usd=reserved_usd,
        pricing_source=pricing_source,
    )

    def _unavailable(error: str) -> Admission:
        if limits:
            logger.warning(
                "[ai_cost] AI call skipped: budget state unavailable provider=%s workload=%s error=%s",
                provider,
                resolved_workload,
                error,
            )
            return _replace(base, admitted=False, reason="budget_state_unavailable")
        _log_unavailable(error)
        return base

    if not ledger_enabled():
        return _unavailable("ledger_disabled")
    if not _database_configured():
        return _unavailable("database_not_configured")

    try:
        from sqlalchemy import text

        from db.session import get_session

        async with get_session(label="ai.cost_ledger.admit", timeout_seconds=_timeout()) as session:
            decision = BudgetDecision(True)
            if limits:
                await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _BUDGET_LOCK_KEY})
                spend_row = (
                    (
                        await session.execute(
                            text(_ADMISSION_SPEND_SQL),
                            {"provider": provider, "workload": resolved_workload, "user_id": attribution.user_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                spend: dict[tuple[str, str], float] = {
                    ("global", "daily"): float(spend_row["global_daily"]),
                    ("global", "monthly"): float(spend_row["global_monthly"]),
                    (f"provider:{provider}", "daily"): float(spend_row["provider_daily"]),
                    (f"provider:{provider}", "monthly"): float(spend_row["provider_monthly"]),
                    (f"workload:{resolved_workload}", "daily"): float(spend_row["workload_daily"]),
                    (f"workload:{resolved_workload}", "monthly"): float(spend_row["workload_monthly"]),
                }
                if attribution.user_id is not None:
                    spend[(f"user:{attribution.user_id}", "daily")] = float(spend_row["user_daily"])
                    spend[(f"user:{attribution.user_id}", "monthly")] = float(spend_row["user_monthly"])
                decision = evaluate_budgets(
                    limits,
                    spend,
                    reserved_usd,
                    user_id=attribution.user_id,
                    thresholds=alert_thresholds(),
                )
                await _record_alerts(session, decision.alerts, spend_row["day_start"], spend_row["month_start"])
            if not decision.admitted:
                scope = f"{decision.exhausted_scope}:{decision.exhausted_period}"
                await session.execute(
                    text(_INSERT_SQL),
                    _row(
                        base,
                        entry_kind="skipped",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        tokens_estimated=True,
                        outcome="budget_exhausted",
                        budget_scope=scope[:160],
                    ),
                )
                await session.commit()
                logger.warning(
                    "[ai_cost] AI call skipped: budget exhausted scope=%s provider=%s workload=%s task=%s",
                    scope,
                    provider,
                    resolved_workload,
                    task,
                )
                return _replace(
                    base, admitted=False, reason="budget_exhausted", scope=scope, recorded=True, alerts=decision.alerts
                )
            await session.execute(
                text(_INSERT_SQL),
                _row(
                    base,
                    entry_kind="reservation",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    tokens_estimated=True,
                    cost_usd=reserved_usd,
                    outcome="reserved",
                ),
            )
            await session.commit()
        return _replace(base, recorded=True, alerts=decision.alerts)
    except Exception as exc:
        return _unavailable(type(exc).__name__)


async def settle(
    admission: Admission,
    *,
    outcome: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    tokens_estimated: bool = False,
    latency_ms: float | None = None,
    error: str | None = None,
    billable: bool = True,
) -> None:
    """Record what one admitted call actually cost.

    ``billable=False`` marks a definite provider rejection (an HTTP error
    response): nothing was generated, so it costs nothing. When token counts
    are unknown for a billable outcome the reserved estimate is kept.
    """
    if not admission.admitted or not admission.recorded:
        return
    if not billable:
        prompt, completion, estimated = 0, 0, False
    elif prompt_tokens is None and completion_tokens is None:
        prompt, completion, estimated = admission.reserved_prompt_tokens, admission.reserved_completion_tokens, True
    else:
        prompt, completion, estimated = max(0, int(prompt_tokens or 0)), max(0, int(completion_tokens or 0)), tokens_estimated
    cost, pricing_source = estimate_cost(admission.provider, admission.model, prompt, completion)
    try:
        from sqlalchemy import text

        from db.session import get_session

        async with get_session(label="ai.cost_ledger.settle", timeout_seconds=_timeout()) as session:
            await session.execute(
                text(_INSERT_SQL),
                _row(
                    admission,
                    entry_kind="settlement",
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    tokens_estimated=bool(estimated),
                    cost_usd=cost,
                    pricing_source=pricing_source,
                    latency_ms=float(latency_ms) if latency_ms is not None else None,
                    outcome=str(outcome or "unknown")[:48],
                    error=str(error)[:160] if error else None,
                ),
            )
            await session.commit()
    except Exception as exc:
        # The reservation stays unsettled and keeps counting at its worst case.
        logger.warning(
            "[ai_cost] settlement write failed call_id=%s error=%s; reserved cost remains counted",
            admission.call_id,
            type(exc).__name__,
        )


def _replace(admission: Admission, **changes: Any) -> Admission:
    from dataclasses import replace

    return replace(admission, **changes)


def openai_usage_tokens(usage: Mapping[str, Any] | None) -> tuple[int | None, int | None]:
    """(input, output) tokens from a Responses API ``usage`` object.

    Output tokens include reasoning tokens. Cached input tokens are priced as
    ordinary input, which over-states rather than under-states cost.
    """
    if not isinstance(usage, Mapping):
        return None, None
    try:
        prompt = int(usage.get("input_tokens")) if usage.get("input_tokens") is not None else None
        completion = int(usage.get("output_tokens")) if usage.get("output_tokens") is not None else None
    except (TypeError, ValueError):
        return None, None
    return prompt, completion


def gemini_usage_tokens(response: Any, prompt: str = "") -> tuple[int, int, bool]:
    """(prompt, completion, estimated) tokens from a google-genai response.

    Thinking tokens are billed as output. Without usage metadata the counts
    are estimated from the prompt and response text.
    """
    meta = getattr(response, "usage_metadata", None)
    try:
        prompt_tokens = getattr(meta, "prompt_token_count", None)
        candidates = getattr(meta, "candidates_token_count", None)
        thoughts = getattr(meta, "thoughts_token_count", None)
        if prompt_tokens is not None or candidates is not None:
            return int(prompt_tokens or 0), int(candidates or 0) + int(thoughts or 0), False
    except (TypeError, ValueError):
        pass
    text = ""
    try:
        text = str(getattr(response, "text", "") or "")
    except Exception:
        text = ""
    return estimate_tokens(prompt), estimate_tokens(text), True


async def spend_summary(*, days: int = 30, user_limit: int = 50) -> dict[str, Any]:
    """Owner/admin spend view: totals by provider, workload, model and user, budgets and alerts."""
    from sqlalchemy import text

    from db.session import get_session

    days = max(1, min(366, int(days)))
    user_limit = max(1, min(500, int(user_limit)))
    window = {"days": days}
    live_window = """
        WITH live AS (
            SELECT l.provider, l.model, l.workload, l.user_id, l.cost_usd, l.created_at,
                   l.prompt_tokens, l.completion_tokens, l.entry_kind, l.outcome, l.latency_ms,
                   l.pricing_source
            FROM ai_usage_ledger l
            WHERE l.created_at >= timezone('utc', now()) - make_interval(days => :days)
              AND (l.entry_kind = 'settlement'
                   OR (l.entry_kind = 'reservation' AND NOT EXISTS (
                       SELECT 1 FROM ai_usage_ledger s
                       WHERE s.call_id = l.call_id AND s.entry_kind = 'settlement')))
        )
    """
    group_sql = live_window + """
        SELECT {key} AS key,
               COUNT(*) FILTER (WHERE entry_kind = 'settlement') AS calls,
               COUNT(*) FILTER (WHERE entry_kind = 'reservation') AS unsettled,
               COUNT(*) FILTER (WHERE entry_kind = 'settlement' AND outcome <> 'ok') AS failed,
               COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
               COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
               COALESCE(SUM(cost_usd), 0) AS cost_usd,
               AVG(latency_ms) FILTER (WHERE entry_kind = 'settlement') AS avg_latency_ms
        FROM live {where}
        GROUP BY {key}
        ORDER BY cost_usd DESC
        {limit}
    """

    def _rows(result: Any) -> list[dict[str, Any]]:
        rows = []
        for row in result.mappings().all():
            rows.append(
                {
                    "key": row["key"],
                    "calls": int(row["calls"] or 0),
                    "unsettled": int(row["unsettled"] or 0),
                    "failed": int(row["failed"] or 0),
                    "prompt_tokens": int(row["prompt_tokens"] or 0),
                    "completion_tokens": int(row["completion_tokens"] or 0),
                    "cost_usd": round(float(row["cost_usd"] or 0), 6),
                    "avg_latency_ms": round(float(row["avg_latency_ms"]), 2)
                    if row["avg_latency_ms"] is not None
                    else None,
                }
            )
        return rows

    async with get_session(label="ai.cost_ledger.summary", timeout_seconds=10.0) as session:
        by_provider = _rows(await session.execute(text(group_sql.format(key="provider", where="", limit="")), window))
        by_workload = _rows(await session.execute(text(group_sql.format(key="workload", where="", limit="")), window))
        by_model = _rows(
            await session.execute(text(group_sql.format(key="provider || ':' || model", where="", limit="")), window)
        )
        by_user = _rows(
            await session.execute(
                text(group_sql.format(key="user_id", where="WHERE user_id IS NOT NULL", limit="LIMIT :user_limit")),
                {**window, "user_limit": user_limit},
            )
        )
        unpriced = [
            str(row[0])
            for row in (
                await session.execute(
                    text(live_window + "SELECT DISTINCT provider || ':' || model FROM live "
                         "WHERE pricing_source = 'unpriced_conservative' ORDER BY 1"),
                    window,
                )
            ).all()
        ]
        skipped = [
            {"scope": row["budget_scope"], "count": int(row["count"])}
            for row in (
                await session.execute(
                    text(
                        "SELECT budget_scope, COUNT(*) AS count FROM ai_usage_ledger "
                        "WHERE entry_kind = 'skipped' AND created_at >= timezone('utc', now()) - make_interval(days => :days) "
                        "GROUP BY budget_scope ORDER BY count DESC"
                    ),
                    window,
                )
            )
            .mappings()
            .all()
        ]
        period = (
            (
                await session.execute(
                    text(
                        _LIVE_SPEND_CTE
                        + """
                SELECT date_trunc('day', timezone('utc', now())) AS day_start,
                       date_trunc('month', timezone('utc', now())) AS month_start,
                       provider, workload, user_id,
                       COALESCE(SUM(cost_usd) FILTER (
                           WHERE created_at >= date_trunc('day', timezone('utc', now()))), 0) AS daily,
                       COALESCE(SUM(cost_usd), 0) AS monthly
                FROM live GROUP BY provider, workload, user_id"""
                    )
                )
            )
            .mappings()
            .all()
        )
        alerts = [
            {
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "scope": row["scope"],
                "period": row["period"],
                "threshold": float(row["threshold"]),
                "spend_usd": float(row["spend_usd"]),
                "limit_usd": float(row["limit_usd"]),
                "exhausted": bool(row["exhausted"]),
            }
            for row in (
                await session.execute(
                    text(
                        "SELECT created_at, scope, period, threshold, spend_usd, limit_usd, exhausted "
                        "FROM ai_budget_alerts ORDER BY created_at DESC, id DESC LIMIT 50"
                    )
                )
            )
            .mappings()
            .all()
        ]
        await session.rollback()

    spend: dict[tuple[str, str], float] = {}
    for row in period:
        daily, monthly = float(row["daily"] or 0), float(row["monthly"] or 0)
        scopes = ["global", f"provider:{row['provider']}", f"workload:{row['workload']}"]
        if row["user_id"] is not None:
            scopes.append(f"user:{row['user_id']}")
        for scope in scopes:
            spend[(scope, "daily")] = spend.get((scope, "daily"), 0.0) + daily
            spend[(scope, "monthly")] = spend.get((scope, "monthly"), 0.0) + monthly
    budgets = []
    for limit in parse_budget_limits():
        if limit.kind == "per_user":
            users = sorted({scope for scope, period_name in spend if scope.startswith("user:") and period_name == limit.period})
            scopes = users or ["user:*"]
        else:
            scopes = [limit.scope()]
        for scope in scopes:
            current = round(spend.get((scope, limit.period), 0.0), 6)
            budgets.append(
                {
                    "scope": scope,
                    "period": limit.period,
                    "env": limit.source,
                    "valid": limit.valid,
                    "limit_usd": limit.limit_usd,
                    "spend_usd": current,
                    "remaining_usd": round(max(0.0, limit.limit_usd - current), 6),
                    "used_ratio": round(current / limit.limit_usd, 4) if limit.limit_usd > 0 else None,
                    "exhausted": (not limit.valid) or current >= limit.limit_usd,
                }
            )
    return {
        "window_days": days,
        "basis": "Settled estimated cost plus unsettled reservations at their worst case; UTC periods.",
        "ledger_enabled": ledger_enabled(),
        "totals": {
            "cost_usd": round(sum(row["cost_usd"] for row in by_provider), 6),
            "calls": sum(row["calls"] for row in by_provider),
            "unsettled": sum(row["unsettled"] for row in by_provider),
        },
        "by_provider": by_provider,
        "by_workload": by_workload,
        "by_model": by_model,
        "by_user": by_user,
        "skipped_by_budget": skipped,
        "budgets": budgets,
        "alerts": alerts,
        "alert_thresholds": list(alert_thresholds()),
        "unpriced_models": unpriced,
        "pricing_note": (
            "Costs are estimates from AI_MODEL_PRICING_JSON; unpriced models use a deliberately high fallback. "
            "Reconcile against provider invoices before treating these as billed amounts."
        ),
    }


__all__ = [
    "AIBudgetExhausted",
    "Admission",
    "Attribution",
    "BudgetAlert",
    "BudgetDecision",
    "BudgetLimit",
    "admit",
    "ai_usage_attribution",
    "alert_thresholds",
    "applicable_limits",
    "current_attribution",
    "estimate_cost",
    "estimate_tokens",
    "evaluate_budgets",
    "gemini_usage_tokens",
    "ledger_enabled",
    "normalize_workload",
    "openai_usage_tokens",
    "parse_budget_limits",
    "price_for",
    "settle",
    "spend_summary",
    "workload_for_task",
]
