"""
Webhook Generator for Auto-Execution (MT4/MT5/Cornix/PineConnector)

Generates JSON webhook payloads that users can plug into:
- Cornix (Crypto)
- PineConnector (Forex) 
- MT5 Bridges
"""

import json
import os
from typing import Any, Dict, List, Optional


def generate_webhook_payload(
    signal: Dict[str, Any],
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a webhook JSON payload for auto-execution.
    
    Args:
        signal: The signal dictionary
        
    Returns:
        JSON payload ready for webhook POST
        
    Example output for Cornix:
    {
        "action": "OPEN",
        "symbol": "BTCUSDT",
        "type": "BUY",
        "amount": 100,
        "leverage": 10,
        "stopLoss": 42000,
        "takeProfit": 45000,
    }
    """
    symbol = str(signal.get('asset') or signal.get('symbol') or '').upper()
    direction = str(signal.get('direction') or 'long').lower()
    entry = float(signal.get('entry') or 0)
    stop_loss = float(signal.get('stop_loss') or signal.get('stop') or 0)
    take_profit = signal.get('take_profit')
    
    # Handle take_profit as list or single value
    tp_levels = []
    if isinstance(take_profit, list):
        for tp in take_profit:
            try:
                tp_levels.append(float(tp))
            except (TypeError, ValueError):
                pass
    elif take_profit:
        try:
            tp_levels.append(float(take_profit))
        except (TypeError, ValueError):
            pass
    
    # Map direction to broker commands
    if direction == 'long':
        order_type = 'BUY'
        action = 'OPEN_LONG'
    else:
        order_type = 'SELL'
        action = 'OPEN_SHORT'
    
    # Build webhook payload
    payload = {
        # Common fields (Cornix, PineConnector)
        "action": action,
        "symbol": symbol,
        "type": order_type,
        "entry": entry,
        "stopLoss": stop_loss,
    }
    
    # Add take profit levels (TP1, TP2, TP3 for multi-tier)
    if tp_levels:
        if len(tp_levels) >= 1:
            payload["takeProfit1"] = tp_levels[0]
        if len(tp_levels) >= 2:
            payload["takeProfit2"] = tp_levels[1]
        if len(tp_levels) >= 3:
            payload["takeProfit3"] = tp_levels[2]
        # Also add as array for compatibility
        payload["takeProfit"] = tp_levels[0] if tp_levels else None
    
    # Add meta information
    payload["meta"] = {
        "signal_id": str(signal.get('signal_id') or ''),
        "timeframe": str(signal.get('timeframe') or ''),
        "strategy": str(signal.get('strategy_name') or ''),
        "score": float(signal.get('score') or 0),
        "confidence": float(signal.get('confidence') or 0),
    }
    
    # Add broker-specific fields
    # MT5 format
    payload["mt5"] = {
        "symbol": symbol,
        "volume": float(signal.get('position_size') or 0.01),
        "type": order_type,
        "price": entry,
        "sl": stop_loss,
        "tp": tp_levels[0] if tp_levels else None,
    }
    
    # PineConnector format (uses different field names)
    payload["pineconnector"] = {
        "symbol": symbol,
        "direction": direction.upper(),
        "entry": entry,
        "sl": stop_loss,
        "tp": ",".join(str(tp) for tp in tp_levels) if tp_levels else "",
    }
    
    return payload


def generate_webhook_urls(env_var: str = "WEBHOOK_URLS") -> List[str]:
    """
    Get webhook URLs from environment.
    
    Format: COMMA_SEPARATED_URLS
    e.g., "https://cornix.io/abc,https://pineconnector.com/xyz"
    """
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return []
    return [url.strip() for url in raw.split(",") if url.strip()]


async def send_webhook(
    payload: Dict[str, Any],
    webhook_url: str,
    timeout: float = 10.0,
) -> bool:
    """
    Send webhook payload to URL.
    
    Returns True if successful.
    """
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                return resp.status in (200, 201, 202)
    except Exception:
        return False


async def broadcast_webhooks(
    signal: Dict[str, Any],
) -> Dict[str, bool]:
    """
    Send signal to all configured webhook URLs.
    
    Returns: {webhook_url: success}
    """
    import asyncio
    
    webhook_urls = generate_webhook_urls()
    if not webhook_urls:
        return {}
    
    payload = generate_webhook_payload(signal)
    
    # Send to all URLs concurrently
    tasks = [send_webhook(payload, url) for url in webhook_urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return {
        url: bool(result) if not isinstance(result, Exception) else False
        for url, result in zip(webhook_urls, results)
    }
