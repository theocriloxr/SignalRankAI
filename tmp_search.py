#!/usr/bin/env python
import re

# Search for CallbackQueryHandler patterns in bot.py
with open("signalrank_telegram/bot.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("=== Searching for CallbackQueryHandler patterns in bot.py ===")
for i, line in enumerate(lines, 1):
    if "CallbackQueryHandler" in line or ("add_handler" in line and "callback" in line.lower()):
        print(f"Line {i}: {line.rstrip()}")

print("\n=== Searching for add_handler in bot.py ===")
for i, line in enumerate(lines, 1):
    if "application.add_handler" in line:
        print(f"Line {i}: {line.rstrip()}")
