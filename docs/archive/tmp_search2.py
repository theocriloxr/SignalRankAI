#!/usr/bin/env python
import re

# Search for webhook patterns in web/app.py
try:
    with open("web/app.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    print("=== Searching for webhook patterns in web/app.py ===")
    for i, line in enumerate(lines, 1):
        if "webhook" in line.lower() or "process_update" in line:
            print(f"Line {i}: {line.rstrip()}")
except FileNotFoundError:
    print("web/app.py not found")

# Search for webhook patterns in railway_main.py
try:
    with open("railway_main.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    print("\n=== Searching for webhook patterns in railway_main.py ===")
    for i, line in enumerate(lines, 1):
        if "webhook" in line.lower() or "process_update" in line or "callback" in line.lower():
            print(f"Line {i}: {line.rstrip()}")
except FileNotFoundError:
    print("railway_main.py not found")
