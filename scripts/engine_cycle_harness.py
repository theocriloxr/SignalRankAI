"""Run ONE real engine cycle (engine.core.main_loop) against an owned local PostgreSQL.

Local verification only: it refuses any database that is not a local test
database, and blocks every outbound connection at the socket layer, so no
provider, AI, Telegram, broker or payment host can be reached.

* synthetic candles (one 15m random walk, aggregated to 1h/4h) are seeded into
  the PostgreSQL candle cache, which the real data layer falls back to;
* only network edges are replaced: the live quote (the synthetic market's last
  price), the external AI reviewer (a fixed approval marked synthetic), the
  active-trade snapshot normally read from Redis (empty) and the Telegram Bot;
* the cycle stops when its batch is marked done, after waiting for the
  background delivery fan-out.

    APP_ENV=test DATABASE_URL=postgresql+asyncpg://user@127.0.0.1:PORT/xxx_test       python scripts/engine_cycle_harness.py out.json [seed] [trend] [vol]

Seed 2, trend 0.00012, vol 0.002 produced a stored and delivered signal on
1 Nov 2026; gates depend on the market session, so other runs may not.
"""
import json
import os
import random
import socket
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

OUT = sys.argv[1]
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 7
TREND = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0006
VOL = float(sys.argv[4]) if len(sys.argv) > 4 else 0.004
ASSET = os.environ.setdefault("CYCLE_ASSET", "ETHUSDT")
TFS = os.environ.setdefault("CRYPTO_TIMEFRAMES", "15m,1h,4h")
os.environ.setdefault("TRADABLE_ASSETS", ASSET)
os.environ.setdefault("ASSET_CLASSES_ENABLED", "crypto")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "unit-test-placeholder")
_url = os.environ.get("DATABASE_URL", "")
if os.environ.get("APP_ENV") != "test" or not any(h in _url for h in ("@127.0.0.1:", "@localhost:")) or "test" not in _url.rsplit("/", 1)[-1]:
    raise SystemExit("engine_cycle_harness: requires APP_ENV=test and a local *test* database")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

# --- network sandbox: loopback only -----------------------------------------
blocked: list[str] = []
_real_getaddrinfo, _real_connect = socket.getaddrinfo, socket.socket.connect


def _local(host) -> bool:
    return str(host) in {"127.0.0.1", "localhost", "::1", "0.0.0.0"} or str(host).startswith("127.")


def guarded_getaddrinfo(host, *a, **k):
    if not _local(host):
        blocked.append(str(host))
        raise socket.gaierror(socket.EAI_NONAME, f"network blocked in harness: {host}")
    return _real_getaddrinfo(host, *a, **k)


def guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if not _local(host):
        blocked.append(str(host))
        raise ConnectionRefusedError(f"network blocked in harness: {host}")
    return _real_connect(self, address)


socket.getaddrinfo = guarded_getaddrinfo
socket.socket.connect = guarded_connect

TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "24h": 86400, "1d": 86400}


_BASE: list[dict] = []


def _base_path() -> list[dict]:
    """One 15m price path (300 x 4h worth); every timeframe is aggregated from it."""
    if _BASE:
        return _BASE
    rng = random.Random(SEED)
    step = 900
    n = 300 * 16 + 16
    last_open = (int(time.time()) // step) * step  # the forming candle, as exchanges return it
    price = 2500.0
    for i in range(n):
        open_t = last_open - (n - 1 - i) * step
        o = price
        c = max(1.0, o * (1 + rng.gauss(TREND, VOL)))
        hi = max(o, c) * (1 + abs(rng.gauss(0, 0.0015)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, 0.0015)))
        _BASE.append({"t": open_t, "open": o, "high": hi, "low": lo, "close": c, "volume": rng.uniform(800, 1600)})
        price = c
    return _BASE


def synthetic(tf: str, n: int = 300) -> list[dict]:
    step = TF_SECONDS[tf]
    groups: dict[int, list[dict]] = {}
    for bar in _base_path():
        groups.setdefault(bar["t"] // step * step, []).append(bar)
    rows = []
    for open_t in sorted(groups)[-n:]:
        g = groups[open_t]
        rows.append({"open_time_ms": open_t * 1000, "close_time_ms": (open_t + step) * 1000 - 1, "open": g[0]["open"],
                     "high": max(b["high"] for b in g), "low": min(b["low"] for b in g), "close": g[-1]["close"],
                     "volume": sum(b["volume"] for b in g)})
    return rows


class StopCycle(BaseException):
    pass


def main() -> int:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    from sqlalchemy import text

    from utils.async_runner import run_sync

    async def seed() -> dict:
        from db.models import MarketCandle, Subscription, User
        from db.session import get_session

        async with get_session() as session:
            # Clear earlier harness runs for this asset (children first, found through the FK graph).
            ids = [r[0] for r in await session.execute(text("SELECT signal_id FROM signals WHERE asset=:a"), {"a": ASSET})]
            if ids:
                refs = (await session.execute(text(
                    "SELECT tc.table_name, kcu.column_name FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name=tc.constraint_name "
                    "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name=tc.constraint_name "
                    "WHERE tc.constraint_type='FOREIGN KEY' AND ccu.table_name='signals' AND ccu.column_name='signal_id'"))).all()
                for _ in range(3):  # tables that reference each other: retry in passes
                    for table, column in refs:
                        try:
                            async with session.begin_nested():
                                await session.execute(text(f'DELETE FROM "{table}" WHERE "{column}" = ANY(:ids)'), {"ids": ids})
                        except Exception:
                            pass
                await session.execute(text("DELETE FROM signals WHERE signal_id = ANY(:ids)"), {"ids": ids})
            await session.execute(text("DELETE FROM market_candles WHERE symbol=:s"), {"s": ASSET})
            last = {}
            for tf in TFS.split(","):
                rows = synthetic(tf)
                for r in rows:
                    session.add(MarketCandle(symbol=ASSET, timeframe=tf, is_final=r is not rows[-1],
                                             updated_at=datetime.now(timezone.utc).replace(tzinfo=None), **r))
                last[tf] = rows[-1]["close"]
            tid = 7_600_000_000 + random.randint(0, 9_999_999)
            user = User(telegram_user_id=tid, username=f"cycle-{tid}", tier="vip", timezone="UTC", accepted_terms=True)
            session.add(user)
            await session.flush()
            session.add(Subscription(user_id=user.id, tier="vip", status="active",
                                     expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)))
            await session.commit()
        return {"telegram_id": tid, "last_close": last}

    seeded = run_sync(seed(), timeout=60)

    import signalrank_telegram.bot as bot
    from engine import core

    sent: list[dict] = []

    class FakeBot:
        def __init__(self, *a, **k):
            pass

        async def send_message(self, chat_id=None, text=None, **k):
            sent.append({"chat_id": int(chat_id), "text": str(text)[:400]})
            return SimpleNamespace(message_id=900000 + len(sent), chat=SimpleNamespace(id=int(chat_id)))

        async def edit_message_text(self, *a, **k):
            return True

        async def edit_message_reply_markup(self, *a, **k):
            return True

    bot.Bot = FakeBot
    bot._require_telegram_token = lambda: "unit-test-placeholder"
    import telegram
    telegram.Bot = FakeBot

    harness_thread = threading.current_thread()
    stop: dict = {}

    class TimeProxy:
        def __getattr__(self, name):
            return getattr(time, name)

        def sleep(self, seconds):
            if threading.current_thread() is harness_thread:
                frame = sys._getframe(1)
                stop.update(line=frame.f_lineno, seconds=seconds)
                raise StopCycle()
            return time.sleep(seconds)

    core.time = TimeProxy()

    # The cycle hands delivery to the shared background loop; keep the futures to wait on them.
    import utils.async_runner as runner
    background: list = []
    _real_submit = runner.submit_background_coro

    def recording_submit(coro, *, label="background"):
        fut = _real_submit(coro, label=label)
        background.append((label, fut))
        return fut

    runner.submit_background_coro = recording_submit

    # Stop when the first batch is marked done (both the no-candidate and the delivery paths call it).
    from engine import cycle_queue
    _real_mark_done = cycle_queue.AssetCycleQueue.mark_done

    def mark_done_then_stop(self, *a, **k):
        _real_mark_done(self, *a, **k)
        if threading.current_thread() is harness_thread:
            stop.update(reason="batch_done", signals_generated=k.get("signals_generated"))
            raise StopCycle()

    cycle_queue.AssetCycleQueue.mark_done = mark_done_then_stop

    # Quote providers are a network edge: quote the synthetic market at its latest 15m close.
    import data.get_live_price as live_price
    import engine.stale_signal_validator as stale
    from data.provider_types import LivePriceFailure, LivePriceQuote

    market_price = float(seeded["last_close"].get("15m") or next(iter(seeded["last_close"].values())))

    async def synthetic_quote(symbol, timeout=5.0, **k):
        if str(symbol).upper() != ASSET:
            return LivePriceFailure(str(symbol), "harness", "not_quoted", retryable=False)
        now_s = time.time()
        return LivePriceQuote(ASSET, market_price, "harness", now_s, 1, asset_class="crypto", source_timestamp=now_s,
                              received_at=now_s, completed_at=now_s, market_status="open", session="continuous",
                              provider_health="healthy", quote_kind="bid_ask", bid=market_price * 0.9999,
                              ask=market_price * 1.0001)

    async def synthetic_price(symbol):
        return market_price if str(symbol).upper() == ASSET else None

    live_price.get_live_price_result = synthetic_quote
    stale._get_live_price_async = synthetic_price
    stale._get_secondary_price = synthetic_price

    # The external AI reviewer is a network edge: a fixed, clearly synthetic approval.
    import services.ai_review_router as ai_router

    async def synthetic_review(signal, candles=None, news_sentiment=None, **k):
        return {"ok": True, "provider": "harness", "model": "synthetic-approval", "latency_ms": 1,
                "data": {"score": 9.0, "approved": True, "confidence": 0.8, "risk_level": "medium",
                         "summary": "synthetic harness approval"}}

    ai_router.review_signal = synthetic_review

    # Redis stand-in for the one admission read that requires it: reachable, no open trades.
    from core.redis_state import state as _state
    _real_active = _state.get_active_trades_sync
    _state.get_active_trades_sync = lambda *, require_complete=False: {} if require_complete else _real_active()
    started = time.time()
    error = None
    try:
        core.main_loop(DRY_RUN=False)
    except StopCycle:
        pass
    except Exception as exc:  # noqa: BLE001
        error = "".join(traceback.format_exception(exc))[-4000:]
    background_results = []
    for label, fut in background:
        try:
            background_results.append({"label": label, "result": repr(fut.result(timeout=150))[:200]})
        except Exception as exc:  # noqa: BLE001
            background_results.append({"label": label, "error": f"{type(exc).__name__}: {exc}"[:300]})

    async def collect() -> dict:
        from db.session import get_session

        async with get_session() as session:
            signals = [dict(r._mapping) for r in await session.execute(text(
                "SELECT signal_id, asset, timeframe, direction, entry, stop_loss, take_profit, score, strategy_name, "
                "quality_gate_passed, created_at FROM signals WHERE asset=:a ORDER BY created_at DESC LIMIT 5"), {"a": ASSET})]
            deliveries = [dict(r._mapping) for r in await session.execute(text(
                "SELECT d.signal_id, d.delivery_state, d.sent_ok FROM signal_deliveries d JOIN signals s USING(signal_id) "
                "WHERE s.asset=:a"), {"a": ASSET})]
            decisions = []
            for table in ("signal_decisions", "signal_decision_log", "engine_decisions"):
                try:
                    rows = await session.execute(text(f"SELECT * FROM {table} ORDER BY 1 DESC LIMIT 20"))
                    decisions = [dict(r._mapping) for r in rows]
                    break
                except Exception:
                    await session.rollback()
            await session.rollback()
        return {"signals": signals, "deliveries": deliveries, "decisions_sample": decisions[:20]}

    db = run_sync(collect(), timeout=60)
    from core.redis_state import state

    cycle_state = None
    for key in ("engine:last_cycle", "engine:cycle_state", "engine_cycle_state"):
        try:
            cycle_state = state.get_sync(key)
            if cycle_state:
                break
        except Exception:
            pass
    result = {"asset": ASSET, "timeframes": TFS, "seed": SEED, "trend": TREND, "seeded": seeded,
              "stopped_at": stop, "seconds": round(time.time() - started, 1), "error": error,
              "blocked_hosts": sorted(set(blocked)), "telegram_sent": sent, "background": background_results, "cycle_state": cycle_state, **db}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, default=str)
    print(json.dumps({k: result[k] for k in ("stopped_at", "seconds", "error")}, default=str))
    print("signals", len(db["signals"]), "deliveries", len(db["deliveries"]), "sent", len(sent),
          "blocked_hosts", len(set(blocked)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
