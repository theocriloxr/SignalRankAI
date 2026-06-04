import ast
import sys

try:
    with open('data/fetcher.py', 'r') as f:
        source = f.read()
    ast.parse(source)
    print("SUCCESS: No syntax errors found in data/fetcher.py")
    sys.exit(0)
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    print(f"  Line {e.lineno}: {e.text}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
