"""Backward-compatible adaptive component import path.

The canonical implementation lives in :mod:`engine.adaptive.components.wyckoff`.
This shim keeps older deployments and extensions operational.
"""
from .components.wyckoff import WyckoffComponent

__all__ = ["WyckoffComponent"]
