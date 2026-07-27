"""Secret-safe production health probe for SignalRankAI.

This command performs read-only checks.  It never prints connection strings,
tokens, hosts, response bodies, or exception messages that could contain
credentials.  A non-zero exit means the deployment must not be promoted.

Typical Railway invocation:

    python scripts/production_health.py --base-url https://service.example
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    ok: bool
    latency_ms: int
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_error(exc: BaseException) -> str:
    """Return only the exception type; exception text can embed secret URLs."""

    return f"error={type(exc).__name__}"


def _normalise_base_url(value: str) -> str:
    base = str(value or "").strip().rstrip("/")
    if not base:
        return ""
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    return base


def resolve_base_url(
    cli_value: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = os.environ if environ is None else environ
    if cli_value:
        return _normalise_base_url(cli_value)
    for name in (
        "APP_BASE_URL",
        "PUBLIC_BASE_URL",
        "RAILWAY_PUBLIC_DOMAIN",
        "RAILWAY_STATIC_URL",
        "WEBHOOK_DOMAIN",
    ):
        value = _normalise_base_url(env.get(name, ""))
        if value:
            return value
    return ""


def _http_get_json(url: str, timeout_seconds: float) -> tuple[int, dict[str, Any] | None]:
    req = request.Request(url=url, method="GET", headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            status = int(response.status)
            raw = response.read(64 * 1024)
    except error.HTTPError as exc:
        # Do not read or return the response body; it may contain diagnostics.
        return int(exc.code), None
    try:
        decoded = json.loads(raw.decode("utf-8", errors="replace"))
        return status, decoded if isinstance(decoded, dict) else None
    except (UnicodeError, ValueError):
        return status, None


def _accepted_endpoint_state(path: str, payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or "").strip().lower()
    if path == "/livez":
        return status in {"live", "ok", "healthy"}
    if path == "/readyz":
        # "degraded" is intentionally not ready.
        return status in {"ready", "ok", "healthy"}
    return status in {"ok", "healthy", "degraded"}


async def check_http_endpoint(
    base_url: str,
    path: str,
    *,
    timeout_seconds: float,
) -> HealthCheck:
    if not base_url:
        return HealthCheck(
            name=f"http:{path}",
            ok=False,
            latency_ms=0,
            detail="missing_base_url",
        )
    started = time.monotonic()
    try:
        status, payload = await asyncio.wait_for(
            asyncio.to_thread(
                _http_get_json,
                base_url.rstrip("/") + path,
                timeout_seconds,
            ),
            timeout=timeout_seconds + 1.0,
        )
        ok = status == 200 and _accepted_endpoint_state(path, payload)
        detail = f"status_code={status};status_contract={'ok' if ok else 'invalid'}"
    except Exception as exc:
        ok = False
        detail = _safe_error(exc)
    return HealthCheck(
        name=f"http:{path}",
        ok=ok,
        latency_ms=int((time.monotonic() - started) * 1_000),
        detail=detail,
    )


async def check_postgres(
    *,
    timeout_seconds: float,
    environ: Mapping[str, str] | None = None,
) -> HealthCheck:
    env = os.environ if environ is None else environ
    if not str(env.get("DATABASE_URL") or "").strip():
        return HealthCheck("postgres", False, 0, "missing_configuration")
    started = time.monotonic()
    try:
        from db.priority import DBPriority
        from db.session import get_session
        from sqlalchemy import text

        async def _query() -> bool:
            async with get_session(
                priority=DBPriority.INTERACTIVE,
                label="production_health",
                timeout_seconds=timeout_seconds,
            ) as session:
                value = (await session.execute(text("SELECT 1"))).scalar_one()
                return int(value) == 1

        ok = bool(await asyncio.wait_for(_query(), timeout=timeout_seconds))
        detail = "query=ok" if ok else "query=invalid"
    except Exception as exc:
        ok = False
        detail = _safe_error(exc)
    return HealthCheck(
        "postgres",
        ok,
        int((time.monotonic() - started) * 1_000),
        detail,
    )


async def check_redis_url(
    name: str,
    url: str,
    *,
    timeout_seconds: float,
) -> HealthCheck:
    if not str(url or "").strip():
        return HealthCheck(name, False, 0, "missing_configuration")
    started = time.monotonic()
    client = None
    try:
        import redis.asyncio as redis

        client = redis.from_url(
            url,
            decode_responses=True,
            max_connections=1,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )
        ok = bool(await asyncio.wait_for(client.ping(), timeout=timeout_seconds))
        detail = "ping=ok" if ok else "ping=invalid"
    except Exception as exc:
        ok = False
        detail = _safe_error(exc)
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass
    return HealthCheck(
        name,
        ok,
        int((time.monotonic() - started) * 1_000),
        detail,
    )


def check_redis_topology(environ: Mapping[str, str] | None = None) -> HealthCheck:
    env = os.environ if environ is None else environ
    state_url = str(env.get("STATE_REDIS_URL") or env.get("REDIS_URL") or "").strip()
    delivery_url = str(env.get("DELIVERY_REDIS_URL") or "").strip()
    require_distinct = str(
        env.get("REQUIRE_DISTINCT_DELIVERY_REDIS")
        or env.get("PRODUCTION_HEALTH_REQUIRE_DISTINCT_REDIS")
        or "1"
    ).strip().lower() in {"1", "true", "yes", "on"}
    configured = bool(state_url and delivery_url)
    distinct = bool(state_url and delivery_url and state_url != delivery_url)
    ok = configured and (distinct or not require_distinct)
    if not configured:
        detail = "state_and_delivery_redis_required"
    elif require_distinct and not distinct:
        detail = "delivery_redis_not_distinct"
    else:
        detail = "topology=ok"
    return HealthCheck("redis_topology", ok, 0, detail)


async def collect_health(
    *,
    base_url: str,
    timeout_seconds: float = 5.0,
    include_http: bool = True,
    include_dependencies: bool = True,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    checks: list[HealthCheck] = []
    if include_http:
        checks.extend(
            await asyncio.gather(
                *(
                    check_http_endpoint(
                        base_url,
                        path,
                        timeout_seconds=timeout_seconds,
                    )
                    for path in ("/livez", "/healthz", "/readyz")
                )
            )
        )
    if include_dependencies:
        state_url = str(env.get("STATE_REDIS_URL") or env.get("REDIS_URL") or "").strip()
        delivery_url = str(env.get("DELIVERY_REDIS_URL") or "").strip()
        dependency_checks = await asyncio.gather(
            check_postgres(timeout_seconds=timeout_seconds, environ=env),
            check_redis_url(
                "state_redis",
                state_url,
                timeout_seconds=timeout_seconds,
            ),
            check_redis_url(
                "delivery_redis",
                delivery_url,
                timeout_seconds=timeout_seconds,
            ),
        )
        checks.append(check_redis_topology(env))
        checks.extend(dependency_checks)

    failures = [item for item in checks if not item.ok]
    return {
        "ok": not failures and bool(checks),
        "summary": {
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "total": len(checks),
        },
        "checks": [item.as_dict() for item in checks],
    }


def _print_human(result: dict[str, Any]) -> None:
    for item in result["checks"]:
        state = "PASS" if item["ok"] else "FAIL"
        print(
            f"[{state}] {item['name']} latency_ms={item['latency_ms']} "
            f"detail={item['detail']}"
        )
    summary = result["summary"]
    print(
        f"overall={'PASS' if result['ok'] else 'FAIL'} "
        f"passed={summary['passed']} failed={summary['failed']} total={summary['total']}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only SignalRankAI production health probe")
    parser.add_argument("--base-url", default=None, help="Service base URL (never printed)")
    parser.add_argument("--timeout", type=float, default=5.0, help="Per-check timeout in seconds")
    parser.add_argument("--skip-http", action="store_true")
    parser.add_argument("--skip-dependencies", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timeout_seconds = min(30.0, max(0.5, float(args.timeout)))
    base_url = resolve_base_url(args.base_url)
    result = asyncio.run(
        collect_health(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            include_http=not args.skip_http,
            include_dependencies=not args.skip_dependencies,
        )
    )
    if args.json_output:
        print(json.dumps(result, sort_keys=True))
    else:
        _print_human(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
