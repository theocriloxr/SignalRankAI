"""
Trade Analytics - MFE & MAE Tracking

Calculates Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE)
for trades. These metrics are essential for optimizing stop-loss and take-profit
levels.

MFE (Maximum Favorable Excursion): 
    How far into profit did the trade go before closing?
    Used to optimize TP levels.

MAE (Maximum Adverse Excursion):
    How far into loss did the trade go before closing?
    Used to optimize SL levels.

Usage:
    from engine.analytics import ExcursionCalculator
    
    excursions = ExcursionCalculator.calculate_mfe_mae(
        entry_price=50000.0,
        direction="LONG",
        price_history_df=candles_df
    )
    # Returns: {'mfe_pct': 2.5, 'mae_pct': -1.2}
"""

from __future__ import annotations

import logging
from typing import Optional
import pandas as pd

logger = logging.getLogger("TradeAnalytics")


class ExcursionCalculator:
    """
    Calculates MFE (Maximum Favorable Excursion) and MAE (Maximum Adverse Excursion)
    for trades to optimize exit strategies.
    """
    
    @staticmethod
    def calculate_mfe_mae(
        entry_price: float,
        direction: str,
        price_history_df: pd.DataFrame,
    ) -> dict:
        """
        Calculate MFE and MAE for a trade.
        
        Args:
            entry_price: Price at which the trade was entered
            direction: 'LONG' or 'SHORT'
            price_history_df: DataFrame with 'high' and 'low' columns 
                           representing price range during the trade
            
        Returns:
            Dict with:
            - mfe_pct: Maximum Favorable Excursion as percentage
            - mae_pct: Maximum Adverse Excursion as percentage (always negative)
        """
        # Validate inputs
        if entry_price <= 0:
            logger.warning(
                f"[analytics] Invalid entry_price: {entry_price}, returning zeros"
            )
            return {"mfe_pct": 0.0, "mae_pct": 0.0}
        
        if price_history_df.empty:
            logger.warning(
                "[analytics] Empty price_history_df, returning zeros"
            )
            return {"mfe_pct": 0.0, "mae_pct": 0.0}
        
        # Ensure we have required columns
        if 'high' not in price_history_df.columns or 'low' not in price_history_df.columns:
            logger.warning(
                "[analytics] price_history_df missing 'high' or 'low' column"
            )
            return {"mfe_pct": 0.0, "mae_pct": 0.0}
        
        try:
            # Find the absolute highest and lowest price points during the trade
            highest_price = price_history_df['high'].max()
            lowest_price = price_history_df['low'].min()
            
            mfe_pct = 0.0
            mae_pct = 0.0
            
            direction = direction.upper() if direction else ""
            
            if direction == "LONG":
                # MFE = How high did it go above entry?
                if highest_price > entry_price:
                    mfe_pct = ((highest_price - entry_price) / entry_price) * 100
                
                # MAE = How low did it drop below entry? (should be negative)
                if lowest_price < entry_price:
                    mae_pct = ((lowest_price - entry_price) / entry_price) * 100
                    
            elif direction == "SHORT":
                # MFE (for SHORT) = How low did it drop below entry?
                if lowest_price < entry_price:
                    mfe_pct = ((entry_price - lowest_price) / entry_price) * 100
                
                # MAE (for SHORT) = How high did it go above entry? (should be negative)
                if highest_price > entry_price:
                    mae_pct = ((entry_price - highest_price) / entry_price) * 100
            
            # Ensure MAE is represented as a negative number for pain
            mae_pct = -abs(mae_pct)
            # Ensure MFE is represented as a positive number for gain
            mfe_pct = abs(mfe_pct)
            
            result = {
                "mfe_pct": round(mfe_pct, 4),
                "mae_pct": round(mae_pct, 4)
            }
            
            logger.debug(
                f"[analytics] {direction} @ ${entry_price:.2f}: "
                f"MFE=+{mfe_pct:.2f}%, MAE={mae_pct:.2f}%"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[analytics] MFE/MAE calculation failed: {e}")
            return {"mfe_pct": 0.0, "mae_pct": 0.0}
    
    @staticmethod
    def calculate_excursion_from_candles(
        entry_price: float,
        entry_time: pd.Timestamp,
        exit_time: pd.Timestamp,
        candles_df: pd.DataFrame,
        direction: str,
    ) -> dict:
        """
        Calculate MFE/MAE using time-bound candles.
        
        More precise version that uses exact entry/exit times.
        
        Args:
            entry_price: Entry price
            entry_time: When the trade was opened
            exit_time: When the trade was closed
            candles_df: DataFrame with 'timestamp', 'high', 'low' columns
            direction: 'LONG' or 'SHORT'
            
        Returns:
            Dict with mfe_pct and mae_pct
        """
        if candles_df.empty:
            return {"mfe_pct": 0.0, "mae_pct": 0.0}
        
        # Filter candles to trade window
        if 'timestamp' in candles_df.columns:
            trade_candles = candles_df[
                (candles_df['timestamp'] >= entry_time) & 
                (candles_df['timestamp'] <= exit_time)
            ]
        elif 'time' in candles_df.columns:
            trade_candles = candles_df[
                (candles_df['time'] >= entry_time) & 
                (candles_df['time'] <= exit_time)
            ]
        else:
            # Use all candles if no timestamp column
            trade_candles = candles_df
        
        return ExcursionCalculator.calculate_mfe_mae(
            entry_price=entry_price,
            direction=direction,
            price_history_df=trade_candles
        )


class AnalyticsTracker:
    """
    Tracks analytics across multiple trades for pattern recognition.
    
    This class can be used to:
    - Aggregate MFE/MAE statistics
    - Identify optimal SL/TP levels
    - Provide feedback to ML models
    """
    
    def __init__(self):
        self._trades: list = []
        self._max_trades = 1000  # Keep last 1000 trades in memory
    
    def record_trade(
        self,
        asset: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        mfe_pct: float,
        mae_pct: float,
    ) -> None:
        """
        Record a completed trade for analytics.
        
        Args:
            asset: Trading symbol
            direction: LONG or SHORT
            entry_price: Entry price
            exit_price: Exit price
            mfe_pct: Maximum favorable excursion %
            mae_pct: Maximum adverse excursion %
        """
        trade = {
            "asset": asset,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "mfe_pct": mfe_pct,
            "mae_pct": mae_pct,
        }
        
        self._trades.append(trade)
        
        # Trim history if needed
        if len(self._trades) > self._max_trades:
            self._trades = self._trades[-self._max_trades:]
    
    def get_average_mfe(self, direction: Optional[str] = None) -> float:
        """
        Get average MFE across recorded trades.
        
        Args:
            direction: Optional filter (LONG/SHORT)
            
        Returns:
            Average MFE percentage
        """
        if not self._trades:
            return 0.0
        
        filtered = self._trades
        if direction:
            filtered = [t for t in self._trades if t.get("direction") == direction.upper()]
        
        if not filtered:
            return 0.0
        
        return sum(t.get("mfe_pct", 0) for t in filtered) / len(filtered)
    
    def get_average_mae(self, direction: Optional[str] = None) -> float:
        """
        Get average MAE across recorded trades.
        
        Args:
            direction: Optional filter (LONG/SHORT)
            
        Returns:
            Average MAE percentage (negative)
        """
        if not self._trades:
            return 0.0
        
        filtered = self._trades
        if direction:
            filtered = [t for t in self._trades if t.get("direction") == direction.upper()]
        
        if not filtered:
            return 0.0
        
        return sum(t.get("mae_pct", 0) for t in filtered) / len(filtered)
    
    def get_optimal_sl(self, direction: str, percentile: float = 95.0) -> float:
        """
        Get optimal stop loss based on historical MAE.
        
        Args:
            direction: LONG or SHORT
            percentile: Percentile to use (e.g., 95 = worst 5% of trades)
            
        Returns:
            Optimal SL percentage (negative)
        """
        if not self._trades:
            return -2.0  # Default -2%
        
        filtered = [t for t in self._trades if t.get("direction") == direction.upper()]
        
        if not filtered:
            return -2.0
        
        mae_values = sorted([abs(t.get("mae_pct", 0)) for t in filtered])
        
        if not mae_values:
            return -2.0
        
        # Get percentile index
        idx = int(len(mae_values) * (1 - percentile / 100))
        idx = min(idx, len(mae_values) - 1)
        
        return -mae_values[idx]
    
    def get_optimal_tp(self, direction: str, percentile: float = 50.0) -> float:
        """
        Get optimal take profit based on historical MFE.
        
        Args:
            direction: LONG or SHORT
            percentile: Percentile to use (e.g., 50 = median, 80 = 80th percentile)
            
        Returns:
            Optimal TP percentage (positive)
        """
        if not self._trades:
            return 3.0  # Default 3%
        
        filtered = [t for t in self._trades if t.get("direction") == direction.upper()]
        
        if not filtered:
            return 3.0
        
        mfe_values = sorted([t.get("mfe_pct", 0) for t in filtered])
        
        if not mfe_values:
            return 3.0
        
        # Get percentile index
        idx = int(len(mfe_values) * (percentile / 100))
        idx = min(idx, len(mfe_values) - 1)
        
        return mfe_values[idx]
    
    def get_statistics(self) -> dict:
        """
        Get overall analytics statistics.
        
        Returns:
            Dict with aggregated statistics
        """
        if not self._trades:
            return {
                "total_trades": 0,
                "avg_mfe": 0.0,
                "avg_mae": 0.0,
                "optimal_sl_long": -2.0,
                "optimal_sl_short": -2.0,
                "optimal_tp_long": 3.0,
                "optimal_tp_short": 3.0,
            }
        
        return {
            "total_trades": len(self._trades),
            "avg_mfe": round(self.get_average_mfe(), 2),
            "avg_mae": round(self.get_average_mae(), 2),
            "optimal_sl_long": round(self.get_optimal_sl("LONG"), 2),
            "optimal_sl_short": round(self.get_optimal_sl("SHORT"), 2),
            "optimal_tp_long": round(self.get_optimal_tp("LONG"), 2),
            "optimal_tp_short": round(self.get_optimal_tp("SHORT"), 2),
        }


# Default instance
default_analytics_tracker = AnalyticsTracker()


def calculate_mfe_mae(
    entry_price: float,
    direction: str,
    price_history_df: pd.DataFrame,
) -> dict:
    """
    Convenience function to calculate MFE/MAE.
    
    Args:
        entry_price: Entry price
        direction: LONG or SHORT
        price_history_df: DataFrame with high/low columns
        
    Returns:
        Dict with mfe_pct and mae_pct
    """
    return ExcursionCalculator.calculate_mfe_mae(
        entry_price=entry_price,
        direction=direction,
        price_history_df=price_history_df
    )


class RegimeAnalytics:
    """In-memory performance analytics grouped by regime, asset, and timeframe."""

    def __init__(self):
        self._results: list[dict] = []
        self._max_results = 5000

    def record_result(
        self,
        asset: str,
        timeframe: str,
        regime: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        outcome: str,
    ) -> None:
        if not outcome:
            return
        try:
            entry = float(entry_price)
            exit_ = float(exit_price)
        except Exception:
            entry = 0.0
            exit_ = 0.0
        pnl_pct = 0.0
        if entry > 0:
            if str(direction or "").upper() == "SHORT":
                pnl_pct = ((entry - exit_) / entry) * 100.0
            else:
                pnl_pct = ((exit_ - entry) / entry) * 100.0
        self._results.append(
            {
                "asset": str(asset or "").upper(),
                "timeframe": str(timeframe or "").lower(),
                "regime": str(regime or "NEUTRAL").upper(),
                "direction": str(direction or "").upper(),
                "outcome": str(outcome or "").upper(),
                "is_win": str(outcome or "").upper() == "WIN",
                "pnl_pct": pnl_pct,
            }
        )
        if len(self._results) > self._max_results:
            self._results = self._results[-self._max_results:]

    def _filtered(self, key: str, value: str) -> list[dict]:
        value_norm = str(value or "").upper()
        return [row for row in self._results if str(row.get(key, "")).upper() == value_norm]

    @staticmethod
    def _win_rate(rows: list[dict]) -> float:
        if not rows:
            return 0.0
        return sum(1 for row in rows if row.get("is_win")) / len(rows) * 100.0

    def get_win_rate_by_regime(self, regime: str) -> float:
        return self._win_rate(self._filtered("regime", regime))

    def get_win_rate_by_asset(self, asset: str) -> float:
        return self._win_rate(self._filtered("asset", asset))

    def get_win_rate_by_timeframe(self, timeframe: str) -> float:
        return self._win_rate([row for row in self._results if row.get("timeframe") == str(timeframe or "").lower()])

    def get_profit_factor_by_regime(self, regime: str) -> float:
        rows = self._filtered("regime", regime)
        gross_profit = sum(float(row.get("pnl_pct", 0) or 0) for row in rows if float(row.get("pnl_pct", 0) or 0) > 0)
        gross_loss = abs(sum(float(row.get("pnl_pct", 0) or 0) for row in rows if float(row.get("pnl_pct", 0) or 0) < 0))
        return gross_profit / gross_loss if gross_loss else (gross_profit if gross_profit > 0 else 0.0)

    def get_regime_statistics(self) -> dict:
        stats = {}
        for regime in sorted({row.get("regime", "NEUTRAL") for row in self._results} | {"TRENDING", "RANGING", "VOLATILE", "NEUTRAL"}):
            win_rate = self.get_win_rate_by_regime(regime)
            profit_factor = self.get_profit_factor_by_regime(regime)
            if win_rate > 0 or profit_factor > 0:
                stats[regime] = {"win_rate": round(win_rate, 2), "profit_factor": round(profit_factor, 2)}
        return stats

    def get_asset_statistics(self) -> dict:
        return {
            asset: {"win_rate": round(self.get_win_rate_by_asset(asset), 2)}
            for asset in sorted({row.get("asset", "") for row in self._results if row.get("asset")})
        }

    def get_timeframe_statistics(self) -> dict:
        return {
            timeframe: {"win_rate": round(self.get_win_rate_by_timeframe(timeframe), 2)}
            for timeframe in sorted({row.get("timeframe", "") for row in self._results if row.get("timeframe")})
        }


_regime_analytics = RegimeAnalytics()


def get_regime_analytics() -> RegimeAnalytics:
    return _regime_analytics
