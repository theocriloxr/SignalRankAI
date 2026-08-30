"""Backward-compatible adaptive component import path.

The canonical implementation lives in :mod:`engine.adaptive.components.indicators`.
This shim keeps older deployments and extensions operational.
"""
from .components.indicators import IndicatorComponent

__all__ = ["IndicatorComponent"]
