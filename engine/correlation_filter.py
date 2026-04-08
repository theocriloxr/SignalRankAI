from __future__ import annotations

from typing import Any, Dict, List, Tuple


# Lightweight cluster map to prevent over-exposure on tightly coupled assets.
CRYPTO_CLUSTER_OVERRIDES: dict[str, str] = {
    "BTCUSDT": "cluster_btc_beta",
    "ETHUSDT": "cluster_btc_beta",
    "SOLUSDT": "cluster_btc_beta",
    "BNBUSDT": "cluster_btc_beta",
    "AVAXUSDT": "cluster_btc_beta",
    "MATICUSDT": "cluster_btc_beta",
    "POLUSDT": "cluster_btc_beta",
}


def _signal_asset(signal: Dict[str, Any]) -> str:
    return str(signal.get("asset") or signal.get("symbol") or "").upper().strip()


def _signal_timeframe(signal: Dict[str, Any]) -> str:
    return str(signal.get("timeframe") or "").lower().strip()


def _signal_score(signal: Dict[str, Any]) -> float:
    try:
        return float(signal.get("score") or 0.0)
    except Exception:
        return 0.0


def _cluster_for_symbol(symbol: str) -> str:
    s = str(symbol or "").upper().strip()
    if not s:
        return "cluster_unknown"

    mapped = CRYPTO_CLUSTER_OVERRIDES.get(s)
    if mapped:
        return mapped

    if s.endswith("USDT"):
        base = s[:-4]
        return f"cluster_crypto_{base[:3]}"

    if len(s) == 6:
        base = s[:3]
        quote = s[3:]
        return f"cluster_fx_{base}_{quote}"

    if ":" in s:
        return f"cluster_{s.split(':', 1)[0]}"

    return f"cluster_asset_{s[:6]}"


def cluster_key(signal: Dict[str, Any]) -> Tuple[str, str]:
    symbol = _signal_asset(signal)
    timeframe = _signal_timeframe(signal)
    return (_cluster_for_symbol(symbol), timeframe)


def select_best_per_cluster(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for signal in signals or []:
        key = cluster_key(signal)
        incumbent = best.get(key)
        if incumbent is None:
            best[key] = signal
            continue

        candidate_rank = (
            _signal_score(signal),
            float(signal.get("ml_probability") or 0.0),
        )
        incumbent_rank = (
            _signal_score(incumbent),
            float(incumbent.get("ml_probability") or 0.0),
        )
        if candidate_rank > incumbent_rank:
            best[key] = signal

    # Keep stable highest-first ordering for deterministic dispatch.
    return sorted(best.values(), key=_signal_score, reverse=True)
