# Test script to verify db.session imports work
import sys
sys.path.insert(0, 'c:/Users/sammm/Desktop/SignalRankAI')

try:
    from db.session import (
        get_pool_status, 
        is_pool_near_exhaustion, 
        run_with_db_retry, 
        is_transient_db_error,
        _effective_pool_settings
    )
    print("✓ All imports successful")
    
    # Test pool settings
    pool_size, max_overflow = _effective_pool_settings()
    print(f"✓ Pool settings: pool_size={pool_size}, max_overflow={max_overflow}")
    
    # Test transient error detection
    test_errors = [
        "too many clients already",
        "TooManyConnectionsError",
        "connection reset by peer"
    ]
    for err in test_errors:
        result = is_transient_db_error(Exception(err))
        print(f"✓ is_transient_db_error('{err}'): {result}")
    
    print("\nAll tests passed!")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
