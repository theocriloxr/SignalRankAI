#!/usr/bin/env python
"""Test importing all main modules to find startup errors."""
import sys
sys.path.insert(0, "c:/Users/sammm/Desktop/SignalRankAI")

# Test each import one by one
modules = [
    "os",
    "logging",
    "datetime",
    "sqlalchemy",
    "asyncpg",
    "fastapi",
    "uvicorn",
    "core.version",
    "core.settings",
    "core.redis_state",
    "core.redis_cache",
    "db.session",
    "db.models",
    "db.repository",
    "web.app",
]

for mod in modules:
    try:
        __import__(mod)
        print(f"✓ {mod}")
    except Exception as e:
        print(f"✗ {mod}: {type(e).__name__}: {e}")

print("\nTrying railway_main...")
try:
    import railway_main
    print("✓ railway_main loaded")
except Exception as e:
    print(f"✗ railway_main: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
