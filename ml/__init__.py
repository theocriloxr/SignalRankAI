"""SignalRankAI machine-learning package.

Submodules are loaded lazily so the production bot/engine does not import the
training stack unless a known ML surface is explicitly requested.
"""

from __future__ import annotations

from types import ModuleType

__all__ = ["train_model", "inference", "features", "scorer"]


def __getattr__(name: str) -> ModuleType:
    if name == "train_model":
        import ml.train_model as module
        return module
    if name == "inference":
        import ml.inference as module
        return module
    if name == "features":
        import ml.features as module
        return module
    if name == "scorer":
        import ml.scorer as module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(__all__))
