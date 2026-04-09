"""
Price validation and freshness checks for signal delivery.
Ensures signals are delivered with current market prices.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from core.tier_constants import MAX_SIGNAL_AGE_SECONDS, PRICE_DRIFT_TOLERANCE

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_asset_type(asset: str) -> str:
    """Determine asset type from symbol."""
    asset_upper = asset.upper()
    if asset_upper.endswith(('USDT', 'USDC', 'BUSD', 'BTC', 'ETH')):
        return 'crypto'
    if '/' in asset and len(asset) == 7:  # e.g., EUR/USD
        return 'fx'
    if asset_upper in ('GOLD', 'SILVER', 'OIL', 'XAUUSD'):
        return 'commodity'
    return 'stock'


def is_signal_fresh(signal: Dict, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Check if signal is fresh enough for delivery.
    
    Returns:
        Tuple of (is_fresh: bool, reason: str)
    """
    if current_time is None:
        current_time = _utcnow_naive()
    
    created_at = signal.get('created_at')
    if not created_at:
        # Hard reject unstamped signals: unknown age means unknown edge quality.
        return False, "No creation timestamp"
    
    # Handle both datetime objects and string timestamps
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            # Make naive if aware
            if created_at.tzinfo is not None:
                created_at = created_at.replace(tzinfo=None)
        except Exception as e:
            logger.warning(f"Failed to parse timestamp {created_at}: {e}")
            return False, f"Invalid timestamp format: {e}"
    
    # Calculate age
    age_seconds = (current_time - created_at).total_seconds()
    
    # Get max age for this asset type
    asset = signal.get('asset', '')
    asset_type = get_asset_type(asset)
    max_age = MAX_SIGNAL_AGE_SECONDS.get(asset_type, 300)
    
    if age_seconds > max_age:
        return False, f"Signal age {age_seconds:.0f}s exceeds max {max_age}s for {asset_type}"
    
    return True, f"Fresh ({age_seconds:.0f}s old)"


def validate_price_drift(signal: Dict, current_price: float) -> Tuple[bool, str, Optional[Dict]]:
    """
    Validate if current price hasn't drifted too far from signal entry.
    
    Returns:
        Tuple of (is_valid: bool, reason: str, updated_signal: Optional[Dict])
        If price has drifted, updated_signal contains recalculated values.
    """
    entry = signal.get('entry')
    if entry is None:
        return False, "No entry price in signal", None
    
    entry = float(entry)
    asset = signal.get('asset', '')
    asset_type = get_asset_type(asset)
    
    # Calculate drift percentage
    drift_pct = abs(current_price - entry) / entry
    max_drift = PRICE_DRIFT_TOLERANCE.get(asset_type, 0.005)
    
    if drift_pct <= max_drift:
        return True, f"Price drift {drift_pct*100:.2f}% within tolerance", None
    
    # Price has drifted - update signal with current price
    logger.info(f"Price drift {drift_pct*100:.2f}% exceeds {max_drift*100:.2f}% for {asset}, updating signal")
    
    updated_signal = signal.copy()
    updated_signal['entry'] = current_price
    updated_signal['original_entry'] = entry
    
    # Recalculate SL/TP proportionally
    direction = signal.get('direction', 'long').lower()
    stop_loss = float(signal.get('stop_loss', 0))
    
    if stop_loss > 0:
        # Calculate original distance from entry to SL
        sl_distance_pct = abs(entry - stop_loss) / entry
        
        # Apply same percentage distance to new entry
        if direction == 'long':
            updated_signal['stop_loss'] = current_price * (1 - sl_distance_pct)
        else:  # short
            updated_signal['stop_loss'] = current_price * (1 + sl_distance_pct)
    
    # Update take profit proportionally
    take_profit = signal.get('take_profit')
    if take_profit:
        try:
            # Handle both list and single value
            import json
            if isinstance(take_profit, str):
                tp_values = json.loads(take_profit)
            else:
                tp_values = take_profit
            
            if isinstance(tp_values, list) and tp_values:
                tp_original = float(tp_values[0])
                tp_distance_pct = abs(tp_original - entry) / entry
                
                if direction == 'long':
                    new_tp = current_price * (1 + tp_distance_pct)
                else:
                    new_tp = current_price * (1 - tp_distance_pct)
                
                updated_signal['take_profit'] = json.dumps([new_tp])
        except Exception as e:
            logger.warning(f"Failed to update take profit: {e}")
    
    return True, f"Price updated from {entry:.4f} to {current_price:.4f} (drift: {drift_pct*100:.2f}%)", updated_signal


def check_sl_tp_hit(signal: Dict, current_price: float) -> Tuple[bool, Optional[str]]:
    """
    Check if stop loss or take profit has been hit.
    
    Returns:
        Tuple of (should_skip: bool, reason: Optional[str])
        If True, signal should not be delivered.
    """
    direction = signal.get('direction', 'long').lower()
    entry = float(signal.get('entry', 0))
    stop_loss = float(signal.get('stop_loss', 0))
    
    # Check stop loss
    if stop_loss > 0:
        if direction == 'long' and current_price <= stop_loss:
            return True, f"Stop loss already hit (price: {current_price:.4f}, SL: {stop_loss:.4f})"
        elif direction == 'short' and current_price >= stop_loss:
            return True, f"Stop loss already hit (price: {current_price:.4f}, SL: {stop_loss:.4f})"
    
    # Check take profit
    take_profit = signal.get('take_profit')
    if take_profit:
        try:
            import json
            if isinstance(take_profit, str):
                tp_values = json.loads(take_profit)
            else:
                tp_values = take_profit
            
            if isinstance(tp_values, list) and tp_values:
                tp_price = float(tp_values[0])
                
                if direction == 'long' and current_price >= tp_price:
                    return True, f"Take profit already hit (price: {current_price:.4f}, TP: {tp_price:.4f})"
                elif direction == 'short' and current_price <= tp_price:
                    return True, f"Take profit already hit (price: {current_price:.4f}, TP: {tp_price:.4f})"
        except Exception as e:
            logger.warning(f"Failed to check take profit: {e}")
    
    return False, None


def get_current_price(asset: str) -> Optional[float]:
    """
    Fetch current market price for an asset.
    Avoids 1m candle pulls for simple spot checks.
    """
    try:
        import requests

        symbol = str(asset or "").upper().replace("/", "").strip()
        if not symbol:
            return None

        # Crypto fast path: direct ticker endpoint (no candle fetch).
        if symbol.endswith(("USDT", "USDC", "BUSD")):
            try:
                resp = requests.get(
                    "https://api.binance.com/api/v3/ticker/price",
                    params={"symbol": symbol},
                    timeout=4,
                )
                if resp.ok:
                    px = float((resp.json() or {}).get("price") or 0)
                    if px > 0:
                        return px
            except Exception:
                pass

            # CryptoCompare fallback
            try:
                base = symbol.replace("USDT", "").replace("USDC", "").replace("BUSD", "")
                resp = requests.get(
                    "https://min-api.cryptocompare.com/data/price",
                    params={"fsym": base, "tsyms": "USD,USDT"},
                    timeout=4,
                )
                if resp.ok:
                    data = resp.json() or {}
                    px = float(data.get("USDT") or data.get("USD") or 0)
                    if px > 0:
                        return px
            except Exception:
                pass

        # Non-crypto fallback: yfinance fast quote (no 1m history).
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            fast = getattr(ticker, "fast_info", None) or {}
            px = float(fast.get("lastPrice") or fast.get("regularMarketPrice") or 0)
            if px > 0:
                return px
            info = getattr(ticker, "info", None) or {}
            px = float(info.get("regularMarketPrice") or 0)
            if px > 0:
                return px
        except Exception:
            pass

        # Last-resort fallback keeps backward compatibility.
        from data.fetcher import get_candles
        candles = get_candles(symbol, '5m')
        if candles:
            return float((candles[-1] or {}).get('close') or 0)
    except Exception as e:
        logger.error(f"Failed to fetch current price for {asset}: {e}")
    
    return None


def enrich_signal_with_live_price(signal: Dict) -> Dict:
    """
    Enrich signal dict with current price, price distance, and age.
    
    Adds fields:
    - current_price: float or None
    - price_distance_pct: float (percentage from entry)
    - signal_age_seconds: float
    
    Returns:
        Enriched signal dict (copy of original)
    """
    enriched = signal.copy()
    
    # Add signal age
    created_at = signal.get('created_at')
    if created_at:
        try:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                if created_at.tzinfo is not None:
                    created_at = created_at.replace(tzinfo=None)
            
            age_seconds = (_utcnow_naive() - created_at).total_seconds()
            enriched['signal_age_seconds'] = age_seconds
        except Exception as e:
            logger.warning(f"Failed to calculate signal age: {e}")
            enriched['signal_age_seconds'] = None
    else:
        enriched['signal_age_seconds'] = None
    
    # Fetch and add current price
    asset = signal.get('asset')
    if asset:
        current_price = get_current_price(asset)
        enriched['current_price'] = current_price
        
        # Calculate price distance from entry
        entry = signal.get('entry')
        if current_price and entry:
            try:
                entry_float = float(entry)
                distance_pct = ((current_price - entry_float) / entry_float) * 100
                enriched['price_distance_pct'] = distance_pct
            except Exception as e:
                logger.warning(f"Failed to calculate price distance: {e}")
                enriched['price_distance_pct'] = None
        else:
            enriched['price_distance_pct'] = None
    else:
        enriched['current_price'] = None
        enriched['price_distance_pct'] = None
    
    return enriched


def is_signal_stale(signal: Dict) -> bool:
    """
    Comprehensive staleness check combining age and price movement.
    
    A signal is stale if:
    - Age exceeds MAX_SIGNAL_AGE_SECONDS for asset type
    - Price has moved past entry significantly (half of TP distance)
    - SL or TP already hit
    
    Returns:
        bool: True if stale, False if fresh
    """
    # Check age freshness
    is_fresh, _ = is_signal_fresh(signal)
    if not is_fresh:
        return True
    
    # Check if SL/TP hit
    asset = signal.get('asset')
    if asset:
        current_price = get_current_price(asset)
        if current_price:
            should_skip, _ = check_sl_tp_hit(signal, current_price)
            if should_skip:
                return True
            
            # Check if price moved past entry significantly
            entry = signal.get('entry')
            direction = signal.get('direction', 'long').lower()
            take_profit = signal.get('take_profit')
            
            if entry and take_profit:
                try:
                    entry_float = float(entry)
                    
                    # Parse TP
                    import json
                    if isinstance(take_profit, str):
                        tp_values = json.loads(take_profit)
                    else:
                        tp_values = take_profit
                    
                    if isinstance(tp_values, list) and tp_values:
                        tp_price = float(tp_values[0])
                        tp_distance = abs(tp_price - entry_float)
                        half_tp_distance = tp_distance / 2
                        
                        # For longs: stale if price > entry + half of TP distance
                        # For shorts: stale if price < entry - half of TP distance
                        if direction == 'long':
                            if current_price > (entry_float + half_tp_distance):
                                return True
                        else:  # short
                            if current_price < (entry_float - half_tp_distance):
                                return True
                except Exception as e:
                    logger.debug(f"Failed to check price movement: {e}")
    
    return False


def filter_stale_signals(signals: list) -> list:
    """
    Filter out stale signals from a list.
    
    Logs each filtered signal for debugging.
    
    Args:
        signals: List of signal dicts
    
    Returns:
        List of fresh signals
    """
    fresh_signals = []
    
    for sig in signals:
        if is_signal_stale(sig):
            sig_id = sig.get('signal_id') or sig.get('id', 'unknown')
            asset = sig.get('asset', 'unknown')
            
            # Get enrichment info for logging
            age_seconds = sig.get('signal_age_seconds')
            if age_seconds is None:
                created_at = sig.get('created_at')
                if created_at:
                    try:
                        if isinstance(created_at, str):
                            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            if created_at.tzinfo is not None:
                                created_at = created_at.replace(tzinfo=None)
                        age_seconds = (_utcnow_naive() - created_at).total_seconds()
                    except Exception:
                        age_seconds = 'unknown'
            
            price_moved = sig.get('price_distance_pct')
            if price_moved is None:
                price_moved = 'unknown'
            else:
                price_moved = f"{price_moved:.2f}%"
            
            logger.info(f"[freshness] signal {sig_id} filtered: age={age_seconds}s price_moved={price_moved} asset={asset}")
        else:
            fresh_signals.append(sig)
    
    return fresh_signals
