"""
Type stubs for MetaTrader5 package.
This file provides type hints when the MT5 library is not installed.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Type aliases
OrderRequest = Dict[str, Any]


class MT5Constants:
    """MT5 constants."""
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 2
    TRADE_ACTION_SLTP = 5
    TRADE_RETCODE_DONE = 0
    TRADE_RETCODE_ERROR = 1


class MetaTrader5:
    """MT5 library stub."""
    
    # Constants
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 2
    TRADE_ACTION_SLTP = 5
    TRADE_RETCODE_DONE = 0
    TRADE_RETCODE_ERROR = 1
    
    @staticmethod
    def initialize() -> bool:
        """Initialize MT5."""
        return False
    
    @staticmethod
    def shutdown() -> bool:
        """Shutdown MT5."""
        return True
    
    @staticmethod
    def last_error() -> Tuple[int, str]:
        """Get last error."""
        return (0, "No error")
    
    @staticmethod
    def account_info() -> Optional["AccountInfo"]:
        """Get account info."""
        return None
    
    @staticmethod
    def positions(ticket: int = 0) -> List["Position"]:
        """Get positions."""
        return []
    
    @staticmethod
    def orders(ticket: int = 0) -> List["Order"]:
        """Get orders."""
        return []
    
    @staticmethod
    def symbol_info(symbol: str) -> Optional["SymbolInfo"]:
        """Get symbol info."""
        return None
    
    @staticmethod
    def order_send(request: OrderRequest) -> "TradeResult":
        """Send order."""
        return TradeResult(0, 0, 0, "")


@dataclass
class AccountInfo:
    """Account info stub."""
    login: int = 0
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    margin_free: float = 0.0
    profit: float = 0.0
    currency: str = "USD"
    server: str = ""


@dataclass
class Position:
    """Position stub."""
    ticket: int = 0
    symbol: str = ""
    volume: float = 0.0
    type: int = 0
    price_open: float = 0.0
    price_current: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    comment: str = ""
    time: Optional[datetime] = None


@dataclass
class Order:
    """Order stub."""
    ticket: int = 0
    symbol: str = ""
    volume: float = 0.0
    type: int = 0
    price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    comment: str = ""


@dataclass
class SymbolInfo:
    """Symbol info stub."""
    name: str = ""
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: float = 0.0
    digits: int = 5


@dataclass
class TradeResult:
    """Trade result stub."""
    retcode: int = 0
    order: int = 0
    deal: int = 0
    comment: str = ""


# For type checking
__all__ = [
    "MetaTrader5",
    "AccountInfo", 
    "Position",
    "Order",
    "SymbolInfo",
    "TradeResult",
]
