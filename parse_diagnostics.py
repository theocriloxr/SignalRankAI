#!/usr/bin/env python3
"""
Parse .diagnostics/heatmap_log.jsonl and summarize per-asset gate rejections.
Shows which gates are blocking the most signals.
"""

import json
import sys
from collections import Counter
from pathlib import Path

def parse_heatmap_log(file_path: str = ".diagnostics/heatmap_log.jsonl"):
    """Parse JSONL heatmap diagnostic log and summarize rejection gates."""
    
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] {file_path} not found")
        return
    
    print(f"Parsing {file_path}...\n")
    
    all_gates = Counter()
    asset_gates = {}
    total_records = 0
    
    with open(path, 'r') as f:
        for line_no, line in enumerate(f, 1):
            try:
                record = json.loads(line.strip())
                total_records += 1
                
                asset = record.get('asset', 'UNKNOWN')
                heatmap = record.get('heatmap', {})
                empty_cycles = record.get('empty_cycles', 0)
                cycle = record.get('cycle', 0)
                
                # Track per-asset gate counts
                if asset not in asset_gates:
                    asset_gates[asset] = Counter()
                
                # Aggregate all gates
                for gate_name, count in heatmap.items():
                    all_gates[gate_name] += count
                    asset_gates[asset][gate_name] += count
                    
            except json.JSONDecodeError as e:
                print(f"[WARN] Line {line_no}: {e}")
    
    print(f"Total diagnostic records: {total_records}\n")
    print("=" * 80)
    print("TOP 15 GATES REJECTING SIGNALS (ALL ASSETS)")
    print("=" * 80)
    for gate, count in all_gates.most_common(15):
        print(f"  {gate:40s} : {count:5d} rejections")
    
    print("\n" + "=" * 80)
    print("PER-ASSET REJECTION SUMMARY (Top rejecting gates per asset)")
    print("=" * 80)
    
    # Sort assets by total rejections
    sorted_assets = sorted(asset_gates.items(), 
                          key=lambda x: sum(x[1].values()), 
                          reverse=True)
    
    for asset, gates in sorted_assets[:12]:  # Top 12 assets
        total_rejects = sum(gates.values())
        print(f"\n{asset} (Total rejections: {total_rejects})")
        top_gates = gates.most_common(5)
        for gate, count in top_gates:
            pct = (count / total_rejects * 100) if total_rejects > 0 else 0
            print(f"  ├─ {gate:35s} : {count:4d} ({pct:5.1f}%)")
    
    print("\n" + "=" * 80)
    print("INTERPRETATION GUIDE")
    print("=" * 80)
    print("""
If final_signals=0 but risk_passed>0, the blocker is in the final scoring/filtering phase:
  - 'score' gate              → signals scored too low (PREMIUM_SCORE_THRESHOLD too high)
  - 'expectancy'              → live_expectancy < 0.0 and EXPECTANCY_HARD_BLOCK_ENABLED=1
  - 'structure'               → invalid TP/SL structure or advanced filters rejected
  - 'ultra'                   → ultra quality filter rejected signal
  - 'gemini'                  → Gemini LLM review rejected signal (API cost/quality)
  - 'confluence'              → confluence direction mismatch
  
To fix:
  1. Set PREMIUM_SCORE_THRESHOLD=0 and PREMIUM_SCORE_THRESHOLD_FORCE=0 (temporary)
  2. Set GEMINI_SIGNAL_REVIEW_ENABLED=0 (disable LLM review temporarily)
  3. Set ULTRA_QUALITY_ENABLED=0 (disable ultra filter)
  4. Set EXPECTANCY_HARD_BLOCK_ENABLED=0 (disable hard expectancy block)
  5. Redeploy and watch logs for signal_stored increase
  6. Then selectively re-enable filters one by one to identify the culprit
""")

if __name__ == '__main__':
    file_path = sys.argv[1] if len(sys.argv) > 1 else ".diagnostics/heatmap_log.jsonl"
    parse_heatmap_log(file_path)
