"""
SignalRankAI — Webhook Generator (PERFECTED)

Every live signal is simultaneously broadcast as a standardized JSON payload
to a configurable API webhook endpoint. This allows VIP clients to plug directly
into Cornix, PineConnector, or custom Python scripts.

Payload standards:
  - TradingView/PineConnector format (primary)
  - Cornix format (secondary)
  - SignalRankAI native format (full detail)

Security:
  - HMAC-SHA256 signature on every payload
  - X-SignalRank-Signature header
  - Timestamp in payload prevents replay attacks
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WEBHOOK_SECRET   = os.getenv("WEBHOOK_SECRET",   "").strip()
WEBHOOK_URL      = os.getenv("WEBHOOK_URL",       "").strip()
WEBHOOK_TIMEOUT  = int(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "10") or 10)
WEBHOOK_MAX_RETRY = int(os.getenv("WEBHOOK_MAX_RETRY", "3") or 3)


# ─── Payload builders ─────────────────────────────────────────────────────────

def _parse_tp_list(raw) -> List[float]:
    """Parse TP levels into a clean list of floats."""
    if raw is None:
        return []
    if isinstance(raw, (int, float)):
        return [float(raw)] if float(raw) > 0 else []
    if isinstance(raw, (list, tuple)):
        result = []
        for item in raw:
            try:
                v = float(item.get("price") if isinstance(item, dict) else item)
                if v > 0:
                    result.append(v)
            except Exception:
                continue
        return result
    if isinstance(raw, str):
        try:
            return _parse_tp_list(json.loads(raw))
        except Exception:
            try:
                return [float(raw)]
            except Exception:
                return []
    return []


def build_native_payload(signal: dict) -> dict:
    """
    Build the SignalRankAI native webhook payload (full detail).
    
    This is the canonical format — all fields, including ML scores and
    institutional concept tags.
    """
    tp_levels = _parse_tp_list(
        signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels")
    )

    payload = {
        "version": "1.0",
        "source":  "signalrankAI",
        "timestamp": int(time.time()),
        "signal_id": str(signal.get("signal_id") or ""),
        "asset":      str(signal.get("asset") or signal.get("symbol") or "").upper(),
        "direction":  str(signal.get("direction") or "long").lower(),
        "timeframe":  str(signal.get("timeframe") or "").lower(),
        "action":     "open",

        # Prices
        "entry":     float(signal.get("entry") or 0),
        "stop_loss": float(signal.get("stop_loss") or signal.get("stop") or 0),
        "tp1":       float(tp_levels[0]) if len(tp_levels) > 0 else None,
        "tp2":       float(tp_levels[1]) if len(tp_levels) > 1 else None,
        "tp3":       float(tp_levels[2]) if len(tp_levels) > 2 else None,
        "tp_levels": tp_levels,

        # Scoring
        "score":           float(signal.get("score") or signal.get("display_score") or 0),
        "rr_ratio":        float(signal.get("rr_ratio") or signal.get("rr_estimate") or 0),
        "ml_probability":  signal.get("ml_probability") or signal.get("ml_prob"),

        # Sub-scores
        "trend_score":     signal.get("trend_score"),
        "volume_score":    signal.get("volume_score"),
        "liquidity_score": signal.get("liquidity_score"),
        "ml_score":        signal.get("ml_score"),

        # Context
        "regime":        str(signal.get("regime") or ""),
        "strategy_name": str(signal.get("strategy_name") or signal.get("strategy") or ""),
        "strategy_group":str(signal.get("strategy_group") or ""),
        "htf_bias":      str(signal.get("htf_bias") or ""),
        "session":       str(signal.get("session") or ""),

        # Institutional concepts
        "has_order_block":     bool(signal.get("has_order_block")),
        "has_fvg":             bool(signal.get("has_fvg")),
        "has_liquidity_sweep": bool(signal.get("has_liquidity_sweep")),
        "has_bos":             bool(signal.get("has_bos")),
        "has_choch":           bool(signal.get("has_choch")),

        # Explainability
        "trade_logic":   str(signal.get("trade_logic") or signal.get("technical_reason") or ""),
        "invalidation":  str(signal.get("invalidation") or ""),
    }

    # Remove None values to keep payload clean
    return {k: v for k, v in payload.items() if v is not None and v != "" and v is not False}


def build_pinescript_payload(signal: dict) -> dict:
    """
    Build PineConnector-compatible alert payload.
    
    Format used by PineConnector MT4/MT5 bridge.
    
    Example:
        {"license_id": "xxx", "ticker": "BTCUSD", "action": "buy",
         "sl": 29000, "tp": 31000, "risk": 1}
    """
    tp_levels = _parse_tp_list(
        signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels")
    )
    direction = str(signal.get("direction") or "long").lower()
    action    = "buy" if direction in ("long", "buy") else "sell"

    return {
        "license_id": os.getenv("PINECONNECTOR_LICENSE_ID", ""),
        "ticker":     str(signal.get("asset") or "").upper(),
        "action":     action,
        "sl":         float(signal.get("stop_loss") or 0),
        "tp":         float(tp_levels[0]) if tp_levels else 0,
        "risk":       float(os.getenv("PINECONNECTOR_RISK_PCT", "1") or 1),
        "comment":    f"SignalRankAI|{str(signal.get('signal_id') or '')[:8]}",
    }


def build_cornix_payload(signal: dict) -> dict:
    """
    Build Cornix-compatible signal payload.
    
    Cornix format (simplified):
        {"symbol": "BTCUSDT", "side": "BUY", "entry": [...], "sl": ..., "tp": [...]}
    """
    tp_levels = _parse_tp_list(
        signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels")
    )
    direction = str(signal.get("direction") or "long").lower()
    side      = "BUY" if direction in ("long", "buy") else "SELL"
    entry     = float(signal.get("entry") or 0)

    # Cornix supports entry zone (±0.3%)
    entry_low  = round(entry * 0.997, 6) if entry else 0
    entry_high = round(entry * 1.003, 6) if entry else 0

    return {
        "symbol":    str(signal.get("asset") or "").upper(),
        "side":      side,
        "exchange":  "BINANCE",
        "entry":     [entry_low, entry_high] if entry else [entry],
        "sl":        float(signal.get("stop_loss") or 0),
        "tp":        tp_levels[:3],
        "leverage":  int(os.getenv("CORNIX_LEVERAGE", "1") or 1),
        "comment":   f"SignalRankAI score={float(signal.get('score') or 0):.0f}",
    }


def build_outcome_payload(signal_id: str, outcome: str, data: dict) -> dict:
    """
    Build webhook payload for signal outcome notifications (TP hit, SL hit, etc.).
    """
    return {
        "version":    "1.0",
        "source":     "signalrankAI",
        "timestamp":  int(time.time()),
        "type":       "outcome",
        "signal_id":  str(signal_id),
        "outcome":    str(outcome).upper(),
        "exit_price": float(data.get("exit_price") or data.get("tp_price") or 0),
        "r_multiple": data.get("r_multiple"),
        "percent":    data.get("percent"),
        "tp_number":  data.get("tp_number"),
        "be_stop":    bool(data.get("break_even_stop")),
    }


# ─── Signature ────────────────────────────────────────────────────────────────

def sign_payload(payload: dict) -> str:
    """
    Generate HMAC-SHA256 signature for a payload.
    
    Used in X-SignalRank-Signature header to allow receivers to verify
    the webhook came from a legitimate SignalRankAI instance.
    """
    if not WEBHOOK_SECRET:
        return ""
    try:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        sig  = hmac.new(
            WEBHOOK_SECRET.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={sig}"
    except Exception as exc:
        logger.debug("[webhook] sign_payload failed: %s", exc)
        return ""


# ─── HTTP dispatch ─────────────────────────────────────────────────────────────

async def dispatch_webhook(
    payload: dict,
    url: Optional[str] = None,
    *,
    retry: bool = True,
) -> bool:
    """
    Send a webhook payload to the configured endpoint.
    
    Returns True if delivery succeeded (2xx response).
    Retries up to WEBHOOK_MAX_RETRY times on failure.
    """
    target_url = url or WEBHOOK_URL
    if not target_url:
        logger.debug("[webhook] No WEBHOOK_URL configured — skipping dispatch")
        return False

    signature = sign_payload(payload)
    headers = {
        "Content-Type":         "application/json",
        "X-SignalRank-Signature": signature,
        "X-SignalRank-Version":  "1.0",
    }

    body = json.dumps(payload, default=str)
    max_attempts = WEBHOOK_MAX_RETRY if retry else 1

    for attempt in range(1, max_attempts + 1):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=float(WEBHOOK_TIMEOUT)) as client:
                resp = await client.post(target_url, content=body, headers=headers)

            if 200 <= resp.status_code < 300:
                logger.debug(
                    "[webhook] Dispatched %s → %d",
                    payload.get("signal_id", "")[:8],
                    resp.status_code,
                )
                return True
            else:
                logger.warning(
                    "[webhook] Non-2xx response: %d (attempt %d/%d)",
                    resp.status_code, attempt, max_attempts,
                )

        except Exception as exc:
            logger.debug("[webhook] Dispatch error (attempt %d/%d): %s", attempt, max_attempts, exc)

        if attempt < max_attempts:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff

    return False


async def broadcast_signal_webhook(signal: dict) -> bool:
    """
    Broadcast a new signal to all configured webhook endpoints.
    
    Sends:
      1. Native SignalRankAI payload to WEBHOOK_URL
      2. PineConnector payload to PINECONNECTOR_WEBHOOK_URL (if set)
      3. Cornix payload to CORNIX_WEBHOOK_URL (if set)
    
    Returns True if at least one webhook succeeded.
    """
    tasks = []

    # Native payload
    native_url = WEBHOOK_URL
    if native_url:
        native_payload = build_native_payload(signal)
        tasks.append(dispatch_webhook(native_payload, native_url))

    # PineConnector
    pine_url = os.getenv("PINECONNECTOR_WEBHOOK_URL", "").strip()
    if pine_url:
        pine_payload = build_pinescript_payload(signal)
        tasks.append(dispatch_webhook(pine_payload, pine_url))

    # Cornix
    cornix_url = os.getenv("CORNIX_WEBHOOK_URL", "").strip()
    if cornix_url:
        cornix_payload = build_cornix_payload(signal)
        tasks.append(dispatch_webhook(cornix_payload, cornix_url))

    if not tasks:
        return False

    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = any(r is True for r in results)

    if success:
        logger.info(
            "[webhook] Signal %s broadcast to %d/%d endpoints",
            str(signal.get("signal_id") or "")[:8],
            sum(1 for r in results if r is True),
            len(tasks),
        )

    return success


async def broadcast_outcome_webhook(signal_id: str, outcome: str, data: dict) -> bool:
    """Broadcast a signal outcome to the webhook endpoint."""
    if not WEBHOOK_URL:
        return False
    payload = build_outcome_payload(signal_id, outcome, data)
    return await dispatch_webhook(payload)


__all__ = [
    "build_native_payload",
    "build_pinescript_payload",
    "build_cornix_payload",
    "build_outcome_payload",
    "dispatch_webhook",
    "broadcast_signal_webhook",
    "broadcast_outcome_webhook",
    "sign_payload",
]