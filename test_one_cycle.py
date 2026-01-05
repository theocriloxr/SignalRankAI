"""Quick test of one engine cycle to verify signal generation"""
import os
os.environ["ENGINE_CYCLE_LOG"] = "1"
os.environ["ENGINE_ASSET_DEBUG"] = "0" 
os.environ["ENGINE_SIGNAL_DEBUG"] = "1"

from engine.core import main_loop
import asyncio

print("[TEST] Running one engine cycle with signal debugging enabled...")
print("[TEST] This will show if signals are being generated and processed.\n")

# Run exactly 1 cycle
import sys
sys.argv = ['test', '--cycles', '1']

try:
    main_loop(DRY_RUN=False)
    print("\n[TEST] ✅ Cycle completed successfully!")
except Exception as e:
    print(f"\n[TEST] ❌ Error: {e}")
    import traceback
    traceback.print_exc()
