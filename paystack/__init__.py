"""SignalRank's local Paystack integration package.

This directory is the canonical Paystack module used across the front door,
worker and webhook (``paystack.paystack``). The ``__init__.py`` guarantees the
local package is a *regular* package so it takes precedence over any unused
installed PyPI ``paystack`` distribution that may otherwise shadow it.
"""
