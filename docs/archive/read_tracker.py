import os

# Read around lines 330-350 and 630-650 in core/trade_tracker.py
path = 'core/trade_tracker.py'
lines_to_show = [
    (330, 345),
    (630, 650),
]

with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
    lines = fp.readlines()

for start, end in lines_to_show:
    print(f"\n=== Lines {start}-{end} of {path} ===")
    for i in range(start-1, end):
        if i < len(lines):
            print(f"{i+1}: {lines[i].rstrip()}")
