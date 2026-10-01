import os

# Read current state of yfinance_adapter.py
path = 'data/connectors/yfinance_adapter.py'
start = 1
end = 100

with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
    lines = fp.readlines()

print(f"=== Lines {start}-{end} of {path} ===")
for i in range(start-1, end):
    if i < len(lines):
        print(f"{i+1}: {lines[i].rstrip()}")
