"""Backward-compatible adaptive component import path.

The canonical implementation lives in :mod:`engine.adaptive.components.ict_smc`.
This shim keeps older deployments and extensions operational.
"""
from .components.ict_smc import ICTSmartMoneyComponent

__all__ = ["ICTSmartMoneyComponent"]
