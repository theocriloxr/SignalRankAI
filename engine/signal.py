from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    signal_id: str
    asset: str
    timeframe: str
    direction: str  # 'long' or 'short'
    entry: float
    stop_loss: float
    take_profit: Optional[float] = None
    score: Optional[float] = None
    strategy: Optional[str] = None
    metadata: dict = None
