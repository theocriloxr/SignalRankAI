#!/usr/bin/env python
"""Test exact healthz behavior."""
import sys
import os

os.environ["PORT"] = "8003"
os.environ["RAILWAY_SERVICE_NAME"] = "signalrankai"
for key in ("DATABASE_URL", "REDIS_URL", "DATABASE_PUBLIC_URL", "REDIS_PUBLIC_URL"):
    os.environ.pop(key, None)

sys.path.insert(0, "c:/Users/sammm/Desktop/SignalRankAI")

from fastapi.testclient import TestClient
from railway_main import app

client = TestClient(app, raise_server_exceptions=False)

print("=== Raw healthz response ===")
resp = client.get("/healthz")
print(f"Status code: {resp.status_code}")
print(f"Response text: {resp.text}")

# Check what Railway might see
json_resp = resp.json()
print(f"\nParsed JSON: {json_resp}")
print(f"Status field: {json_resp.get('status')}")

# Railway typically expects HTTP 200 for healthy, anything else is failure
if resp.status_code == 200:
    print("\n✅ PASS: Railway would see 200 (healthy/degraded)")
else:
    print(f"\n❌ FAIL: Railway would see {resp.status_code}")
