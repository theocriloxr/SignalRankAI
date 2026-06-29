"""
Public Track Record
Phase 4.3 - Public Performance Statistics

Shows: 30-day win rate, 90-day win rate, Profit factor, Drawdown
Per asset class performance
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TrackRecord:
    """Single signal outcome record."""
    signal_id: str
    asset: str
    asset_class: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    result: str  # 'win', 'loss', 'breakeven'
    pnl_pct: float
    pnl_r: float
    closed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PerformanceStats:
    """Aggregated performance statistics."""
    period_days: int
    
    total_trades: int
    
    # Win rate
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    
    # P&L
    total_pnl_pct: float
    avg_pnl_pct: float
    total_r: float
    
    # Best/worst
    best_trade_pct: float
    worst_trade_pct: float
    
    # Holding times
    avg_holding_hours: float
    
    # By asset class
    crypto_stats: Optional['AssetClassStats'] = None
    forex_stats: Optional['AssetClassStats'] = None
    indices_stats: Optional['AssetClassStats'] = None
    commodities_stats: Optional['AssetClassStats'] = None


@dataclass
class AssetClassStats:
    """Per asset class statistics."""
    asset_class: str
    total: int
    wins: int
    win_rate: float
    avg_pnl: float


class PublicTrackRecord:
    """Public performance track record."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize track record."""
        self.db_path = db_path or os.getenv("TRACK_RECORD_DB", "data/track_record.json")
        self.records: List[TrackRecord] = []
        self._load_records()
    
    def _load_records(self) -> None:
        """Load records from persistent storage."""
        if not os.path.exists(self.db_path):
            return
        
        try:
            import json
            with open(self.db_path, 'r') as f:
                data = json.load(f)
            
            for item in data.get('records', []):
                closed = item.get('closed_at')
                if closed:
                    try:
                        closed = datetime.fromisoformat(closed)
                    except Exception:
                        closed = datetime.now(timezone.utc)
                else:
                    closed = datetime.now(timezone.utc)
                
                self.records.append(TrackRecord(
                    signal_id=item.get('signal_id', ''),
                    asset=item.get('asset', ''),
                    asset_class=item.get('asset_class', ''),
                    direction=item.get('direction', ''),
                    entry_price=float(item.get('entry_price', 0)),
                    exit_price=float(item.get('exit_price', 0)),
                    stop_loss=float(item.get('stop_loss', 0)),
                    take_profit=float(item.get('take_profit', 0)),
                    result=item.get('result', ''),
                    pnl_pct=float(item.get('pnl_pct', 0)),
                    pnl_r=float(item.get('pnl_r', 0)),
                    closed_at=closed,
                ))
            
            logger.info(f"[track_record] Loaded {len(self.records)} records")
        
        except Exception as e:
            logger.warning(f"[track_record] Load failed: {e}")
    
    def _save_records(self) -> None:
        """Save records to persistent storage."""
        try:
            import json
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            data = {
                'records': [
                    {
                        'signal_id': r.signal_id,
                        'asset': r.asset,
                        'asset_class': r.asset_class,
                        'direction': r.direction,
                        'entry_price': r.entry_price,
                        'exit_price': r.exit_price,
                        'stop_loss': r.stop_loss,
                        'take_profit': r.take_profit,
                        'result': r.result,
                        'pnl_pct': r.pnl_pct,
                        'pnl_r': r.pnl_r,
                        'closed_at': r.closed_at.isoformat()
                    }
                    for r in self.records
                ],
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }
            
            with open(self.db_path, 'w') as f:
                json.dump(data, f, indent=2)
        
        except Exception as e:
            logger.warning(f"[track_record] Save failed: {e}")
    
    def record_trade(
        self,
        signal_id: str,
        asset: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> None:
        """Record a completed trade."""
        asset_class = self._get_asset_class(asset)
        
        # Calculate PnL
        if direction == 'long':
            pnl_pct = (exit_price - entry_price) / entry_price * 100
            risk = entry_price - stop_loss
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100
            risk = stop_loss - entry_price
        
        # Calculate R multiples
        pnl_r = 0.0
        if risk > 0:
            pnl_r = (exit_price - entry_price) / risk if direction == 'long' else (entry_price - exit_price) / risk
        
        # Determine result
        result = 'breakeven'
        if pnl_pct > 0.5:
            result = 'win'
        elif pnl_pct < -0.5:
            result = 'loss'
        
        record = TrackRecord(
            signal_id=signal_id,
            asset=asset.upper(),
            asset_class=asset_class,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            result=result,
            pnl_pct=pnl_pct,
            pnl_r=pnl_r,
        )
        
        self.records.append(record)
        
        # Save periodically
        if len(self.records) % 50 == 0:
            self._save_records()
    
    def _get_asset_class(self, asset: str) -> str:
        """Determine asset class."""
        asset_upper = asset.upper()
        
        crypto = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'DOT', 'AVAX', 'MATIC', 'LINK', 'UNI']
        forex = ['EUR', 'USD', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD']
        indices = ['US30', 'US500', 'NAS100', 'GER40', 'UK100', 'JPN225']
        commodities = ['XAU', 'XAG', 'OIL', 'NATGAS']
        
        if any(c in asset_upper for c in crypto):
            return 'CRYPTO'
        elif any(c in asset_upper for c in forex):
            return 'FOREX'
        elif any(c in asset_upper for c in indices):
            return 'INDICES'
        elif any(c in asset_upper for c in commodities):
            return 'COMMODITIES'
        
        return 'OTHER'
    
    def get_stats(self, days: int) -> PerformanceStats:
        """Get performance stats for a period."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        
        # Filter by period
        period_records = [r for r in self.records if r.closed_at >= cutoff]
        
        if not period_records:
            return PerformanceStats(
                period_days=days,
                total_trades=0,
                wins=0,
                losses=0,
                breakeven=0,
                win_rate=0.0,
                total_pnl_pct=0.0,
                avg_pnl_pct=0.0,
                total_r=0.0,
                best_trade_pct=0.0,
                worst_trade_pct=0.0,
                avg_holding_hours=0.0,
            )
        
        # Calculate stats
        total = len(period_records)
        wins = sum(1 for r in period_records if r.result == 'win')
        losses = sum(1 for r in period_records if r.result == 'loss')
        breakeven = sum(1 for r in period_records if r.result == 'breakeven')
        
        win_rate = wins / total * 100 if total > 0 else 0
        
        total_pnl = sum(r.pnl_pct for r in period_records)
        avg_pnl = total_pnl / total if total > 0 else 0
        
        total_r = sum(r.pnl_r for r in period_records)
        
        best = max((r.pnl_pct for r in period_records), default=0)
        worst = min((r.pnl_pct for r in period_records), default=0)
        
        # By asset class
        crypto_records = [r for r in period_records if r.asset_class == 'CRYPTO']
        forex_records = [r for r in period_records if r.asset_class == 'FOREX']
        indices_records = [r for r in period_records if r.asset_class == 'INDICES']
        commodities_records = [r for r in period_records if r.asset_class == 'COMMODITIES']
        
        return PerformanceStats(
            period_days=days,
            total_trades=total,
            wins=wins,
            losses=losses,
            breakeven=breakeven,
            win_rate=win_rate,
            total_pnl_pct=total_pnl,
            avg_pnl_pct=avg_pnl,
            total_r=total_r,
            best_trade_pct=best,
            worst_trade_pct=worst,
            avg_holding_hours=0,  # Would need holding time tracked
            crypto_stats=self._asset_class_stats(crypto_records),
            forex_stats=self._asset_class_stats(forex_records),
            indices_stats=self._asset_class_stats(indices_records),
            commodities_stats=self._asset_class_stats(commodities_records),
        )
    
    def _asset_class_stats(self, records: List[TrackRecord]) -> Optional[AssetClassStats]:
        """Calculate stats for asset class."""
        if not records:
            return None
        
        total = len(records)
        wins = sum(1 for r in records if r.result == 'win')
        
        return AssetClassStats(
            asset_class=records[0].asset_class,
            total=total,
            wins=wins,
            win_rate=wins / total * 100 if total > 0 else 0,
            avg_pnl=sum(r.pnl_pct for r in records) / total if total > 0 else 0,
        )
    
    def get_public_message(self) -> str:
        """Get public track record message."""
        stats_30 = self.get_stats(30)
        stats_90 = self.get_stats(90)
        
        lines = [
            "📊 <b>SignalRankAI Track Record</b>",
            "",
            f"<b>Last 30 Days:</b>",
            f"  Trades: {stats_30.total_trades}",
            f"  Win Rate: {stats_30.win_rate:.1f}%",
            f"  Net P&L: {stats_30.total_pnl_pct:+.2f}%",
            f"  Total R: {stats_30.total_r:+.1f}R",
            "",
            f"<b>Last 90 Days:</b>",
            f"  Trades: {stats_90.total_trades}",
            f"  Win Rate: {stats_90.win_rate:.1f}%",
            f"  Net P&L: {stats_90.total_pnl_pct:+.2f}%",
            f"  Total R: {stats_90.total_r:+.1f}R",
        ]
        
        # Per asset class (if available)
        lines.append("")
        lines.append("<b>By Asset Class:</b>")
        
        for name, stats in [
            ('Crypto', stats_30.crypto_stats),
            ('Forex', stats_30.forex_stats),
            ('Indices', stats_30.indices_stats),
            ('Commodities', stats_30.commodities_stats),
        ]:
            if stats and stats.total > 0:
                lines.append(f"  {name}: {stats.total} trades | {stats.win_rate:.0f}% win | {stats.avg_pnl:+.1f}% avg")
        
        # Disclaimer
        lines.append("")
        lines.append("⚠️ <i>Past performance does not guarantee future results.</i>")
        
        return "\n".join(lines)


# Singleton
_track_record: Optional[PublicTrackRecord] = None


def get_public_track_record() -> PublicTrackRecord:
    """Get global track record."""
    global _track_record
    if _track_record is None:
        _track_record = PublicTrackRecord()
    return _track_record


def format_track_record() -> str:
    """Convenience function."""
    return get_public_track_record().get_public_message()


def record_trade_result(
    signal_id: str,
    asset: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    stop_loss: float,
    take_profit: float,
) -> None:
    """Convenience function to record a trade result."""
    get_public_track_record().record_trade(
        signal_id=signal_id,
        asset=asset,
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
