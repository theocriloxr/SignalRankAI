import os

# Find ALL .dropna() calls without subset parameter
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
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    # Look for .dropna( NOT followed by subset
                    if '.dropna(' in line and 'subset' not in line:
                        results.append(f"{path}:{i}: {line[:120]}")
        except Exception:
            pass

print("ALL .dropna() calls WITHOUT subset parameter:")
for r in results:
    print(r)
