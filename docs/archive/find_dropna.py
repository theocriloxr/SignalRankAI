import os
import re

# Search for dropna in key files
search_in = [
    'data/indicators.py',
    'data/fetcher.py', 
    'data/providers.py',
    'signalrank_telegram/bot.py',
    'engine/realtime_outcome_tracker.py'
]

for fpath in search_in:
    if not os.path.exists(fpath):
        print(f"NOT FOUND: {fpath}")
        continue
    
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as fp:
        content = fp.read()
    
    if 'dropna' in content:
        print(f"\n=== {fpath} ===")
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if 'dropna' in line.lower():
                # Show context
                start = max(0, i-3)
                end = min(len(lines), i+2)
                for j in range(start, end):
                    marker = ">>>" if j+1 == i else "   "
                    print(f"{marker} {j+1}: {lines[j][:100]}")
                print()
