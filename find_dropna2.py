import os

# Search ALL .py files for dropna
results = []
for root, dirs, files in os.walk('.'):
    # Skip hidden dirs and pycache
    dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
    for f in files:
        if not f.endswith('.py'):
            continue
        path = os.path.join(root, f)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
                if 'dropna' in content.lower():
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if 'dropna' in line.lower():
                            results.append(f"{path}:{i}: {line[:120]}")
        except Exception:
            pass

print("All dropna references found:")
for r in results:
    print(r)
