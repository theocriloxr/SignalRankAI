import os

# Check yfinance_adapter.py for volume handling
path = 'data/connectors/yfinance_adapter.py'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
        content = fp.read()
        lines = content.split('\n')
        print(f"=== {path} ===")
        for i, line in enumerate(lines, 1):
            # Look for volume-related operations
            if 'volume' in line.lower():
                print(f"{i}: {line[:120]}")
            if 'dropna' in line.lower():
                print(f"{i}: {line[:120]}")
