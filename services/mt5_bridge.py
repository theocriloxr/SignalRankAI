"""
MT5 Bridge - MetaTrader 5 Integration Service

This module provides:
- Connection to MetaTrader 5 terminal via MT5 Python library
- Signal to order conversion and execution
- Multiple account support per user
- Trade sync back to paper ledger
- Real-time position monitoring

Usage:
    from services.mt5_bridge import MT5Bridge
    
    bridge = MT5Bridge()
    await bridge.connect(account_id)
    result = await bridge.execute_signal(signal)
    positions = await bridge.get_positions()
"""

import os
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import asyncio

logger = logging.getLogger("MT5Bridge")

# MT5 connection state
_mt5_connections: Dict[str, Any] = {}
_mt5_lock = asyncio.Lock()


@dataclass
class MT5Config:
    """MT5 connection configuration."""
    server: str = ""  # Broker server (e.g., "MetaQuotes-Demo")
    login: int = 0  # Account login number
    password: str = ""  # Account password
    platform: str = "MetaTrader 5"
    timeout: int = 30000  # Connection timeout ms
    max_retry: int = 3
    retry_delay: float = 2.0


@dataclass
class MT5Order:
    """MT5 order request."""
    symbol: str
    volume: float
    order_type: str  # "buy" or "sell"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    comment: str = ""
    magic: int = 234000  # Expert Advisor ID
    
    def to_mt5_type(self) -> int:
        """Convert to MT5 order type."""
        # MT5 constants
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        ORDER_TYPE_BUY_LIMIT = 2
        ORDER_TYPE_SELL_LIMIT = 3
        ORDER_TYPE_BUY_STOP = 4
        ORDER_TYPE_SELL_STOP = 5
        
        if self.order_type.lower() == "buy":
            if self.price:
                return ORDER_TYPE_BUY_STOP if self.stop_loss else ORDER_TYPE_BUY
            return ORDER_TYPE_BUY
        else:
            if self.price:
                return ORDER_TYPE_SELL_STOP if self.stop_loss else ORDER_TYPE_SELL
            return ORDER_TYPE_SELL


@dataclass
class MT5Position:
    """MT5 position."""
    ticket: int
    symbol: str
    volume: float
    type: str  # "buy" or "sell"
    entry_price: float
    current_price: float
    profit: float
    stop_loss: float
    take_profit: float
    comment: str
    open_time: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            "ticket": self.ticket,
            "symbol": self.symbol,
            "volume": self.volume,
            "type": self.type,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "profit": self.profit,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "comment": self.comment,
            "open_time": str(self.open_time) if self.open_time else None
        }


class MT5Bridge:
    """
    MetaTrader 5 Bridge for automated trading.
    
    Features:
    - Connect to multiple MT5 accounts
    - Execute signals as market/limit orders
    - Track positions in real-time
    - Sync with paper ledger
    """
    
    def __init__(self):
        self._initialized = False
        self._mt5 = None
        self._config: Dict[str, MT5Config] = {}
    
    async def initialize(self) -> bool:
        """Initialize MT5 library."""
        if self._initialized:
            return True
        
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
            initialized = mt5.initialize()
            
            if initialized:
                logger.info("[MT5] Initialized successfully")
                self._initialized = True
                return True
            else:
                error = mt5.last_error()
                logger.error(f"[MT5] Initialize failed: {error}")
                return False
                
        except ImportError:
            logger.warning("[MT5] MetaTrader5 library not installed")
            return False
        except Exception as e:
            logger.error(f"[MT5] Initialize error: {e}")
            return False
    
    async def connect(self, account_id: str, config: Optional[MT5Config] = None) -> bool:
        """
        Connect to MT5 account.
        
        Args:
            account_id: Unique account identifier
            config: MT5 configuration (uses env vars if not provided)
        """
        if not await self.initialize():
            return False
        
        # Use provided config or load from environment
        cfg = config or self._load_config(account_id)
        if not cfg.server or not cfg.login:
            logger.warning(f"[MT5] No config for account {account_id}")
            return False
        
        self._config[account_id] = cfg
        
        # Note: MT5 terminal connects on initialize(), not per-account
        # Account selection is done via login
        account_info = self._mt5.account_info()
        if account_info is None:
            logger.error(f"[MT5] No account info: {self._mt5.last_error()}")
            return False
        
        logger.info(f"[MT5] Connected to account: {account_info.login}")
        return True
    
    def _load_config(self, account_id: str) -> MT5Config:
        """Load config from environment."""
        return MT5Config(
            server=os.getenv(f"MT5_{account_id}_SERVER", ""),
            login=int(os.getenv(f"MT5_{account_id}_LOGIN", 0)),
            password=os.getenv(f"MT5_{account_id}_PASSWORD", ""),
            platform=os.getenv(f"MT5_{account_id}_PLATFORM", "MetaTrader 5"),
        )
    
    async def disconnect(self) -> None:
        """Disconnect from MT5."""
        if self._mt5 and self._initialized:
            self._mt5.shutdown()
            self._initialized = False
            logger.info("[MT5] Disconnected")
    
    async def execute_signal(
        self,
        signal: Dict[str, Any],
        account_id: str = "default"
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Execute signal as MT5 order.
        
        Args:
            signal: Signal dict with asset, direction, entry, stop_loss, take_profit
            account_id: MT5 account to use
            
        Returns:
            Tuple of (success, message, order_ticket)
        """
        if not await self.initialize():
            return False, "MT5 not initialized", None
        
        try:
            # Convert signal to MT5 order
            symbol = self._normalize_symbol(signal.get("asset", ""))
            volume = self._calculate_volume(signal)
            order_type = signal.get("direction", "long").lower()
            
            price = float(signal.get("entry") or 0)
            if price <= 0:
                # Get current price
                symbol_info = self._mt5.symbol_info(symbol)
                if symbol_info is None:
                    return False, f"Symbol {symbol} not found", None
                
                if order_type == "long":
                    price = symbol_info.ask
                else:
                    price = symbol_info.bid
            
            stop_loss = float(signal.get("stop_loss") or 0)
            take_profit = float(signal.get("take_profit") or signal.get("targets", [0])[0] if signal.get("targets") else 0)
            
            # Build order request
            order = MT5Order(
                symbol=symbol,
                volume=volume,
                order_type=order_type,
                price=price,
                stop_loss=stop_loss if stop_loss > 0 else None,
                take_profit=take_profit if take_profit > 0 else None,
                comment=f"SignalRank:{signal.get('signal_id', '')}"
            )
            
            # Send order
            result = self._mt5.order_send(
                {
                    "action": self._mt5.TRADE_ACTION_DEAL,
                    "symbol": order.symbol,
                    "volume": order.volume,
                    "type": order.to_mt5_type(),
                    "price": order.price,
                    "sl": order.stop_loss,
                    "tp": order.take_profit,
                    "comment": order.comment,
                    "magic": order.magic,
                }
            )
            
            # Check result
            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                error_msg = self._mt5.last_error()
                logger.error(f"[MT5] Order failed: {result.retcode} - {error_msg}")
                return False, f"Order rejected: {result.retcode}", None
            
            logger.info(f"[MT5] Order placed: ticket={result.order}")
            return True, "Order executed", result.order
            
        except Exception as e:
            logger.error(f"[MT5] Execute error: {e}")
            return False, str(e), None
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for MT5."""
        # MT5 uses different symbols for some assets
        symbol = symbol.upper().replace("/", "")
        
        # Handle common conversions
        conversions = {
            "BTCUSDT": "BTCUSDt",
            "ETHUSDT": "ETHUSDt",
            "XAUUSD": "GOLD",
            "XAGUSD": "SILVER",
        }
        
        return conversions.get(symbol, symbol)
    
    def _calculate_volume(self, signal: Dict[str, Any]) -> float:
        """Calculate lot size from signal."""
        # Get from signal or use default
        default_volume = 0.01  # Micro lots
        
        if signal.get("position_size"):
            try:
                return float(signal["position_size"])
            except (ValueError, TypeError):
                pass
        
        if signal.get("risk_pct"):
            # Calculate based on risk
            risk_pct = float(signal["risk_pct"])
            account_balance = 10000  # TODO: Get from account
            risk_amount = account_balance * (risk_pct / 100)
            
            # Get stop loss distance
            entry = float(signal.get("entry", 0))
            sl = float(signal.get("stop_loss", 0))
            
            if entry > 0 and sl > 0:
                sl_distance = abs(entry - sl)
                if sl_distance > 0:
                    return risk_amount / sl_distance
        
        return default_volume
    
    async def get_positions(self, account_id: str = "default") -> List[MT5Position]:
        """Get open positions."""
        if not await self.initialize():
            return []
        
        try:
            positions = self._mt5.positions()
            result = []
            
            for pos in positions:
                result.append(MT5Position(
                    ticket=pos.ticket,
                    symbol=pos.symbol,
                    volume=pos.volume,
                    type="buy" if pos.type == 0 else "sell",
                    entry_price=pos.price_open,
                    current_price=pos.price_current,
                    profit=pos.profit,
                    stop_loss=pos.sl,
                    take_profit=pos.tp,
                    comment=pos.comment,
                    open_time=pos.time
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"[MT5] Get positions error: {e}")
            return []
    
    async def close_position(self, ticket: int, volume: Optional[float] = None) -> Tuple[bool, str]:
        """Close position."""
        if not await self.initialize():
            return False, "MT5 not initialized"
        
        try:
            positions = self._mt5.positions(ticket=ticket)
            if not positions:
                return False, "Position not found"
            
            pos = positions[0]
            
            # Determine close volume
            close_volume = volume if volume else pos.volume
            
            # Opposite type to close
            close_type = 1 if pos.type == 0 else 0  # sell to close buy, buy to close sell
            
            result = self._mt5.order_send(
                {
                    "action": self._mt5.TRADE_ACTION_DEAL,
                    "symbol": pos.symbol,
                    "volume": close_volume,
                    "type": close_type,
                    "position": ticket,
                    "price": pos.price_current,
                    "comment": f"Close SignalRank:{ticket}",
                    "magic": 234000,
                }
            )
            
            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                return False, f"Close failed: {result.retcode}"
            
            return True, "Position closed"
            
        except Exception as e:
            logger.error(f"[MT5] Close error: {e}")
            return False, str(e)
    
    async def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Tuple[bool, str]:
        """Modify position SL/TP."""
        if not await self.initialize():
            return False, "MT5 not initialized"
        
        try:
            result = self._mt5.order_send(
                {
                    "action": self._mt5.TRADE_ACTION_SLTP,
                    "position": ticket,
                    "sl": stop_loss if stop_loss else 0,
                    "tp": take_profit if take_profit else 0,
                    "magic": 234000,
                }
            )
            
            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                return False, f"Modify failed: {result.retcode}"
            
            return True, "Position modified"
            
        except Exception as e:
            logger.error(f"[MT5] Modify error: {e}")
            return False, str(e)
    
    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account information."""
        if not await self.initialize():
            return None
        
        try:
            info = self._mt5.account_info()
            if info is None:
                return None
            
            return {
                "login": info.login,
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "free_margin": info.margin_free,
                "profit": info.profit,
                "currency": info.currency,
                "server": info.server,
            }
        except Exception as e:
            logger.error(f"[MT5] Account info error: {e}")
            return None


class MT5AccountManager:
    """Manage multiple MT5 accounts per user."""
    
    def __init__(self):
        self._accounts: Dict[str, MT5Bridge] = {}
    
    async def add_account(
        self,
        user_id: int,
        account_id: str,
        config: MT5Config
    ) -> bool:
        """Add MT5 account for user."""
        try:
            bridge = MT5Bridge()
            connected = await bridge.connect(account_id, config)
            
            if connected:
                self._accounts[f"{user_id}:{account_id}"] = bridge
                logger.info(f"[MT5] Account added: user={user_id} account={account_id}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"[MT5] Add account error: {e}")
            return False
    
    async def get_bridge(self, user_id: int, account_id: str = "default") -> Optional[MT5Bridge]:
        """Get MT5 bridge for user."""
        key = f"{user_id}:{account_id}"
        return self._accounts.get(key)
    
    async def remove_account(self, user_id: int, account_id: str = "default") -> None:
        """Remove MT5 account."""
        key = f"{user_id}:{account_id}"
        bridge = self._accounts.pop(key, None)
        if bridge:
            await bridge.disconnect()


# Default instances
mt5_bridge = MT5Bridge()
account_manager = MT5AccountManager()


# Convenience functions
async def execute_signal(signal: Dict[str, Any], account_id: str = "default") -> Tuple[bool, str, Optional[int]]:
    """Execute signal via MT5."""
    return await mt5_bridge.execute_signal(signal, account_id)


async def get_positions(account_id: str = "default") -> List[MT5Position]:
    """Get open positions."""
    return await mt5_bridge.get_positions(account_id)


if __name__ == "__main__":
    # Test
    import asyncio
    
    async def test():
        bridge = MT5Bridge()
        
        # Test init
        initialized = await bridge.initialize()
        print(f"Initialized: {initialized}")
        
        if initialized:
            # Get account info
            info = await bridge.get_account_info()
            print(f"Account: {info}")
            
            # Get positions
            positions = await bridge.get_positions()
            print(f"Positions: {len(positions)}")
    
    asyncio.run(test())
