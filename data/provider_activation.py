"""Central provider activation state machine.

Every provider resolves to exactly one activation state per environment:

    disabled | public_ready | missing_credentials | invalid_credentials |
    plan_insufficient | rate_limited | healthy | degraded | circuit_open |
    suspended

Rules (Phase 24 / provider addendum §22):

* A public endpoint with the provider enabled  -> public_ready (market data on).
* A credential-backed provider without keys    -> missing_credentials (never
  a service failure, never log spam).
* Credentials present + explicit market-data flag -> healthy.
* Execution keys NEVER activate execution on their own.  Execution requires
  the provider's explicit execution flag *and* certification evidence.

This module is pure and side-effect free (no network, no Redis) so every
service can resolve the same structured answer.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class ProviderActivationState(str, Enum):
    DISABLED = "disabled"
    PUBLIC_READY = "public_ready"
    MISSING_CREDENTIALS = "missing_credentials"
    INVALID_CREDENTIALS = "invalid_credentials"
    PLAN_INSUFFICIENT = "plan_insufficient"
    RATE_LIMITED = "rate_limited"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CIRCUIT_OPEN = "circuit_open"
    SUSPENDED = "suspended"


@dataclass(frozen=True, slots=True)
class ProviderActivation:
    """Structured activation decision for one provider in one environment."""

    provider: str
    state: ProviderActivationState
    market_data_ready: bool
    execution_ready: bool
    reason: str
    required_env: tuple[str, ...] = ()
    present_env: tuple[str, ...] = ()

    @property
    def can_serve_analysis(self) -> bool:
        """Analysis/market-data may proceed in these states."""
        return self.state in (
            ProviderActivationState.PUBLIC_READY,
            ProviderActivationState.HEALTHY,
            ProviderActivationState.DEGRADED,
        )

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "state": self.state.value,
            "market_data_ready": self.market_data_ready,
            "execution_ready": self.execution_ready,
            "reason": self.reason,
            "required_env": list(self.required_env),
            "present_env": list(self.present_env),
        }


def _as_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().lower() for item in str(value).split(",") if item.strip()}


def resolve_activation(
    *,
    provider: str,
    enabled_env: str | None = None,
    default_enabled: bool = False,
    public_endpoint: bool = False,
    required_env: tuple[str, ...] = (),
    execution_flag_env: str | None = None,
    execution_certification_env: str | None = None,
    allowlist_env: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ProviderActivation:
    """Resolve the provider activation decision from environment variables."""
    source: Mapping[str, str] = os.environ if env is None else env

    # Explicit admin/health overrides always win (visible even when the
    # provider is otherwise disabled).
    if _as_bool(source.get(f"{provider.upper()}_SUSPENDED")):
        return ProviderActivation(
            provider, ProviderActivationState.SUSPENDED, False, False,
            "provider_suspended_by_configuration",
        )
    if _as_bool(source.get(f"{provider.upper()}_CIRCUIT_OPEN")):
        return ProviderActivation(
            provider, ProviderActivationState.CIRCUIT_OPEN, False, False,
            "provider_circuit_open",
        )
    if _as_bool(source.get(f"{provider.upper()}_RATE_LIMITED")):
        return ProviderActivation(
            provider, ProviderActivationState.RATE_LIMITED, False, False,
            "provider_rate_limit_exhausted",
        )
    if _as_bool(source.get(f"{provider.upper()}_PLAN_INSUFFICIENT")):
        return ProviderActivation(
            provider, ProviderActivationState.PLAN_INSUFFICIENT, False, False,
            "provider_plan_insufficient",
        )

    # Enabled gate.
    enabled = _as_bool(
        source.get(enabled_env or f"{provider.upper()}_ENABLED"), default_enabled
    )
    if not enabled:
        return ProviderActivation(
            provider, ProviderActivationState.DISABLED, False, False,
            "provider_disabled_by_feature_flag",
        )

    present = tuple(name for name in required_env if str(source.get(name, "")).strip())
    credentials_present = (not required_env) or public_endpoint or len(present) == len(required_env)

    # Execution is NEVER derived from credentials alone.
    execution_ready = False
    if execution_flag_env:
        raw_flag = str(source.get(execution_flag_env, "")).strip().lower()
        explicit_live = raw_flag in {"live", "live_guarded", "1", "true", "on"}
        certified_raw = str(source.get(execution_certification_env or "") or "").strip()
        # A literal "0"/"false"/"no" is NOT certification evidence.
        certified = bool(certified_raw) and certified_raw.lower() not in {"0", "false", "no", "off"}
        if explicit_live and not certified:
            return ProviderActivation(
                provider, ProviderActivationState.PLAN_INSUFFICIENT, False, False,
                "execution_flag_set_without_certification_evidence",
                required_env, present,
            )
        execution_ready = explicit_live and certified and credentials_present
        # Trading also requires an instrument allowlist when one is configured.
        if execution_ready and allowlist_env:
            execution_ready = bool(_as_set(source.get(allowlist_env)))

    if not public_endpoint and required_env and len(present) < len(required_env):
        missing = tuple(name for name in required_env if not str(source.get(name, "")).strip())
        return ProviderActivation(
            provider, ProviderActivationState.MISSING_CREDENTIALS, False, execution_ready,
            f"missing_credentials:{','.join(missing)}",
            required_env, present,
        )

    if public_endpoint or present:
        state = ProviderActivationState.PUBLIC_READY if not required_env else ProviderActivationState.HEALTHY
        return ProviderActivation(
            provider, state, True, execution_ready,
            "public_endpoint_ready" if state is ProviderActivationState.PUBLIC_READY
            else "credentials_verified_and_healthy",
            required_env, present,
        )

    return ProviderActivation(
        provider, ProviderActivationState.MISSING_CREDENTIALS, False, execution_ready,
        "credentials_absent", required_env, present,
    )


def execution_mode(source: Mapping[str, str] | None = None) -> str:
    """Global execution mode resolution (paper | testnet | live_guarded | live | disabled)."""
    env = os.environ if source is None else source
    if _as_bool(env.get("REAL_EXECUTION_ENABLED")):
        return "live_guarded"
    if _as_bool(env.get("LIVE_EXECUTION_ENABLED")):
        return "live_guarded"
    if _as_bool(env.get("TESTNET_EXECUTION_ENABLED")):
        return "testnet"
    if _as_bool(env.get("PAPER_TRADING_ENABLED"), True):
        return "paper"
    return "disabled"


__all__ = [
    "ProviderActivation",
    "ProviderActivationState",
    "execution_mode",
    "resolve_activation",
]
