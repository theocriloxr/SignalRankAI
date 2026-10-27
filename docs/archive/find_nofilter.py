import os

# Search for the exact message "No filtered candles" in all .py files
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
                if 'No filtered candles' in content or 'no filtered candle' in content.lower():
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if 'no filtered' in line.lower():
                            results.append(f"{path}:{i}: {line[:120]}")
        except Exception:
            pass

print("Files containing 'No filtered candles':")
for r in sorted(set(results)):
    print(r)
