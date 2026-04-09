from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass
class CheckResult:
    name: str
    ok: bool
    status_code: int
    detail: str
    latency_ms: int


def _derive_base_url(cli_base: str | None) -> str:
    if cli_base:
        return cli_base.rstrip("/")
    for key in ("APP_BASE_URL", "WEBHOOK_URL", "RAILWAY_PUBLIC_DOMAIN"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            if raw.startswith("http://") or raw.startswith("https://"):
                return raw.rstrip("/")
            return f"https://{raw.strip('/')}"
    raise ValueError("No base URL provided. Pass --base-url or set APP_BASE_URL/WEBHOOK_URL/RAILWAY_PUBLIC_DOMAIN.")


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout_s: int = 15,
) -> tuple[int, dict[str, Any] | None, str, int]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url=url, data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            latency = int((time.monotonic() - started) * 1000)
            parsed = None
            try:
                parsed = json.loads(body) if body else None
            except Exception:
                parsed = None
            return int(resp.status), parsed, body[:500], latency
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        latency = int((time.monotonic() - started) * 1000)
        parsed = None
        try:
            parsed = json.loads(body) if body else None
        except Exception:
            parsed = None
        return int(exc.code), parsed, body[:500], latency


def _check_health(base: str) -> CheckResult:
    status, body, raw, latency = _http_json("GET", f"{base}/health")
    ok = status == 200 and isinstance(body, dict) and body.get("status") in {"ok", "degraded"}
    detail = f"status={status} body_status={(body or {}).get('status')}"
    if not ok:
        detail = f"{detail} raw={raw}"
    return CheckResult("health", ok, status, detail, latency)


def _check_ready(base: str) -> CheckResult:
    status, body, raw, latency = _http_json("GET", f"{base}/ready")
    ok = status == 200 and isinstance(body, dict) and body.get("status") in {"ok", "degraded"}
    detail = f"status={status} body_status={(body or {}).get('status')}"
    if not ok:
        detail = f"{detail} raw={raw}"
    return CheckResult("ready", ok, status, detail, latency)


def _check_broker_permission_policy(base: str) -> CheckResult:
    status, body, raw, latency = _http_json(
        "POST",
        f"{base}/broker/validate-api-permissions",
        payload={
            "provider": "bybit",
            "trade": True,
            "read": True,
            "permissions": ["trade", "read", "transfer"],
        },
    )
    ok = status == 400 and isinstance(body, dict) and body.get("policy") == "trade_only_required"
    detail = f"status={status} policy={(body or {}).get('policy')}"
    if not ok:
        detail = f"{detail} raw={raw}"
    return CheckResult("broker_permission_policy", ok, status, detail, latency)


def _check_webhook_enqueue(base: str) -> CheckResult:
    status, body, raw, latency = _http_json(
        "POST",
        f"{base}/telegram/webhook",
        payload={"update_id": int(time.time()), "message": {"text": "smoke"}},
    )
    ok = status == 200 and isinstance(body, dict) and bool(body.get("ok"))
    backend = (body or {}).get("queue_backend")
    detail = f"status={status} queued_ok={bool((body or {}).get('ok'))} queue_backend={backend}"
    if not ok:
        detail = f"{detail} raw={raw}"
    return CheckResult("webhook_enqueue", ok, status, detail, latency)


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-deploy smoke tests for SignalRankAI")
    parser.add_argument("--base-url", default=None, help="Public base URL, e.g. https://signalrankai.up.railway.app")
    parser.add_argument("--skip-webhook", action="store_true", help="Skip webhook enqueue test")
    args = parser.parse_args()

    try:
        base = _derive_base_url(args.base_url)
    except Exception as exc:
        print(f"[smoke] ERROR: {exc}")
        return 2

    checks: list[CheckResult] = []
    checks.append(_check_health(base))
    checks.append(_check_ready(base))
    checks.append(_check_broker_permission_policy(base))
    if not args.skip_webhook:
        checks.append(_check_webhook_enqueue(base))

    print(f"[smoke] base_url={base}")
    failures = 0
    for item in checks:
        state = "PASS" if item.ok else "FAIL"
        print(
            f"[{state}] {item.name} code={item.status_code} latency_ms={item.latency_ms} detail={item.detail}"
        )
        if not item.ok:
            failures += 1

    if failures:
        print(f"[smoke] FAILED checks={failures}/{len(checks)}")
        return 1

    print(f"[smoke] ALL PASS checks={len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
