from __future__ import annotations

from datetime import datetime, timedelta

from strategies.imp import institutional_momentum_pulse_strategies


def _candle(ts: datetime, o: float, h: float, l: float, c: float, v: float = 1000.0) -> dict:
    return {
        "timestamp": int(ts.timestamp() * 1000),
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "volume": float(v),
    }


def _build_h4_uptrend() -> list[dict]:
    now = datetime.utcnow()
    out: list[dict] = []
    price = 100.0
    for i in range(240):
        ts = now - timedelta(hours=(240 - i) * 4)
        o = price
        c = price + 0.15
        h = c + 0.12
        l = o - 0.12
        out.append(_candle(ts, o, h, l, c, 1200.0))
        price = c
    return out


def _build_h1_imp_long_setup() -> list[dict]:
    now = datetime.utcnow()
    out: list[dict] = []
    close = 132.0
    # Structured drift down toward EMA50 area.
    for i in range(118):
        ts = now - timedelta(hours=(120 - i))
        o = close
        close = close - 0.03
        c = close
        h = max(o, c) + 0.08
        l = min(o, c) - 0.08
        out.append(_candle(ts, o, h, l, c, 1100.0 + i))

    # Candle -2 bearish body.
    prev_ts = now - timedelta(hours=2)
    out.append(_candle(prev_ts, 128.30, 128.40, 127.95, 128.00, 2500.0))

    # Candle -1 bullish engulfing touching EMA zone with stronger volume.
    cur_ts = now - timedelta(hours=1)
    out.append(_candle(cur_ts, 127.96, 129.30, 127.90, 129.15, 5000.0))
    return out


def test_imp_generates_long_signal_on_valid_setup(monkeypatch):
    monkeypatch.setenv("IMP_FX_OVERLAP_ONLY", "0")

    h4_candles = _build_h4_uptrend()
    h1_candles = _build_h1_imp_long_setup()

    market_data = {
        "4h": {
            "candles": h4_candles,
            "indicators": {
                "ema_200": 118.0,
            },
        },
        "1h": {
            "candles": h1_candles,
            "indicators": {
                "ema_50": 128.05,
                "atr": 0.28,
                "rsi": 53.0,
            },
        },
    }

    out = institutional_momentum_pulse_strategies("EURUSD", market_data)
    assert out
    sig = out[0]
    assert sig["direction"] == "LONG"
    assert sig["timeframe"] == "1h"
    assert float(sig["rr_ratio"]) >= 1.5


def test_imp_blocks_fx_outside_overlap(monkeypatch):
    monkeypatch.setenv("IMP_FX_OVERLAP_ONLY", "1")
    monkeypatch.setattr("strategies.imp._utc_hour_now", lambda: 9)

    market_data = {
        "4h": {
            "candles": _build_h4_uptrend(),
            "indicators": {"ema_200": 118.0},
        },
        "1h": {
            "candles": _build_h1_imp_long_setup(),
            "indicators": {"ema_50": 128.05, "atr": 0.28, "rsi": 53.0},
        },
    }

    out = institutional_momentum_pulse_strategies("GBPUSD", market_data)
    assert out == []


def test_imp_allows_london_session_when_configured(monkeypatch):
    monkeypatch.setenv("IMP_FX_OVERLAP_ONLY", "0")
    monkeypatch.setenv("IMP_FX_ALLOWED_SESSIONS", "london")
    monkeypatch.setattr("strategies.imp._utc_hour_now", lambda: 9)

    market_data = {
        "4h": {
            "candles": _build_h4_uptrend(),
            "indicators": {"ema_200": 118.0},
        },
        "1h": {
            "candles": _build_h1_imp_long_setup(),
            "indicators": {"ema_50": 128.05, "atr": 0.28, "rsi": 53.0},
        },
    }

    out = institutional_momentum_pulse_strategies("GBPUSD", market_data)
    assert out
