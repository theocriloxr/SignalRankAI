#!/usr/bin/env python
"""Debug test - check mounted routes."""
import sys
import os

os.environ.pop("RAILWAY_SERVICE_NAME", None)
os.environ.pop("DATABASE_URL", None)

sys.path.insert(0, "c:/Users/sammm/Desktop/SignalRankAI")

# Import and inspect routes
import railway_main

app = railway_main.app

print("=== Main app routes ===")
for route in app.routes:
    if hasattr(route, 'path'):
        print(f"  {route.path}")

print("\n=== Mounted app routes ===")
# Access the mounted app
for route in app.routes:
    if hasattr(route, 'app'):
        mounted = route.app
        print(f"  Mount: {getattr(mounted, 'title', 'unknown')}")
        if hasattr(mounted, 'routes'):
            for r in mounted.routes:
                if hasattr(r, 'path'):
                    print(f"    {r.path}")
        else:
            print(f"    mounted app has no routes (type={type(mounted)})")
