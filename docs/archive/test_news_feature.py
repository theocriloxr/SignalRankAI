#!/usr/bin/env python
"""Test the News Feature implementation"""
import sys
sys.path.insert(0, '.')

print("Testing News Feature Implementation...\n")

# Test 1: Economic Calendar Module
print("1. Testing economic_calendar imports...")
try:
    from services.economic_calendar import (
        fetch_economic_events,
        is_no_trade_zone,
        is_no_trade_zone_sync,
        get_macro_news_context,
        get_volatility_buffer_info,
        get_upcoming_events_summary,
        REDIS_EVENTS_KEY,
        NO_TRADE_BUFFER_MINUTES,
    )
    print("   ✓ All economic_calendar exports OK")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 2: Repository get_economic_events  
print("\n2. Testing repository.get_economic_events...")
try:
    from db.repository import get_economic_events
    print("   ✓ get_economic_events exists")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 3: EconomicEvent Model
print("\n3. Testing EconomicEvent model...")
try:
    from db.models import EconomicEvent
    attrs = [a for a in dir(EconomicEvent) if not a.startswith('_')]
    print(f"   ✓ Model OK - fields: {attrs}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 4: Worker news_sync
print("\n4. Testing worker news_sync_worker...")
try:
    from worker.news_sync_worker import start_news_sync_worker
    print("   ✓ news_sync_worker imports OK")
except Exception as e:
    print(f"   ✗ Import warning: {e} (may be env issue)")

# Test 5: Gemini ML Module (if API key present)
print("\n5. Testing services.gemini_ml...")
try:
    import os
    if os.getenv("GEMINI_API_KEY"):
        from services.gemini_ml import gemini_confluence_check
        print("   ✓ gemini_ml with API key OK")
    else:
        from services.gemini_ml import gemini_confluence_check
        print("   ✓ gemini_ml imports OK (no API key)")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 6: Engine integration
print("\n6. Testing engine news integration...")
try:
    # Just check the import, don't run full engine
    from engine.news_filter import NewsKillswitch, news_guard
    print("   ✓ NewsKillswitch exists")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "="*50)
print("News Feature Test Complete!")
print("="*50)
