from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass
class CircuitConfig:
    failure_threshold: int = 3
    window_seconds: float = 10.0
    open_seconds: float = 30.0


class CircuitBreaker:
    def __init__(self, config: CircuitConfig | None = None) -> None:
        self.config = config or CircuitConfig()
        self._failures: deque[float] = deque()
        self._open_until: float = 0.0

    def _now(self) -> float:
        return time.time()

    def _prune(self, now_ts: float) -> None:
        window_start = now_ts - float(self.config.window_seconds)
        while self._failures and self._failures[0] < window_start:
            self._failures.popleft()

    def allow(self) -> bool:
        now_ts = self._now()
        if now_ts < self._open_until:
            return False
        self._prune(now_ts)
        return True

    def record_success(self) -> None:
        self._failures.clear()
        self._open_until = 0.0

    def record_failure(self) -> bool:
        now_ts = self._now()
        self._failures.append(now_ts)
        self._prune(now_ts)
        if len(self._failures) >= int(self.config.failure_threshold):
            self._open_until = now_ts + float(self.config.open_seconds)
            return True
        return False


_provider_breakers: dict[str, CircuitBreaker] = {}


def provider_breaker(name: str) -> CircuitBreaker:
    key = str(name or "unknown").strip().lower() or "unknown"
    if key not in _provider_breakers:
        _provider_breakers[key] = CircuitBreaker()
    return _provider_breakers[key]


def get_provider_breaker_snapshot() -> dict[str, dict[str, float | int | bool]]:
    now_ts = time.time()
    snapshot: dict[str, dict[str, float | int | bool]] = {}
    for name, breaker in _provider_breakers.items():
        try:
            open_until = float(getattr(breaker, "_open_until", 0.0) or 0.0)
            failures = list(getattr(breaker, "_failures", []) or [])
        except Exception:
            open_until = 0.0
            failures = []
        open_remaining = max(0.0, open_until - now_ts) if open_until else 0.0
        cfg = getattr(breaker, "config", None)
        snapshot[str(name)] = {
            "open": bool(open_remaining > 0.0),
            "open_remaining_s": float(open_remaining),
            "failures": int(len(failures)),
            "failure_threshold": int(getattr(cfg, "failure_threshold", 0) or 0),
            "window_seconds": float(getattr(cfg, "window_seconds", 0.0) or 0.0),
            "open_seconds": float(getattr(cfg, "open_seconds", 0.0) or 0.0),
        }
    return snapshot
