from __future__ import annotations

from typing import List

from engine.signal import Signal


class Strategy:
    """Base strategy interface.

    Implementations should provide `generate` that returns a list of `Signal`.
    """
    name = "base"

    def generate(self, market_data: dict) -> List[Signal]:  # pragma: no cover - interface
        raise NotImplementedError()
