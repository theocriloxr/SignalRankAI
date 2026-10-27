import os

# Read data/indicators.py
path = 'data/indicators.py'
start = 1
end = 60

with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
    lines = fp.readlines()

print(f"=== Lines {start}-{end} of {path} ===")
for i in range(start-1, end):
    if i < len(lines):
        print(f"{i+1}: {lines[i].rstrip()}")
