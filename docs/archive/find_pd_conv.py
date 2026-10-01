import os

# Find where candles are converted to pandas DataFrames
patterns = [
    'pd.DataFrame(candles)',
    'pd.DataFrame(data)',
    'df = pd.DataFrame',
]

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
                for pat in patterns:
                    if pat in content:
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if pat in line:
                                results.append(f"{path}:{i}: {line[:100]}")
        except Exception:
            pass

print("Places where candles are converted to DataFrames:")
for r in sorted(set(results)):
    print(r)
