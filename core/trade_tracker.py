import logging
from datetime import datetime
import yfinance as yf
import requests

logger = logging.getLogger(__name__)

class TradeRecord:
    def __init__(self, signal):
        self.signal_id = signal["id"]
        self.symbol = signal["symbol"]
        self.entry = signal["entry"]
        self.stop = signal["stop"]
        self.target = signal["targets"]
        self.direction = signal.get("direction", signal.get("side", "LONG")).upper()
        self.open_time = signal["timestamp"]
        self.close_time = None
        self.outcome = None  # "TP" | "SL"
        self.signal = signal  # Keep reference to original signal

open_trades_list = []

# Example: update outcomes on each candle close

def open_trades():
    return open_trades_list

def _convert_symbol_for_yfinance(symbol):
    """Convert crypto symbols from Binance format to yfinance format."""
    # BTCUSDT -> BTC-USD
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}-USD"
    elif symbol.endswith("USD"):
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
        price = ticker.fast_info.get('lastPrice')
        if price and price > 0:
            logger.debug(f"Got price for {symbol} ({yf_symbol}) from yfinance: {price}")
            return float(price)
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

def price_hit_tp(trade, market_data):
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
    
    # Handle targets - can be a single value or list
    targets = trade.target
    if not isinstance(targets, list):
        targets = [targets]
    
    # Get trade direction
    direction = trade.direction
    
    # Check if any target is hit
    for target in targets:
        if direction == "LONG":
            if current_price >= target:
                logger.info(f"TP hit for {trade.symbol} LONG: price={current_price} >= target={target}")
                return True
        elif direction == "SHORT":
            if current_price <= target:
                logger.info(f"TP hit for {trade.symbol} SHORT: price={current_price} <= target={target}")
                return True
    
    return False

def price_hit_sl(trade, market_data):
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
    
    # Get trade direction and stop loss
    direction = trade.direction
    stop = trade.stop
    
    # Check if stop loss is hit
    if direction == "LONG":
        if current_price <= stop:
            logger.info(f"SL hit for {trade.symbol} LONG: price={current_price} <= stop={stop}")
            return True
    elif direction == "SHORT":
        if current_price >= stop:
            logger.info(f"SL hit for {trade.symbol} SHORT: price={current_price} >= stop={stop}")
            return True
    
    return False

def close_trade(trade, outcome):
    trade.close_time = datetime.utcnow()
    trade.outcome = outcome


def update_trade_outcomes(market_data):
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
    
    # Remove closed trades from open_trades_list
    for trade in trades_to_remove:
        if trade in open_trades_list:
            open_trades_list.remove(trade)
            logger.info(f"Removed closed trade {trade.signal_id} ({trade.outcome}) from open_trades_list")
