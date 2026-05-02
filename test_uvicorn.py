#!/usr/bin/env python
"""Test uvicorn startup."""
import sys
sys.path.insert(0, "c:/Users/sammm/Desktop/SignalRankAI")

# Set required env vars to simulate Railway (but don't set DB/Redis)
import os
os.environ["RAILWAY_SERVICE_NAME"] = "test"
os.environ["PORT"] = "8000"

# Test that uvicorn can load the app without DATABASE_URL
from fastapi.testclient import TestClient
from railway_main import app

client = TestClient(app)
print("Routes in main app:", [r.path for r in app.routes])

# Test healthz
try:
    response = client.get("/healthz")
    print(f"healthz status: {response.status_code}")
    print(f"healthz body: {response.json()}")
except Exception as e:
    print(f"healthz error: {e}")
