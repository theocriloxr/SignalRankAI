#!/usr/bin/env python3
"""Script to fix the whitespace issues in core.py"""

with open('engine/core.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and remove lines that are just extra whitespace
new_lines = []
skip_next = False
for i, line in enumerate(lines):
    # Skip lines that are just whitespace inside the exception block
    stripped = line.strip()
    if stripped == '' and i > 140 and i < 170:
        # Check indent - if it has random 5 spaces, skip it
        if line.startswith('     ') and not line.startswith('        '):
            continue
    
    new_lines.append(line)

with open('engine/core.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
    
print("Fixed whitespace!")
