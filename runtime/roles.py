"""Canonical process-role contract for SignalRankAI.

Pass 7 introduces a small ownership boundary before moving work out of the
legacy monolith.  Role adapters are intentionally dependency-light and may be
used by tests, health checks, and deployment tooling without importing the
Telegram, database, or provider stacks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class RunMode(StrEnum):
    WEB = "web"
    BOT = "bot"
    ENGINE = "engine"
    DELIVERY = "delivery"
    OUTCOME = "outcome"
    ANALYTICS = "analytics"
    SCHEDULER = "scheduler"
    ALL_DEV = "all/dev"


class SchedulerOwner(StrEnum):
    """Explicit owner for scheduler/maintenance registration."""

    MONOLITH = "monolith"
    STANDALONE = "scheduler"
    DISABLED = "disabled"


# Existing deployments use ``worker`` and ``all``.  Keep these aliases for a
# bounded compatibility window, but expose only the canonical enum values to
# new callers.
MODE_ALIASES: Mapping[str, RunMode] = {
    "all": RunMode.ALL_DEV,
    "all_dev": RunMode.ALL_DEV,
    "dev": RunMode.ALL_DEV,
    "worker": RunMode.DELIVERY,
}


@dataclass(frozen=True, slots=True)
class RoleSpec:
    mode: RunMode
    owns: str
    description: str
    legacy_aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SchedulerOwnership:
    """Resolved scheduler ownership for one deployment.

    The single-process monolith is the safe default.  A decomposed scheduler
    process must be selected explicitly and must hold the distributed lease
    implemented by :mod:`runtime.scheduler`.
    """

    owner: SchedulerOwner
    lease_required: bool

    def allows(self, mode: str | RunMode) -> bool:
        parsed = parse_run_mode(mode)
        if self.owner is SchedulerOwner.MONOLITH:
            return parsed is RunMode.ALL_DEV
        if self.owner is SchedulerOwner.STANDALONE:
            return parsed is RunMode.SCHEDULER
        return False


ROLE_SPECS: Mapping[RunMode, RoleSpec] = {
    RunMode.WEB: RoleSpec(RunMode.WEB, "FastAPI ingress and API", "HTTP routes and readiness", ()),
    RunMode.BOT: RoleSpec(RunMode.BOT, "Telegram interaction", "Commands and callbacks", ()),
    RunMode.ENGINE: RoleSpec(RunMode.ENGINE, "Signal candidate pipeline", "Market analysis and persistence", ()),
    RunMode.DELIVERY: RoleSpec(
        RunMode.DELIVERY,
        "Delivery receipts and outbox work",
        "Final eligibility, send proof, and reconciliation",
        ("worker",),
    ),
    RunMode.OUTCOME: RoleSpec(RunMode.OUTCOME, "Signal lifecycle outcomes", "Batched outcome detection", ()),
    RunMode.ANALYTICS: RoleSpec(RunMode.ANALYTICS, "Performance analytics", "Shadow/WFO/report jobs", ()),
    RunMode.SCHEDULER: RoleSpec(
        RunMode.SCHEDULER,
        "Leased scheduler/maintenance hand-off",
        "Explicit standalone owner guarded by a singleton lease",
        (),
    ),
    RunMode.ALL_DEV: RoleSpec(
        RunMode.ALL_DEV,
        "Compatibility composition including scheduler/maintenance",
        "All roles in one local process",
        ("all", "dev"),
    ),
}


def parse_run_mode(value: str | RunMode | None) -> RunMode:
    """Parse a strict role value, accepting only documented legacy aliases."""

    if isinstance(value, RunMode):
        return value
    raw = str(value or "").strip().lower().replace("\\", "/")
    if not raw:
        raise ValueError("RUN_MODE is required (web, bot, engine, delivery, outcome, analytics, scheduler, all/dev)")
    try:
        return RunMode(raw)
    except ValueError:
        try:
            return MODE_ALIASES[raw]
        except KeyError as exc:
            allowed = ", ".join(mode.value for mode in RunMode)
            raise ValueError(f"Unknown RUN_MODE={raw!r}; expected one of: {allowed}") from exc


def infer_run_mode(environ: Mapping[str, str] | None = None) -> RunMode:
    """Resolve ``RUN_MODE`` or infer one from a Railway service name.

    The historical default was ``engine``; preserving it avoids changing local
    and existing Railway behavior while deployments migrate to explicit roles.
    """

    env = os.environ if environ is None else environ
    explicit = str(env.get("RUN_MODE") or "").strip()
    if explicit:
        return parse_run_mode(explicit)

    service = str(env.get("RAILWAY_SERVICE_NAME") or env.get("RAILWAY_SERVICE") or "").lower()
    for needle, mode in (
        ("all", RunMode.ALL_DEV),
        ("web", RunMode.WEB),
        ("bot", RunMode.BOT),
        ("telegram", RunMode.BOT),
        ("delivery", RunMode.DELIVERY),
        ("worker", RunMode.DELIVERY),
        ("outcome", RunMode.OUTCOME),
        ("analytics", RunMode.ANALYTICS),
        ("scheduler", RunMode.SCHEDULER),
        ("engine", RunMode.ENGINE),
        ("core", RunMode.ENGINE),
    ):
        if needle in service:
            return mode
    return RunMode.ENGINE


def role_spec(mode: str | RunMode | None) -> RoleSpec:
    """Return immutable ownership metadata for a role."""

    return ROLE_SPECS[parse_run_mode(mode)]


def scheduler_ownership(environ: Mapping[str, str] | None = None) -> SchedulerOwnership:
    """Resolve the one scheduler owner for this deployment.

    ``SCHEDULER_OWNER`` defaults to ``monolith``.  Selecting ``scheduler`` is
    an explicit decomposition hand-off and therefore requires a distributed
    lease.  The existing explicit ``RUN_MODE=scheduler`` contract performs the
    same hand-off so the legacy Procfile remains usable.  ``disabled`` is
    accepted for maintenance windows and tests.
    """

    env = os.environ if environ is None else environ
    configured_owner = env.get("SCHEDULER_OWNER") or env.get(
        "SCHEDULER_OWNER_ROLE"
    )
    if configured_owner:
        owner_value = configured_owner
    elif str(env.get("RUN_MODE") or "").strip().lower() == RunMode.SCHEDULER.value:
        owner_value = SchedulerOwner.STANDALONE.value
    else:
        owner_value = SchedulerOwner.MONOLITH.value
    raw = str(
        owner_value
    ).strip().lower().replace("_", "/")
    aliases = {
        "all": SchedulerOwner.MONOLITH,
        "all/dev": SchedulerOwner.MONOLITH,
        "web": SchedulerOwner.MONOLITH,
        "monolith": SchedulerOwner.MONOLITH,
        "scheduler": SchedulerOwner.STANDALONE,
        "standalone": SchedulerOwner.STANDALONE,
        "off": SchedulerOwner.DISABLED,
        "none": SchedulerOwner.DISABLED,
        "disabled": SchedulerOwner.DISABLED,
    }
    try:
        owner = aliases[raw]
    except KeyError as exc:
        allowed = ", ".join(owner.value for owner in SchedulerOwner)
        raise ValueError(
            f"Unknown SCHEDULER_OWNER={raw!r}; expected one of: {allowed}"
        ) from exc
    return SchedulerOwnership(
        owner=owner,
        lease_required=(owner is SchedulerOwner.STANDALONE),
    )


__all__ = [
    "MODE_ALIASES",
    "ROLE_SPECS",
    "RoleSpec",
    "RunMode",
    "SchedulerOwner",
    "SchedulerOwnership",
    "infer_run_mode",
    "parse_run_mode",
    "role_spec",
    "scheduler_ownership",
]
