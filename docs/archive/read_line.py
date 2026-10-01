import os

# Read around line 5649 in bot.py
path = 'signalrank_telegram/bot.py'
start = 5600
end = 5700

with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
    lines = fp.readlines()

print(f"=== Lines {start}-{end} of {path} ===")
for i, line in enumerate(lines[start-1:end], start):
    print(f"{i}: {line.rstrip()}")
