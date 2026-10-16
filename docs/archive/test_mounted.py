#!/usr/bin/env python
"""Comprehensive healthz test."""
import sys
import os

# Simulate Railway startup
os.environ["PORT"] = "8002"
os.environ["RAILWAY_SERVICE_NAME"] = "signalrankai"

# Remove DB/Redis to test degraded response
for key in ("DATABASE_URL", "REDIS_URL", "DATABASE_PUBLIC_URL", "REDIS_PUBLIC_URL"):
    os.environ.pop(key, None)

sys.path.insert(0, "c:/Users/sammm/Desktop/SignalRankAI")

from fastapi.testclient import TestClient
from railway_main import app

print("=== Main app routes ===")
for route in app.routes:
    if hasattr(route, 'path'):
        print(f"  {route.path}")

print("\n=== Testing via TestClient ===")
client = TestClient(app, raise_server_exceptions=False)

# Test ALL possible health endpoints
for path in ["/health", "/healthz", "/", ""]:
    resp = client.get(path)
    print(f"GET {path}: {resp.status_code} - {resp.json if resp.status_code == 200 else resp.text[:100]}")

# Check if web.app is mounted
print("\n=== Checking mount ===")
for route in app.routes:
    if hasattr(route, 'app'):
        print(f"Mounted at {route.path}: {route.app}")
    if hasattr(route, 'mount'):
        print(f"Mount: {route.path}")
