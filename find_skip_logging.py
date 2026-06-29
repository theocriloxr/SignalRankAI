#!/usr/bin/env python3
"""Find skip-related logging in core.py"""
import re

filepath = 'engine/core.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all skip-related logging
for i, line in enumerate(content.split('\n'), 1):
    if 'skip' in line.lower() and ('logger.' in line or 'print(' in line):
        print(f'{i}: {line[:120]}')
