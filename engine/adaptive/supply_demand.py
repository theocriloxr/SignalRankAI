"""Backward-compatible adaptive component import path.

The canonical implementation lives in :mod:`engine.adaptive.components.supply_demand`.
This shim keeps older deployments and extensions operational.
"""
from .components.supply_demand import SupplyDemandComponent

__all__ = ["SupplyDemandComponent"]
