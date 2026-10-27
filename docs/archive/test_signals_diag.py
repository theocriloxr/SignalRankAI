"""Quick diagnostic to test signal retrieval functions."""
import asyncio
import os
import sys

# Set up path
sys.path.insert(0, os.path.dirname(__file__))


async def test_signal_retrieval():
    """Test if signals can be retrieved for a user ID."""
    from db.session import get_session, get_engine_for_event_loop
    from db.pg_features import list_unresolved_signals_for_user, list_signals_sent_today
    from sqlalchemy import select
    from db.models import User, SignalDelivery
    
    engine = get_engine_for_event_loop()
    if engine is None:
        print("❌ Database not configured")
        return
    
    # Test with user_id 0 for testing (or use actual user)
    test_user_id = 0  # Use 0 to test without user-specific filtering
    
    async with get_session() as session:
        # Test list_unresolved_signals_for_user
        print(f"Testing list_unresolved_signals_for_user for user {test_user_id}...")
        signals = await list_unresolved_signals_for_user(session, test_user_id, 30)
        print(f"  Found {len(signals)} unresolved signals")
        if signals:
            print(f"  First signal: {signals[0].asset} {signals[0].timeframe} {signals[0].direction}")
        
        # Test list_signals_sent_today  
        print(f"\nTesting list_signals_sent_today for user {test_user_id}...")
        today_signals = await list_signals_sent_today(session, test_user_id)
        print(f"  Found {len(today_signals)} signals sent today")
        if today_signals:
            print(f"  First signal: {today_signals[0].asset} {today_signals[0].timeframe}")
        
        # Check if there are ANY signals in the database
        print("\nChecking total signals in database...")
        result = await session.execute(select(SignalDelivery).limit(5))
        deliveries = result.scalars().all()
        print(f"  Total SignalDelivery rows (sample of 5): {len(deliveries)}")
        for d in deliveries:
            print(f"    - user_id={d.user_id}, signal_id={str(d.signal_id)[:8]}, sent_ok={d.sent_ok}")


if __name__ == "__main__":
    asyncio.run(test_signal_retrieval())
