"""Small liveness/readiness contracts shared by runtime role adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Iterable


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class HealthReport:
    status: str
    checks: tuple[HealthCheck, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {"status": self.status, "checks": [asdict(item) for item in self.checks]}


def livez() -> HealthReport:
    return HealthReport("live")


def readyz(checks: Iterable[HealthCheck] = ()) -> HealthReport:
    values = tuple(checks)
    return HealthReport("ready" if all(item.ok for item in values) else "degraded", values)


def role_readiness(role: str, checks: Iterable[Callable[[], HealthCheck]] = ()) -> dict[str, object]:
    results: list[HealthCheck] = []
    for check in checks:
        try:
            results.append(check())
        except Exception as exc:  # readiness must never crash the health endpoint
            results.append(HealthCheck(getattr(check, "__name__", "dependency"), False, type(exc).__name__))
    report = readyz(results)
    payload = report.as_dict()
    payload["role"] = str(role)
    return payload


__all__ = ["HealthCheck", "HealthReport", "livez", "readyz", "role_readiness"]
