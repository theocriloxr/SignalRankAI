"""Canonical execution boundary.

The package intentionally contains policy and orchestration only. Broker
adapters remain in :mod:`services.mt5_client`; callers must pass the explicit
preflight gate before an adapter can be invoked.
"""

from .service import (
    ExecutionGate,
    ExecutionRequest,
    ExecutionResult,
    GateDecision,
)

__all__ = ["ExecutionGate", "ExecutionRequest", "ExecutionResult", "GateDecision"]
