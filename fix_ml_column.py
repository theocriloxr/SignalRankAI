#!/usr/bin/env python3
"""
Quick fix: Add ml_probability column to Railway PostgreSQL if it doesn't exist.
Run this if Alembic migration hasn't applied yet.
"""
import sys
import os
import asyncio
from utils.async_runner import run_sync
from sqlalchemy import text

async def add_ml_probability_column():
    """Add ml_probability column to signals table if missing."""
    try:
        from db.session import get_session
        
        async with get_session() as session:
            # Check if column exists
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='signals' AND column_name='ml_probability'
                )
            """))
            column_exists = result.scalar()
            
            if column_exists:
                print("✅ ml_probability column already exists")
                return True
            
            # Add the column
            print("Adding ml_probability column to signals table...")
            await session.execute(text("""
                ALTER TABLE signals ADD COLUMN ml_probability FLOAT
            """))
            await session.commit()
            print("✅ Successfully added ml_probability column")
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    result = run_sync(add_ml_probability_column())
    sys.exit(0 if result else 1)
