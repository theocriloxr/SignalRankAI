#!/usr/bin/env python
"""Check command_access.py has valid syntax"""
import py_compile
import sys

try:
    py_compile.compile("signalrank_telegram/command_access.py", doraise=True)
    print("✓ signalrank_telegram/command_access.py has valid syntax")
except py_compile.PyCompileError as e:
    print(f"✗ Syntax error: {e}")
    sys.exit(1)
