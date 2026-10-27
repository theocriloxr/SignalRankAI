#!/usr/bin/env python
"""Start uvicorn server for testing."""
import os
os.environ["PORT"] = "8001"
os.environ["RAILWAY_SERVICE_NAME"] = "signalrankai"

# Remove DB/Redis to test degraded healthz
for key in ("DATABASE_URL", "REDIS_URL", "DATABASE_PUBLIC_URL", "REDIS_PUBLIC_URL"):
    os.environ.pop(key, None)

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "railway_main:app",
        host="127.0.0.1",
        port=8001,
        log_level="info",
        reload=False,
    )
