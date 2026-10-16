import os
import os.path

# Search for the debug message in ALL .py files
search_term = "No filtered candles"
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
                if search_term in content:
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if search_term in line:
                            results.append(f"{path}:{i}: {line[:150]}")
        except Exception:
            pass

print("All 'No filtered candles' references found:")
for r in results:
    print(r)
