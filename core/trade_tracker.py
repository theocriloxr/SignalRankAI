from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class TradeRecord:
    def __init__(self, signal):
        self.signal_id = signal.get("id") or signal.get("signal_id")
        self.symbol = signal.get("symbol") or signal.get("asset")
        self.direction = (signal.get("direction") or "long").lower()
        self.entry = float(signal.get("entry") or 0)
        self.stop = float(signal.get("stop") or signal.get("stop_loss") or 0)
        # Support both single target and list of targets
        raw_target = signal.get("targets") or signal.get("take_profit")
        if isinstance(raw_target, list):
            self.targets = [float(t) for t in raw_target]
        elif raw_target is not None:
            self.targets = [float(raw_target)]
        else:
            self.targets = []
        self.targets_hit = []  # Track which TPs have been hit
        self.open_time = signal.get("timestamp") or datetime.utcnow().isoformat()
        self.close_time = None
        self.outcome = None  # "TP" | "SL" | "PARTIAL_TP"
        self.strategy_name = signal.get("strategy_name")

open_trades_list = []

def open_trades():
    return list(open_trades_list)

def _get_current_price(symbol: str) -> float | None:
    """Get real-time price using yfinance primary, Binance fallback."""
    # Import here to avoid circular imports
    try:
        from data.market_data import get_realtime_price
        price = get_realtime_price(symbol)
        if price and price > 0:
            return price
    except Exception:
        pass
    
    # Direct yfinance fallback
    try:
        import yfinance as yf
        # Try common symbol formats
        for fmt in [symbol, f"{symbol}-USD", symbol.replace("USDT", "-USD")]:
            try:
                ticker = yf.Ticker(fmt)
                price = ticker.fast_info.get('lastPrice')
                if price and price > 0:
                    return float(price)
            except Exception:
                continue
    except Exception:
        pass
    
    # Binance REST fallback for crypto
    try:
        import requests
        binance_symbol = symbol.upper().replace("/", "").replace("-", "")
        if not binance_symbol.endswith("USDT"):
            binance_symbol += "USDT"
        resp = requests.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={binance_symbol}",
            timeout=5
        )
        if resp.status_code == 200:
            return float(resp.json()["price"])
    except Exception:
        pass
    
    return None

def price_hit_tp(trade: TradeRecord, market_data=None) -> bool:
    """Check if any take-profit target has been hit."""
    price = _get_current_price(trade.symbol)
    if price is None or not trade.targets:
        return False
    
    remaining_targets = [t for t in trade.targets if t not in trade.targets_hit]
    if not remaining_targets:
        return False
    
    for target in remaining_targets:
        hit = False
        if trade.direction == "long":
            hit = price >= target
        else:  # short
            hit = price <= target
        
        if hit:
            trade.targets_hit.append(target)
            logger.info(f"TP hit for {trade.symbol}: target={target}, price={price}, direction={trade.direction}")
    
    # All targets hit = full TP
    if len(trade.targets_hit) >= len(trade.targets):
        return True
    # Some targets hit = partial TP (still return True to mark progress)
    if trade.targets_hit:
        return True
    return False

def price_hit_sl(trade: TradeRecord, market_data=None) -> bool:
    """Check if stop-loss has been hit."""
    if trade.stop <= 0:
        return False
    price = _get_current_price(trade.symbol)
    if price is None:
        return False
    
    if trade.direction == "long":
        hit = price <= trade.stop
    else:  # short
        hit = price >= trade.stop
    
    if hit:
        logger.info(f"SL hit for {trade.symbol}: stop={trade.stop}, price={price}, direction={trade.direction}")
    return hit

def close_trade(trade: TradeRecord, outcome: str):
    trade.close_time = datetime.utcnow()
    if trade.targets_hit and len(trade.targets_hit) < len(trade.targets):
        trade.outcome = "PARTIAL_TP"
    else:
        trade.outcome = outcome

def add_trade(signal: dict):
    """Add a new trade to track."""
    trade = TradeRecord(signal)
    open_trades_list.append(trade)
    logger.info(f"Trade opened: {trade.symbol} {trade.direction} entry={trade.entry}")
    return trade

def update_trade_outcomes(market_data=None):
    """Check all open trades and close those that hit TP or SL."""
    closed = []
    for trade in open_trades_list:
        if price_hit_tp(trade, market_data):
            close_trade(trade, "TP")
            closed.append(trade)
        elif price_hit_sl(trade, market_data):
            close_trade(trade, "SL")
            closed.append(trade)
    
    # Remove closed trades from open list
    for trade in closed:
        if trade in open_trades_list:
            open_trades_list.remove(trade)
    
    return closed
