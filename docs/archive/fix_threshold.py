#!/usr/bin/env python3
"""Script to fix the leftover comment in core.py"""

with open('engine/core.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the problematic line and fix
new_lines = []
for i, line in enumerate(lines):
    if "_threshold_optimizer = _FallbackThresholdOptimizer()" in line and "# Track" in line:
        # Split the line
        new_lines.append(line.replace("# Track", "\n# Track"))
    else:
        new_lines.append(line)

with open('engine/core.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
    
print("Fixed!")
