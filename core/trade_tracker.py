import logging
from datetime import datetime, timezone
import yfinance as yf
import requests

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class TradeRecord:
    def __init__(self, signal):
        # Normalize common signal field names used across the codebase/tests
        self.signal_id = signal.get("id") or signal.get("signal_id")
        self.symbol = signal.get("symbol") or signal.get("asset")
        self.entry = signal.get("entry") or signal.get("price") or signal.get("entry_price")
        # stop can be provided as 'stop', 'stop_loss' or 'stopLoss'
        self.stop = signal.get("stop") or signal.get("stop_loss") or signal.get("stopLoss")
        # targets may be 'targets' (list) or 'take_profit' / 'take_profits' (single)
        t = signal.get("targets") or signal.get("targets_list") or signal.get("take_profit") or signal.get("take_profits") or signal.get("take_profit")
        self.target = t
        # Normalize direction to lowercase 'long' or 'short' (tests expect lowercase)
        self.direction = (signal.get("direction") or signal.get("side") or "long").lower()
        # Timestamp fallback
        self.open_time = signal.get("timestamp") or signal.get("created_at") or _utcnow_naive().isoformat()
        self.close_time = None
        self.outcome = None  # "TP" | "SL"
        self.signal = signal  # Keep reference to original signal
        # Helper: ensure targets list for easier checks
        if self.target is None:
            self.targets = []
        elif isinstance(self.target, list):
            self.targets = self.target
        else:
            # single numeric target
            try:
                self.targets = [float(self.target)]
            except Exception:
                self.targets = []
        # Track which targets have been hit (for partial TP handling)
        self.targets_hit = []

open_trades_list = []

def open_trades():
    return list(open_trades_list)

def _convert_symbol_for_yfinance(symbol):
    """Convert crypto symbols from Binance format to yfinance format."""
    try:
        from data.market_data import format_ticker
        return format_ticker(symbol, "yfinance")
    except Exception:
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}-USD"
        if symbol.endswith("USD"):
            return f"{symbol[:-3]}-USD"
        return symbol

def _get_current_price(symbol):
    """
    Fetch current price for a symbol.
    Primary: yfinance fast_info
    Fallback: Binance REST API for crypto
    """
    # Try yfinance first
    try:
        yf_symbol = _convert_symbol_for_yfinance(symbol)
        ticker = yf.Ticker(yf_symbol)
        fast_info = getattr(ticker, "fast_info", {}) or {}
        price = fast_info.get('lastPrice') or fast_info.get('last_price') or fast_info.get('regularMarketPrice')
        if price and price > 0:
            logger.debug(f"Got price for {symbol} ({yf_symbol}) from yfinance: {price}")
            return float(price)
        history = ticker.history(period="2d", interval="1m", auto_adjust=False)
        if history is not None and not history.empty:
            last_close = float(history["Close"].dropna().iloc[-1])
            if last_close > 0:
                logger.debug(f"Got price for {symbol} ({yf_symbol}) from yfinance history: {last_close}")
                return last_close
    except Exception as e:
        logger.debug(f"yfinance failed for {symbol}: {e}")
    
    # Fallback to Binance for crypto
    if symbol.endswith("USDT") or symbol.endswith("USD"):
        try:
            binance_symbol = symbol if symbol.endswith("USDT") else f"{symbol}T"
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={binance_symbol}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                price = float(data["price"])
                logger.debug(f"Got price for {symbol} from Binance: {price}")
                return price
        except Exception as e:
            logger.debug(f"Binance API failed for {symbol}: {e}")
    
    logger.warning(f"Could not fetch price for {symbol}")
    return None

def price_hit_tp(trade, market_data=None):
    """
    Check if take profit is hit.
    For LONG: TP hit when current price >= target
    For SHORT: TP hit when current price <= target
    """
    # Get current price from market_data or fetch it
    current_price = None
    if market_data and isinstance(market_data, dict) and "price" in market_data:
        current_price = market_data["price"]
    else:
        current_price = _get_current_price(trade.symbol)
    
    if current_price is None:
        return False
    
    # Use normalized targets list
    targets = getattr(trade, "targets", []) or []
    if not targets:
        return False
    direction = (getattr(trade, "direction", "long") or "long").lower()
    
    # Check if any target is hit
    any_hit = False
    for target in targets:
        if target is None:
            continue
        if direction == "long":
            if current_price >= target:
                logger.info(f"TP hit for {trade.symbol} LONG: price={current_price} >= target={target}")
                try:
                    if target not in trade.targets_hit:
                        trade.targets_hit.append(target)
                        any_hit = True
                except Exception:
                    pass
        elif direction == "short":
            if current_price <= target:
                logger.info(f"TP hit for {trade.symbol} SHORT: price={current_price} <= target={target}")
                try:
                    if target not in trade.targets_hit:
                        trade.targets_hit.append(target)
                        any_hit = True
                except Exception:
                    pass

    return any_hit

def price_hit_sl(trade, market_data=None):
    """
    Check if stop loss is hit.
    For LONG: SL hit when current price <= stop
    For SHORT: SL hit when current price >= stop
    """
    # Get current price from market_data or fetch it
    current_price = None
    if market_data and isinstance(market_data, dict) and "price" in market_data:
        current_price = market_data["price"]
    else:
        current_price = _get_current_price(trade.symbol)
    
    if current_price is None:
        return False
    
    # Normalize direction and stop
    direction = (getattr(trade, "direction", "LONG") or "LONG").upper()
    stop = getattr(trade, "stop", None)
    if stop is None:
        return False

    # Ensure numeric
    try:
        stop_val = float(stop)
    except Exception:
        return False

    if direction == "LONG":
        if current_price <= stop_val:
            logger.info(f"SL hit for {trade.symbol} LONG: price={current_price} <= stop={stop_val}")
            return True
    elif direction == "SHORT":
        if current_price >= stop_val:
            logger.info(f"SL hit for {trade.symbol} SHORT: price={current_price} >= stop={stop_val}")
            return True

    return False

def close_trade(trade: TradeRecord, outcome: str):
    trade.close_time = _utcnow_naive()
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
    """
    Update trade outcomes based on current market data.
    Closes trades that hit TP/SL and removes them from open_trades_list.
    """
    trades_to_remove = []

    for trade in open_trades():
        if price_hit_tp(trade, market_data):
            close_trade(trade, "TP")
            trades_to_remove.append(trade)
        elif price_hit_sl(trade, market_data):
            close_trade(trade, "SL")
            trades_to_remove.append(trade)

    closed = []
    # Remove closed trades from open_trades_list and collect for return
    for trade in trades_to_remove:
        if trade in open_trades_list:
            try:
                open_trades_list.remove(trade)
            except ValueError:
                pass
            logger.info(f"Removed closed trade {trade.signal_id} ({trade.outcome}) from open_trades_list")
        closed.append(trade)

    return closed
