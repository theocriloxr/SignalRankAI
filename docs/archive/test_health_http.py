#!/usr/bin/env python
"""HTTP test."""
import sys
import os
os.environ.pop("RAILWAY_SERVICE_NAME", None)
os.environ.pop("DATABASE_URL", None)

sys.path.insert(0, "c:/Users/sammm/Desktop/SignalRankAI")

import asyncio
from railway_main import app
from fastapi.testclient import TestClient

client = TestClient(app, raise_server_exceptions=False)

# Test on main app directly 
print("=== Test /telegram/webhook_status (main app) ===")
r = client.get("/telegram/webhook_status")
print(f"  Status: {r.status_code}")
print(f"  Body: {r.text[:200]}")

print("\n=== Test /healthz (mounted) ===")
r = client.get("/healthz")
print(f"  Status: {r.status_code}")
print(f"  Body: {r.text[:200]}")

print("\n=== Test /healthz again ===")
r = client.get("/healthz")
print(f"  Status: {r.status_code}")
print(f"  Body: {r.text[:100]}")
