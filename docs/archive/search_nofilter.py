import os
import re

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
                    # Find line number
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if search_term in line:
                            results.append(f"{path}:{i}: {line[:120]}")
                            break
        except Exception as e:
            pass

if results:
    print("Found files with search term:")
    for r in results:
        print(r)
else:
    print("Term not found. Let's also search for just 'filtered candles'..")
    
    # Try variant
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        for f in files:
            if not f.endswith('.py'):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                    content = fp.read()
                    if 'filtered candles' in content:
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if 'filtered candles' in line:
                                print(f"{path}:{i}: {line[:120]}")
                                break
            except Exception:
                pass
