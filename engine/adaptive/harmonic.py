"""Backward-compatible adaptive component import path.

The canonical implementation lives in :mod:`engine.adaptive.components.harmonic`.
This shim keeps older deployments and extensions operational.
"""
from .components.harmonic import HarmonicComponent

__all__ = ["HarmonicComponent"]
