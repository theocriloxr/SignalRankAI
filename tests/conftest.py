"""Repository-wide pytest dependency boundaries."""
from __future__ import annotations

import sys

# SignalRankAI is asyncio-native and does not declare Eventlet. Some developer
# machines have an unrelated user-level Eventlet install; curl_cffi probes for
# it opportunistically and emits a deprecation warning. Mark the undeclared
# optional module unavailable so tests exercise the production dependency set.
sys.modules.setdefault("eventlet", None)
