"""SignalRankAI machine-learning package.

Submodules are loaded lazily so the production bot/engine does not import the
XGBoost training stack merely because a lightweight ML helper is referenced.
The analytics role can continue to use ``from ml import train_model`` without
changing call sites.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

__all__ = ["train_model", "inference", "features", "scorer"]


def __getattr__(name: str) -> ModuleType:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f"{__name__}.{name}")
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
