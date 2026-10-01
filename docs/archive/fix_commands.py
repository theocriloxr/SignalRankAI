#!/usr/bin/env python3
"""Fix the commands.py indentation issue."""

import os

file_path = 'signalrank_telegram/commands.py'

# Read the file
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the problem lines (around 179-206)
# We need to remove the old code that starts with "}" around line 180

# Find the line with just "}" that doesn't belong
problem_start = None
for i, line in enumerate(lines):
    if i >= 178 and i <= 210:  # Search area
        stripped = line.strip()
        if stripped == '}' or stripped.startswith('}'):
            problem_start = i
            break

if problem_start is not None:
    print(f"Found problem at line {problem_start + 1}")
    print(f"Content: {repr(lines[problem_start])}")
    
    # Find where the problem ends (look for next sensible code)
    problem_end = problem_start
    for i in range(problem_start + 1, min(problem_start + 35, len(lines))):
        line = lines[i].strip()
        if line.startswith('from .formatter import format_signal'):
            problem_end = i - 1
            break
    
    print(f"Problem range: lines {problem_start + 1} to {problem_end + 1}")
    
    # Remove the problem lines
    del lines[problem_start:problem_end+1]
    
    # Insert the correct code at problem_start
    correct_code = [
        "\n",
        "\t# PREMIUM/VIP: detailed formatting per tier\n",
        "\tfrom .formatter import format_signal\n",
        "\tfor s in unresolved_signals[:10]:\n",
    ]
    
    for j, code_line in enumerate(correct_code):
        lines.insert(problem_start + j, code_line)
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"Fixed! Removed {problem_end - problem_start + 1 - len(correct_code)} lines of bad code")
    print("File updated successfully")
else:
    print("Could not find the problem area")
