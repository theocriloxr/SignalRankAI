"""Quick test to verify MLRejectionTracker import"""
import sys
sys.path.insert(0, 'c:/Users/sammm/Desktop/SignalRankAI')

try:
    from engine.signal_deduplicator import SignalDeduplicator
    print("SignalDeduplicator import: OK")
except Exception as e:
    print(f"SignalDeduplicator import: FAILED - {e}")

try:
    from engine.signal_deduplicator import MLRejectionTracker
    print("MLRejectionTracker import: OK")
    # Try instantiating
    tracker = MLRejectionTracker()
    print("MLRejectionTracker instantiated: OK")
except Exception as e:
    print(f"MLRejectionTracker import: FAILED - {e}")
