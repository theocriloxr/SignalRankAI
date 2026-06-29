import os

# Read engine/confluence_engine.py around lines 180-210
path = 'engine/confluence_engine.py'
start = 40
end = 80

with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
    lines = fp.readlines()

print(f"=== Lines {start}-{end} of {path} ===")
for i in range(start-1, end):
    if i < len(lines):
        print(f"{i+1}: {lines[i].rstrip()}")
