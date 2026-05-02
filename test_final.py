#!/usr/bin/env python
"""Direct healthz test - no Railway env."""
import sys
import os

# NO Railway env vars
os.environ.pop("RAILWAY_SERVICE_NAME", None)
os.environ.pop("DATABASE_URL", None)
os.environ.pop("REDIS_URL", None)

sys.path.insert(0, "c:/Users/sammm/Desktop/SignalRankAI")

# Directly import railway_main to trigger lifespan
import railway_main

# Get the mounted app
app = railway_main.app

# Test
from fastapi.testclient import TestClient
client = TestClient(app, raise_server_exceptions=False)

print("Testing healthz...")
r = client.get("/healthz")
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:200]}")
