#!/usr/bin/env python3
"""Add created_at column to signal_deliveries table."""
import asyncio
import os


async def check_and_add_column():
    try:
        from db.session import get_session
        from sqlalchemy import text

        async with get_session() as session:
            # First, check if column exists
            try:
                result = await session.execute(text("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'signal_deliveries' AND column_name = 'created_at'
                """))
                exists = result.fetchone()
                if exists:
                    print('Column created_at already exists in signal_deliveries')
                    return True
            except Exception as e:
                print(f'Check error (may not matter): {e}')

            # Try to add column with IF NOT EXISTS (PostgreSQL 9.3+)
            try:
                await session.execute(text("""
                    ALTER TABLE signal_deliveries 
                    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                """))
                await session.commit()
                print('Column created_at added successfully')
                return True
            except Exception as e:
                print(f'Add column error: {e}')
                # Try without IF NOT EXISTS
                try:
                    await session.execute(text("""
                        ALTER TABLE signal_deliveries 
                        ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    """))
                    await session.commit()
                    print('Column created_at added (alt syntax)')
                    return True
                except Exception as e2:
                    print(f'Alt syntax error: {e2}')
                    return False

    except Exception as main_err:
        print(f'Database connection error: {main_err}')
        return False


if __name__ == '__main__':
    result = asyncio.run(check_and_add_column())
    print(f"Done: {result}")
