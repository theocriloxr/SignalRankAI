"""Health endpoint used only by the isolated SignalRank clean-room test service.

The process starts only after the shell's compile/schema/test chain succeeds.
It refuses to run without SIGNALRANK_CLEANROOM=1 so it cannot accidentally
serve as a production application entrypoint.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


if str(os.getenv("SIGNALRANK_CLEANROOM") or "").strip() != "1":
    raise SystemExit("cleanroom_health_server_requires_SIGNALRANK_CLEANROOM=1")

port = int(os.getenv("PORT") or "8080")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path not in {"/", "/healthz"}:
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(
            {
                "status": "CLEANROOM_PASS",
                "commit": str(
                    os.getenv("RAILWAY_GIT_COMMIT_SHA")
                    or os.getenv("GIT_COMMIT_SHA")
                    or ""
                ),
            },
            sort_keys=True,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
