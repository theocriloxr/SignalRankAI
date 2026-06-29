import os

# Read mtf_analysis.py lines 50-90 and 160-240
path = 'engine/mtf_analysis.py'
sections = [
    (50, 90),
    (160, 240),
]

with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
    lines = fp.readlines()

for start, end in sections:
    print(f"\n=== Lines {start}-{end} of {path} ===")
    for i in range(start-1, end):
        if i < len(lines):
            print(f"{i+1}: {lines[i].rstrip()}")
