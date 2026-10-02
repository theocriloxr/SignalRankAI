import os
import re

# Find all usages of fetch_yahoo_candles and yfinance
results = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
    for f in files:
        if not f.endswith('.py'):
            continue
        path = os.path.join(root, f)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
                if 'fetch_yahoo_candles' in content or 'yfinance_adapter.get_candles' in content:
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if 'fetch_yahoo_candles' in line or 'yfinance_adapter' in line:
                            results.append(f"{path}:{i}: {line[:100]}")
        except Exception:
            pass

print("Files using fetch_yahoo_candles or yfinance_adapter:")
for r in sorted(set(results)):
    print(r)
