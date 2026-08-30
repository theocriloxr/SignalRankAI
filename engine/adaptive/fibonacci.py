"""Backward-compatible adaptive component import path.

The canonical implementation lives in :mod:`engine.adaptive.components.fibonacci`.
This shim keeps older deployments and extensions operational.
"""
from .components.fibonacci import FibonacciComponent

__all__ = ["FibonacciComponent"]
