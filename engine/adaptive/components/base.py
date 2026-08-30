from __future__ import annotations

from typing import Protocol
from engine.adaptive.types import MarketContext, StrategyEvidence


class StrategyComponent(Protocol):
    strategy_id: str
    version: str
    family: str

    def evaluate(self, context: MarketContext) -> tuple[StrategyEvidence, ...]: ...
