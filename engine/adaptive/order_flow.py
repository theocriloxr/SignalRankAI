"""Backward-compatible adaptive component import path.

The canonical implementation lives in :mod:`engine.adaptive.components.order_flow`.
This shim keeps older deployments and extensions operational.
"""
from .components.order_flow import OrderFlowComponent

__all__ = ["OrderFlowComponent"]
