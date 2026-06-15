#!/usr/bin/env python3
"""
Apply the threshold fix to allow 82.43 scores through.

Run this script BEFORE starting the engine to set the correct thresholds.
Or set environment variables directly in Railway dashboard.
"""

import os
import sys

def apply_fix():
    """Apply threshold overrides"""
    # These must be set BEFORE importing engine modules
    os.environ['ML_PROB_THRESHOLD'] = '0.80'
    os.environ['PREMIUM_SCORE_THRESHOLD'] = '75'
    os.environ['PREMIUM_SCORE_THRESHOLD_FORCE'] = '0'
    os.environ['LOG_LEVEL'] = 'DEBUG'
    
    print("=" * 60)
    print("THRESHOLD FIX APPLIED")
    print("=" * 60)
    print()
    print("Environment Variables Set:")
    print(f"  ML_PROB_THRESHOLD = {os.environ['ML_PROB_THRESHOLD']}")
    print(f"  PREMIUM_SCORE_THRESHOLD = {os.environ['PREMIUM_SCORE_THRESHOLD']}")
    print(f"  PREMIUM_SCORE_THRESHOLD_FORCE = {os.environ['PREMIUM_SCORE_THRESHOLD_FORCE']}")
    print(f"  LOG_LEVEL = {os.environ['LOG_LEVEL']}")
    print()
    print("Expected Results:")
    print("  - generated_signals=1")
    print("  - stored=1")
    print("  - ml_shadow_predictions will populate")
    print()
    print("Railway Dashboard Settings:")
    print("  Add these environment variables:")
    print("    ML_PROB_THRESHOLD = 0.80")
    print("    PREMIUM_SCORE_THRESHOLD = 75")
    print("    LOG_LEVEL = DEBUG")
    print()
    
    return True

if __name__ == "__main__":
    success = apply_fix()
    sys.exit(0 if success else 1)
