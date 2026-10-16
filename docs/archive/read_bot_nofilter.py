import os

# Read signalrank_telegram/bot.py around line 5649
path = 'signalrank_telegram/bot.py'
start = 5620
end = 5690

with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
    lines = fp.readlines()

print(f"=== Lines {start}-{end} of {path} ===")
for i in range(start-1, end):
    if i < len(lines):
        print(f"{i+1}: {lines[i].rstrip()}")
