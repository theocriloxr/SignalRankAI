"""Backward-compatible Elliott Wave import path.

The canonical implementation lives in :mod:`engine.adaptive.components.elliott`.
This shim keeps deployments and extensions that still import
``engine.adaptive.elliott`` operational while the package layout remains
component-based.
"""
from .components.elliott import ElliottWaveComponent

__all__ = ["ElliottWaveComponent"]
