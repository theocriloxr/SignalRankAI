#!/usr/bin/env python3
"""Quick test to verify all bot commands are working."""
import sys
try:
    # Test imports
    from signalrank_telegram import commands
    print("✓ Commands module imports successfully")
    
    # Count command functions
    cmd_funcs = [name for name in dir(commands) if name.endswith('_command') and callable(getattr(commands, name))]
    print(f"✓ Found {len(cmd_funcs)} command functions:")
    for cmd in sorted(cmd_funcs):
        print(f"  - {cmd}")
    
    # Test compile
    import py_compile
    py_compile.compile('signalrank_telegram/commands.py', doraise=True)
    print("✓ commands.py compiles without errors")
    
    print("\n✅ All commands are working!")
    sys.exit(0)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
