"""Collect live production evidence for launch-readiness claims.

This script is intentionally evidence-first:
- It never prints secrets.
- It does not place broker orders by default.
- It marks missing credentials/live access as SKIP/FAIL instead of pretending.
- It emits JSON so the readiness scorecard can be updated from proof, not vibes.

Typical Railway run:
    python scripts/live_production_evidence.py --days 30 --provider-smoke

Optional local run with a .env file:
    python scripts/live_production_evidence.py --env-file .env --days 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


WIN_STATUSES = {"tp", "tp1", "tp2", "tp3", "partial_tp"}
LOSS_STATUSES = {"sl"}
ASSET_CLASS_ALIASES = {
    "fx": "forex",
    "forex": "forex",
    "stock": "equity",
    "stocks": "equity",
    "equity": "equity",
    "index": "indices",
    "indices": "indices",
    "commodity": "commodity",
    "commodities": "commodity",
    "crypto": "crypto",
}


@dataclass
class Check:
    name: str
    ok: bool
    status: str
    detail: str
    data: dict[str, Any] | None = None


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _asset_class(asset: str) -> str:
    try:
        from data.fetcher import get_asset_type

        cls = str(get_asset_type(asset) or "").strip().lower()
    except Exception:
        cls = ""
    if not cls:
        sym = str(asset or "").upper()
        if sym.endswith(("USDT", "USDC", "BTC", "ETH")):
            cls = "crypto"
        elif len(sym) == 6 and sym.isalpha():
            cls = "forex"
        elif sym in {"SPY", "QQQ", "DIA", "IWM", "US500", "NAS100", "DJI"}:
            cls = "indices"
        elif sym.startswith(("XAU", "XAG", "WTI", "BRENT")):
            cls = "commodity"
        else:
            cls = "equity"
    return ASSET_CLASS_ALIASES.get(cls, cls or "unknown")


def _wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = wins / total
    denom = 1.0 + (z * z / total)
    centre = p + (z * z / (2 * total))
    margin = z * math.sqrt((p * (1.0 - p) / total) + (z * z / (4 * total * total)))
    return max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom)


def check_environment() -> Check:
    required = ["DATABASE_URL", "TELEGRAM_BOT_TOKEN", "OWNER_IDS", "ENCRYPTION_KEY"]
    redis_ok = bool(os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL"))
    missing = [key for key in required if not os.getenv(key)]
    if not redis_ok:
        missing.append("REDIS_URL or REDIS_PRIVATE_URL")
    provider_keys = {
        "polygon": bool(os.getenv("POLYGON_API_KEY")),
        "twelvedata": bool(os.getenv("TWELVEDATA_API_KEY")),
        "alphavantage": bool(os.getenv("ALPHAVANTAGE_API_KEY")),
        "fmp": bool(os.getenv("FMP_API_KEY")),
        "binance": True,
        "bybit": True,
    }
    return Check(
        name="environment",
        ok=not missing,
        status="PASS" if not missing else "FAIL",
        detail="required Railway env present" if not missing else "missing=" + ",".join(missing),
        data={"providers_configured": provider_keys},
    )


async def check_postgres() -> Check:
    try:
        from db.session import get_session
        from sqlalchemy import text

        async with get_session() as session:
            row = (await session.execute(text("SELECT 1"))).first()
            delivery_row = (await session.execute(text("SELECT COUNT(*) FROM signal_deliveries"))).first()
            signal_row = (await session.execute(text("SELECT COUNT(*) FROM signals"))).first()
            await session.commit()
        return Check(
            name="postgres",
            ok=bool(row and row[0] == 1),
            status="PASS",
            detail="Postgres query succeeded",
            data={
                "signals": int(signal_row[0] or 0) if signal_row else 0,
                "signal_deliveries": int(delivery_row[0] or 0) if delivery_row else 0,
            },
        )
    except Exception as exc:
        return Check(name="postgres", ok=False, status="FAIL", detail=type(exc).__name__ + ": " + str(exc)[:300])


async def check_redis() -> Check:
    redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL")
    if not redis_url:
        return Check(name="redis", ok=False, status="FAIL", detail="REDIS_URL/REDIS_PRIVATE_URL not configured")
    try:
        import redis.asyncio as redis

        client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
        key = "signalrank:live_evidence:ping"
        await client.set(key, "1", ex=60)
        value = await client.get(key)
        await client.aclose()
        return Check(name="redis", ok=value == "1", status="PASS" if value == "1" else "FAIL", detail="Redis read/write succeeded")
    except Exception as exc:
        return Check(name="redis", ok=False, status="FAIL", detail=type(exc).__name__ + ": " + str(exc)[:300])


async def check_health_url() -> Check:
    base = (
        os.getenv("PUBLIC_BASE_URL")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("RAILWAY_STATIC_URL")
        or ""
    ).strip()
    if not base:
        return Check(name="railway_health_url", ok=False, status="SKIP", detail="PUBLIC_BASE_URL/RAILWAY_PUBLIC_DOMAIN not configured")
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    url = base.rstrip("/") + "/health"
    try:
        import requests

        res = await asyncio.to_thread(requests.get, url, timeout=10)
        ok = 200 <= int(res.status_code) < 300
        body: dict[str, Any]
        try:
            body = dict(res.json())
        except Exception:
            body = {"text": res.text[:300]}
        return Check(
            name="railway_health_url",
            ok=ok,
            status="PASS" if ok else "FAIL",
            detail=f"GET /health status={res.status_code}",
            data={"url": url, "body": body},
        )
    except Exception as exc:
        return Check(name="railway_health_url", ok=False, status="FAIL", detail=type(exc).__name__ + ": " + str(exc)[:300], data={"url": url})


async def check_outcome_coverage(days: int, min_coverage: float, min_tracked: int) -> Check:
    try:
        from db.session import get_session
        from sqlalchemy import text

        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, int(days)))
        query = text(
            """
            SELECT s.asset, o.status, COUNT(d.id) AS deliveries
            FROM signal_deliveries d
            JOIN signals s ON s.signal_id = d.signal_id
            LEFT JOIN outcomes o ON o.signal_id = d.signal_id
            WHERE d.delivered_at >= :since
              AND d.sent_ok IS TRUE
            GROUP BY s.asset, o.status
            """
        )
        async with get_session() as session:
            rows = (await session.execute(query, {"since": since})).fetchall()
            await session.commit()

        delivered = 0
        wins = 0
        losses = 0
        by_class: dict[str, dict[str, int]] = {}
        for asset, status, count in rows:
            n = int(count or 0)
            delivered += n
            cls = _asset_class(str(asset or ""))
            item = by_class.setdefault(cls, {"delivered": 0, "wins": 0, "losses": 0, "tracked": 0})
            item["delivered"] += n
            status_l = str(status or "").strip().lower()
            if status_l in WIN_STATUSES:
                wins += n
                item["wins"] += n
                item["tracked"] += n
            elif status_l in LOSS_STATUSES:
                losses += n
                item["losses"] += n
                item["tracked"] += n

        tracked = wins + losses
        coverage = (tracked / delivered) if delivered > 0 else 0.0
        win_rate = (wins / tracked) if tracked > 0 else 0.0
        low, high = _wilson_interval(wins, tracked)
        reliable = delivered > 0 and tracked >= int(min_tracked) and coverage >= float(min_coverage)
        detail = (
            f"delivered={delivered} tracked={tracked} coverage={coverage:.2%} "
            f"win_rate={win_rate:.2%} wilson95=[{low:.2%},{high:.2%}]"
        )
        return Check(
            name="outcome_coverage_expected_win_rate",
            ok=bool(reliable),
            status="PASS" if reliable else "FAIL",
            detail=detail,
            data={
                "days": int(days),
                "delivered": delivered,
                "tracked": tracked,
                "coverage_pct": round(coverage * 100.0, 3),
                "wins": wins,
                "losses": losses,
                "observed_win_rate_pct": round(win_rate * 100.0, 3),
                "wilson_95_low_pct": round(low * 100.0, 3),
                "wilson_95_high_pct": round(high * 100.0, 3),
                "expected_win_rate_reliable": bool(reliable),
                "by_asset_class": by_class,
            },
        )
    except Exception as exc:
        return Check(name="outcome_coverage_expected_win_rate", ok=False, status="FAIL", detail=type(exc).__name__ + ": " + str(exc)[:300])


async def check_provider_smoke(enabled: bool) -> Check:
    if not enabled:
        return Check(name="provider_ohlc_smoke", ok=False, status="SKIP", detail="run with --provider-smoke to call live OHLC providers")
    raw_assets = os.getenv(
        "LIVE_PROVIDER_SMOKE_ASSETS",
        "BTCUSDT:crypto,EURUSD:forex,XAUUSD:commodity,AAPL:equity,SPY:indices",
    )
    assets: list[tuple[str, str]] = []
    for item in raw_assets.split(","):
        if not item.strip():
            continue
        if ":" in item:
            symbol, cls = item.split(":", 1)
        else:
            symbol, cls = item, _asset_class(item)
        assets.append((symbol.strip().upper(), ASSET_CLASS_ALIASES.get(cls.strip().lower(), cls.strip().lower())))

    results: dict[str, Any] = {}
    ok_count = 0
    try:
        from data.fetcher import get_candles, is_market_open, market_closed_reason
    except Exception as exc:
        return Check(name="provider_ohlc_smoke", ok=False, status="FAIL", detail="fetcher import failed: " + str(exc)[:300])

    for symbol, expected_class in assets:
        started = time.perf_counter()
        try:
            open_now = bool(is_market_open(symbol))
        except Exception:
            open_now = True
        if not open_now and expected_class != "crypto":
            try:
                reason = str(market_closed_reason(symbol))
            except Exception:
                reason = "market closed"
            results[symbol] = {"ok": True, "skipped_fetch": True, "asset_class": expected_class, "reason": reason}
            ok_count += 1
            continue
        try:
            candles = await asyncio.wait_for(asyncio.to_thread(get_candles, symbol, "1h"), timeout=30)
            count = len(candles or [])
            sample = candles[-1] if candles else None
            ok = count >= 20 and isinstance(sample, dict) and float(sample.get("close", 0) or 0) > 0
            if ok:
                ok_count += 1
            results[symbol] = {
                "ok": ok,
                "asset_class": expected_class,
                "candles": count,
                "elapsed_s": round(time.perf_counter() - started, 3),
                "last_close_present": bool(sample and sample.get("close")),
            }
        except Exception as exc:
            results[symbol] = {
                "ok": False,
                "asset_class": expected_class,
                "error": type(exc).__name__ + ": " + str(exc)[:240],
            }

    all_ok = ok_count == len(assets) and bool(assets)
    return Check(
        name="provider_ohlc_smoke",
        ok=all_ok,
        status="PASS" if all_ok else "FAIL",
        detail=f"{ok_count}/{len(assets)} asset-class OHLC checks passed",
        data=results,
    )


async def check_broker_sandbox() -> Check:
    """Check broker execution proof.

    This does not place an order unless BROKER_SANDBOX_ALLOW_ORDER is explicitly
    set to I_UNDERSTAND_THIS_PLACES_A_SANDBOX_ORDER. Without that, it checks
    link/status evidence only.
    """
    allow_order = os.getenv("BROKER_SANDBOX_ALLOW_ORDER") == "I_UNDERSTAND_THIS_PLACES_A_SANDBOX_ORDER"
    data: dict[str, Any] = {"order_attempted": False, "order_permission": bool(allow_order)}
    linked = False
    try:
        from db.session import get_session
        from sqlalchemy import text

        async with get_session() as session:
            mt5_row = (await session.execute(text("SELECT COUNT(*) FROM mt5_credentials"))).first()
            exchange_row = (
                await session.execute(
                    text("SELECT COUNT(*) FROM runtime_state WHERE key LIKE 'broker_exchange:%'")
                )
            ).first()
            await session.commit()
        mt5_count = int(mt5_row[0] or 0) if mt5_row else 0
        exchange_count = int(exchange_row[0] or 0) if exchange_row else 0
        linked = (mt5_count + exchange_count) > 0
        data.update({"mt5_credentials": mt5_count, "exchange_links": exchange_count})
    except Exception as exc:
        return Check(name="broker_sandbox_execution", ok=False, status="FAIL", detail="broker DB link check failed: " + str(exc)[:300], data=data)

    if not allow_order:
        return Check(
            name="broker_sandbox_execution",
            ok=False,
            status="SKIP" if linked else "FAIL",
            detail=(
                "broker link exists; order smoke skipped by safety flag"
                if linked
                else "no linked MT5/exchange broker credentials found"
            ),
            data=data,
        )

    # Keep order execution deliberately unimplemented here until a dedicated
    # sandbox account, symbol, size, and kill-switch policy are configured.
    return Check(
        name="broker_sandbox_execution",
        ok=False,
        status="FAIL",
        detail="order flag set, but no dedicated sandbox order adapter is configured in this script",
        data=data,
    )


async def collect(args: argparse.Namespace) -> dict[str, Any]:
    checks = [
        check_environment(),
        await check_postgres(),
        await check_redis(),
        await check_health_url(),
        await check_outcome_coverage(args.days, args.min_coverage, args.min_tracked),
        await check_provider_smoke(args.provider_smoke),
        await check_broker_sandbox(),
    ]
    pass_count = sum(1 for c in checks if c.status == "PASS")
    fail_count = sum(1 for c in checks if c.status == "FAIL")
    skip_count = sum(1 for c in checks if c.status == "SKIP")
    readiness_90_evidence = fail_count == 0 and skip_count == 0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "readiness_90_evidence": readiness_90_evidence,
        "summary": {"pass": pass_count, "fail": fail_count, "skip": skip_count},
        "checks": [asdict(c) for c in checks],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect live SignalRankAI production evidence.")
    parser.add_argument("--env-file", default=None, help="Optional .env file to load before checks.")
    parser.add_argument("--days", type=int, default=30, help="Outcome coverage lookback window.")
    parser.add_argument("--min-coverage", type=float, default=float(os.getenv("EXPECTED_WIN_RATE_MIN_COVERAGE", "0.80") or 0.80))
    parser.add_argument("--min-tracked", type=int, default=int(os.getenv("EXPECTED_WIN_RATE_MIN_TRACKED", "100") or 100))
    parser.add_argument("--provider-smoke", action="store_true", help="Call live OHLC providers for representative assets.")
    parser.add_argument("--json-out", default=None, help="Optional file path for JSON evidence output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _load_env_file(args.env_file)
    result = asyncio.run(collect(args))
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0 if result.get("readiness_90_evidence") else 1


if __name__ == "__main__":
    raise SystemExit(main())
