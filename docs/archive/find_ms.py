import os

# Find the _ms function definition
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
                    if 'def _ms(' in line:
                        results.append(f"{path}:{i}: {line[:120]}")
                        # Show next 20 lines for context
                        for j in range(i, min(i+20, len(lines))):
                            results.append(f"  {j+1}: {lines[j].rstrip()}")
        except Exception:
            pass

print("Definition of _ms function:")
for r in results:
    print(r)
