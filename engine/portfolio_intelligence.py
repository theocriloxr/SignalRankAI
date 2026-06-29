"""
Portfolio Intelligence
Phase 4.1 - Risk Management & Position Tracking

Commands: /portfolio, /risk, /exposure
Shows: Crypto, Forex, Commodity Exposure, Total Risk
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Asset class groupings
ASSET_CLASSES = {
    'CRYPTO': ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'DOT', 'AVAX', 'MATIC', 'LINK', 'UNI', 'BNB'],
    'FOREX_MAJOR': ['EUR', 'USD', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD'],
    'FOREX_JPY': ['JPY', 'GBP/JPY', 'EUR/JPY', 'AUD/JPY', 'NZD/JPY', 'CAD/JPY'],
    'INDICES': ['US30', 'US500', 'NAS100', 'GER40', 'UK100', 'JPN225'],
    'COMMODITIES': ['XAU', 'XAG', 'OIL', 'NATGAS', 'COPPER'],
}


@dataclass
class Position:
    """Single trading position."""
    symbol: str
    asset_class: str
    direction: str  # 'long' or 'short'
    entry_price: float
    current_price: float
    volume: float
    stop_loss: float
    take_profit: float
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def pnl_pct(self) -> float:
        """Calculate PnL percentage."""
        if self.direction == 'long':
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100
    
    @property
    def pnl_pips(self) -> float:
        """Calculate PnL in pips."""
        if self.direction == 'long':
            return self.current_price - self.entry_price
        else:
            return self.entry_price - self.current_price
    
    @property
    def risk_reward(self) -> float:
        """Calculate current R:R ratio."""
        if self.direction == 'long':
            potential_loss = self.entry_price - self.stop_loss
            potential_gain = self.take_profit - self.entry_price
        else:
            potential_loss = self.stop_loss - self.entry_price
            potential_gain = self.entry_price - self.take_profit
        
        if potential_loss <= 0:
            return 0.0
        return potential_gain / potential_loss


@dataclass
class PortfolioSummary:
    """Overall portfolio summary."""
    total_positions: int
    total_equity: float
    
    # By asset class
    crypto_exposure: float
    forex_exposure: float
    indices_exposure: float
    commodity_exposure: float
    
    # Counts
    crypto_positions: int
    forex_positions: int
    indices_positions: int
    commodity_positions: int
    
    # P&L
    total_pnl: float
    total_pnl_pct: float
    
    # Risk metrics
    max_risk_per_trade: float
    current_risk: float
    total_correlation_risk: float
    
    # Open positions (not full)
    open_positions: List[Position] = field(default_factory=list)


class PortfolioIntelligence:
    """Manage portfolio positions and risk exposure."""
    
    def __init__(self):
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.history: List[Dict] = []
    
    def add_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        current_price: float,
        volume: float,
        stop_loss: float,
        take_profit: float,
    ) -> None:
        """Add or update a position."""
        asset_class = self._get_asset_class(symbol)
        
        self.positions[symbol.upper()] = Position(
            symbol=symbol.upper(),
            asset_class=asset_class,
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
    
    def close_position(self, symbol: str, exit_price: float) -> Optional[float]:
        """Close a position and return PnL."""
        symbol = symbol.upper()
        
        if symbol not in self.positions:
            return None
        
        position = self.positions[symbol]
        position.current_price = exit_price
        
        pnl = position.pnl_pct
        
        # Record to history
        self.history.append({
            'symbol': symbol,
            'asset_class': position.asset_class,
            'direction': position.direction,
            'entry': position.entry_price,
            'exit': exit_price,
            'volume': position.volume,
            'pnl_pct': pnl,
            'closed_at': datetime.now(timezone.utc).isoformat(),
        })
        
        # Remove from active
        del self.positions[symbol]
        
        return pnl
    
    def _get_asset_class(self, symbol: str) -> str:
        """Determine asset class."""
        symbol_upper = symbol.upper()
        
        for class_name, symbols in ASSET_CLASSES.items():
            if any(s in symbol_upper for s in symbols):
                return class_name
        
        return 'OTHER'
    
    def get_exposure_by_class(self) -> Dict[str, Dict]:
        """Get exposure breakdown by asset class."""
        exposure = {
            'CRYPTO': {'count': 0, 'exposure': 0.0, 'pnl': 0.0},
            'FOREX': {'count': 0, 'exposure': 0.0, 'pnl': 0.0},
            'INDICES': {'count': 0, 'exposure': 0.0, 'pnl': 0.0},
            'COMMODITIES': {'count': 0, 'exposure': 0.0, 'pnl': 0.0},
            'OTHER': {'count': 0, 'exposure': 0.0, 'pnl': 0.0},
        }
        
        for pos in self.positions.values():
            ac = pos.asset_class
            
            if ac in ['FOREX_MAJOR', 'FOREX_JPY']:
                ac = 'FOREX'
            elif ac not in exposure:
                ac = 'OTHER'
            
            exposure[ac]['count'] += 1
            exposure[ac]['exposure'] += pos.volume * pos.current_price
            exposure[ac]['pnl'] += pos.pnl_pct
        
        return exposure
    
    def get_correlation_risk(self) -> float:
        """Calculate correlation risk (same-direction positions)."""
        # Count same-direction positions per asset class
        direction_risk: Dict[str, Dict[str, int]] = {}
        
        for pos in self.positions.values():
            if pos.asset_class not in direction_risk:
                direction_risk[pos.asset_class] = {'long': 0, 'short': 0}
            
            direction_risk[pos.asset_class][pos.direction] += 1
        
        # High risk = 3+ same-direction in same class
        risk = 0.0
        for ac, dirs in direction_risk.items():
            if dirs['long'] >= 3:
                risk += 0.3
            if dirs['short'] >= 3:
                risk += 0.3
        
        return min(risk, 1.0)
    
    def get_summary(self) -> PortfolioSummary:
        """Get portfolio summary."""
        total_equity = 0.0
        total_pnl = 0.0
        
        crypto_exposure = 0.0
        forex_exposure = 0.0
        indices_exposure = 0.0
        commodity_exposure = 0.0
        
        crypto_positions = 0
        forex_positions = 0
        indices_positions = 0
        commodity_positions = 0
        
        for pos in self.positions.values():
            value = pos.volume * pos.current_price
            total_equity += value
            total_pnl += pos.pnl_pct
            
            if pos.asset_class == 'CRYPTO':
                crypto_exposure += value
                crypto_positions += 1
            elif pos.asset_class in ['FOREX_MAJOR', 'FOREX_JPY']:
                forex_exposure += value
                forex_positions += 1
            elif pos.asset_class == 'INDICES':
                indices_exposure += value
                indices_positions += 1
            elif pos.asset_class == 'COMMODITIES':
                commodity_exposure += value
                commodity_positions += 1
        
        return PortfolioSummary(
            total_positions=len(self.positions),
            total_equity=total_equity,
            crypto_exposure=crypto_exposure,
            forex_exposure=forex_exposure,
            indices_exposure=indices_exposure,
            commodity_exposure=commodity_exposure,
            crypto_positions=crypto_positions,
            forex_positions=forex_positions,
            indices_positions=indices_positions,
            commodity_positions=commodity_positions,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl / len(self.positions) if self.positions else 0,
            max_risk_per_trade=float(os.getenv('MAX_RISK_PER_TRADE', '2.0') or 2.0),
            current_risk=sum(p.risk_reward for p in self.positions.values()) / len(self.positions) if self.positions else 0,
            total_correlation_risk=self.get_correlation_risk(),
            open_positions=list(self.positions.values()),
        )
    
    def format_portfolio_message(self) -> str:
        """Format portfolio summary as Telegram message."""
        summary = self.get_summary()
        
        lines = [
            "📊 <b>Portfolio Summary</b>",
            "",
            f"Positions: <b>{summary.total_positions}</b>",
            f"Equity: <b>${summary.total_equity:,.2f}</b>",
            f"P&L: <b>{summary.total_pnl_pct:+.2f}%</b>",
            "",
            "<b>Exposure by Asset Class:</b>",
            f"  Crypto: {summary.crypto_positions} pos • ${summary.crypto_exposure:,.0f}",
            f"  Forex: {summary.forex_positions} pos • ${summary.forex_exposure:,.0f}",
            f"  Indices: {summary.indices_positions} pos • ${summary.indices_exposure:,.0f}",
            f"  Commodities: {summary.commodity_positions} pos • ${summary.commodity_exposure:,.0f}",
            "",
            "<b>Risk Metrics:</b>",
            f"  Max Risk/Trade: {summary.max_risk_per_trade}%",
            f"  Current R:R: {summary.current_risk:.2f}",
            f"  Correlation Risk: {summary.total_correlation_risk:.0%}",
        ]
        
        if summary.open_positions:
            lines.append("")
            lines.append("<b>Open Positions:</b>")
            for pos in summary.open_positions[:10]:  # Show top 10
                lines.append(
                    f"  {pos.symbol} {pos.direction} "
                    f"{pos.pnl_pct:+.2f}% | "
                    f"RR: {pos.risk_reward:.2f}"
                )
        
        return "\n".join(lines)


# Singleton
_portfolio: Optional[PortfolioIntelligence] = None


def get_portfolio_intelligence() -> PortfolioIntelligence:
    """Get global portfolio intelligence."""
    global _portfolio
    if _portfolio is None:
        _portfolio = PortfolioIntelligence()
    return _portfolio


def format_portfolio() -> str:
    """Convenience function."""
    return get_portfolio_intelligence().format_portfolio_message()
