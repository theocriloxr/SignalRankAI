from datetime import datetime

class TradeRecord:
    def __init__(self, signal):
        self.signal_id = signal["id"]
        self.symbol = signal["symbol"]
        self.entry = signal["entry"]
        self.stop = signal["stop"]
        self.target = signal["targets"]
        self.open_time = signal["timestamp"]
        self.close_time = None
        self.outcome = None  # "TP" | "SL"

open_trades_list = []

# Example: update outcomes on each candle close

def open_trades():
    return open_trades_list

def price_hit_tp(trade, market_data):
    # Implement logic to check if TP hit
    return False

def price_hit_sl(trade, market_data):
    # Implement logic to check if SL hit
    return False

def close_trade(trade, outcome):
    trade.close_time = datetime.utcnow()
    trade.outcome = outcome


def update_trade_outcomes(market_data):
    for trade in open_trades():
        if price_hit_tp(trade, market_data):
            close_trade(trade, "TP")
        elif price_hit_sl(trade, market_data):
            close_trade(trade, "SL")
