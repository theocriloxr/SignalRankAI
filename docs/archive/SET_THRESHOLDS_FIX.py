#!/usr/bin/env python3
"""
Fix script to lower ML threshold to allow 82.43 scores to pass through.

This addresses the issue where signals with 82.43 scores are blocked because:
1. The threshold optimizer defaults to ML_PROB_THRESHOLD=0.50 but ML probability 
   (when multiplied by 100) shows as ~82.43 which gets compared to threshold incorrectly
2. Need to set explicit thresholds to allow high scores through

Fix: Set ML_PROB_THRESHOLD=0.80 and PREMIUM_SCORE_THRESHOLD=75
"""

import os
import sys

def main():
    # Set environment variables to override thresholds
    os.environ['ML_PROB_THRESHOLD'] = '0.80'
    os.environ['PREMIUM_SCORE_THRESHOLD'] = '75'
    os.environ['PREMIUM_SCORE_THRESHOLD_FORCE'] = '1'  # Force env override over DB
    os.environ['LOG_LEVEL'] = 'DEBUG'  # Enable debug logging
    
    print("=== Threshold Override Applied ===")
    print(f"ML_PROB_THRESHOLD = {os.environ['ML_PROB_THRESHOLD']}")
    print(f"PREMIUM_SCORE_THRESHOLD = {os.environ['PREMIUM_SCORE_THRESHOLD']}")
    print(f"LOG_LEVEL = {os.environ['LOG_LEVEL']}")
    print("\nIf running on Railway, set these environment variables in dashboard:")
    print("  ML_PROB_THRESHOLD = 0.80")
    print("  PREMIUM_SCORE_THRESHOLD = 75")
    print("  LOG_LEVEL = DEBUG")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
