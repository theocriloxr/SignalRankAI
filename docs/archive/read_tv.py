import os

# Find files in data/connectors/ that handle candle data
path = 'data/connectors'
try:
    files = os.listdir(path)
    print(f"Files in {path}:")
    for f in files:
        if f.endswith('.py'):
            print(f"  {f}")
except Exception as e:
    print(f"Error: {e}")

# Also check data/alternative_providers.py
alt_path = 'data/alternative_providers.py'
if os.path.exists(alt_path):
    print(f"\n=== Checking {alt_path} ===")
    with open(alt_path, 'r', encoding='utf-8', errors='ignore') as fp:
        content = fp.read()
        # Check if it has volume handling
        if 'volume' in content.lower() or 'dropna' in content.lower():
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                if 'volume' in line.lower() and ('nan' in line.lower() or 'fillna' in line.lower()):
                    print(f"{i}: {line[:100]}")
                elif 'dropna' in line.lower():
                    print(f"{i}: {line[:100]}")
