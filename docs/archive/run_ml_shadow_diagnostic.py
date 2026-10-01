#!/usr/bin/env python3
"""
ML Shadow Predictions Diagnostic Script

This script queries the ml_shadow_predictions table to diagnose:
1. Whether shadow predictions are being persisted
2. The distribution of prob_source (model, default_zero, no_model, etc.)
3. Average probabilities by source
4. Any data gaps or errors

Run with: python run_ml_shadow_diagnostic.py
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def run_diagnostic() -> None:
    """Run the ML shadow predictions diagnostic query."""
    
    try:
        from db.session import get_session
        from db.models import MLShadowPrediction
        from sqlalchemy import select, func
        from sqlalchemy.sql import func as sql_func
    except ImportError as exc:
        logger.error("Failed to import required modules: %s", exc)
        logger.info("Make sure you're running from the project root with proper env vars set.")
        return

    # Query to get distribution by source (extracted from meta JSON)
    query = """
        SELECT 
            meta->>'source' as prob_source,
            COUNT(*) as count,
            ROUND(AVG(probability)::numeric, 4) as avg_prob,
            MIN(created_at) as first_seen
        FROM ml_shadow_predictions
        GROUP BY meta->>'source'
        ORDER BY count DESC;
    """
    
    # Alternative - use SQLAlchemy expressions
    logger.info("=" * 60)
    logger.info("ML SHADOW PREDICTIONS DIAGNOSTIC")
    logger.info("=" * 60)
    
    async with get_session() as session:
        # Get total count
        total_stmt = select(func.count(MLShadowPrediction.id))
        total_result = await session.execute(total_stmt)
        total_count = total_result.scalar() or 0
        
        logger.info("")
        logger.info("TOTAL RECORDS: %d", total_count)
        logger.info("")
        
        if total_count == 0:
            logger.warning("No shadow predictions found in the database!")
            logger.warning("")
            logger.warning("This means either:")
            logger.warning("1. ML Shadow Mode is disabled (ML_SHADOW_MODE env var)")
            logger.warning("2. The ML scoring code hasn't run yet")
            logger.warning("3. There's a code issue preventing persistence")
            return
        
        # Get count by source using raw SQL since we need to extract from JSON
        # First get all records and group in Python
        stmt = select(MLShadowPrediction)
        result = await session.execute(stmt)
        records = result.scalars().all()
        
        # Group by source
        source_stats: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            source = rec.meta.get("source", "unknown") if rec.meta else "unknown"
            if source not in source_stats:
                source_stats[source] = {
                    "count": 0,
                    "total_prob": 0.0,
                    "first_seen": rec.created_at,
                }
            source_stats[source]["count"] += 1
            source_stats[source]["total_prob"] += rec.probability
            if rec.created_at < source_stats[source]["first_seen"]:
                source_stats[source]["first_seen"] = rec.created_at
        
        # Print results
        logger.info("DISTRIBUTION BY SOURCE:")
        logger.info("-" * 60)
        logger.info(f"{'Source':<30} {'Count':>8} {'Avg Prob':>12} {'First Seen':>18}")
        logger.info("-" * 60)
        
        for source, stats in sorted(source_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            avg_prob = stats["total_prob"] / stats["count"] if stats["count"] > 0 else 0.0
            first_seen = stats["first_seen"].strftime("%Y-%m-%d %H:%M") if stats["first_seen"] else "N/A"
            logger.info(f"{source:<30} {stats['count']:>8} {avg_prob:>12.4f} {first_seen:>18}")
        
        logger.info("-" * 60)
        
        # Additional stats
        logger.info("")
        logger.info("ADDITIONAL INSIGHTS:")
        logger.info("-" * 60)
        
        # Count by schema_ok
        schema_ok_true = sum(1 for rec in records if rec.feature_schema_ok)
        schema_ok_false = total_count - schema_ok_true
        logger.info("feature_schema_ok=True:  %d", schema_ok_true)
        logger.info("feature_schema_ok=False: %d", schema_ok_false)
        
        # Probability distribution
        probs = [rec.probability for rec in records]
        if probs:
            logger.info("")
            logger.info("PROBABILITY STATS:")
            logger.info("  Min:    %.4f", min(probs))
            logger.info("  Max:    %.4f", max(probs))
            logger.info("  Avg:    %.4f", sum(probs) / len(probs))
            logger.info("  Zero:   %d", sum(1 for p in probs == 0.0))
            logger.info("  Non-Zero: %d", sum(1 for p in probs > 0.0))
        
        # Recent records
        logger.info("")
        logger.info("RECENT RECORDS (last 5):")
        logger.info("-" * 60)
        
        recent_stmt = (
            select(MLShadowPrediction)
            .order_by(MLShadowPrediction.created_at.desc())
            .limit(5)
        )
        recent_result = await session.execute(recent_stmt)
        recent_records = recent_result.scalars().all()
        
        for rec in recent_records:
            source = rec.meta.get("source", "N/A") if rec.meta else "N/A"
            asset = rec.meta.get("asset", "N/A") if rec.meta else "N/A"
            logger.info(
                "  %s | asset=%s | prob=%.3f | source=%s | schema_ok=%s",
                rec.created_at.strftime("%Y-%m-%d %H:%M"),
                asset,
                rec.probability,
                source,
                rec.feature_schema_ok,
            )


async def main() -> None:
    """Main entry point."""
    logger.info("Starting ML Shadow Predictions Diagnostic...")
    logger.info("")
    
    try:
        await run_diagnostic()
    except Exception as exc:
        logger.error("Diagnostic failed: %s", exc)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    logger.info("")
    logger.info("Diagnostic complete.")


if __name__ == "__main__":
    asyncio.run(main())
