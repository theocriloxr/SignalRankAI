#!/usr/bin/env python
"""Diagnostic test simulating Railway startup."""
import sys
import os

# Simulate Railway env BEFORE any imports
os.environ["RAILWAY_SERVICE_NAME"] = "signalrankai"
os.environ["PORT"] = "8000"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("REDIS_URL", None)
os.environ.pop("DATABASE_PUBLIC_URL", None)
os.environ.pop("REDIS_PUBLIC_URL", None)

sys.path.insert(0, "c:/Users/sammm/Desktop/SignalRankAI")

print("=== Step 1: Import railway_main ===")
import railway_main

print("\n=== Step 2: Check app created ===")
app = railway_main.app
print(f"App: {app}")

print("\n=== Step 3: List routes ===")
routes = [r.path for r in app.routes]
print(f"Routes: {routes}")

print("\n=== Step 4: Test healthz endpoint ===")
from fastapi.testclient import TestClient
client = TestClient(app)
resp = client.get("/healthz")
print(f"Status: {resp.status_code}")
print(f"Body: {resp.json()}")

print("\n=== All tests passed! ===")
