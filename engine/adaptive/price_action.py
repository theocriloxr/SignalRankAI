"""Backward-compatible adaptive component import path.

The canonical implementation lives in :mod:`engine.adaptive.components.price_action`.
This shim keeps older deployments and extensions operational.
"""
from .components.price_action import PriceActionComponent

__all__ = ["PriceActionComponent"]
