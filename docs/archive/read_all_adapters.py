import os

# Check other adapters for volume handling
adapters = [
    'data/connectors/binance_adapter.py',
    'data/connectors/bybit_adapter.py', 
    'data/connectors/cryptocompare_adapter.py',
    'data/connectors/polygon_adapter.py',
    'data/connectors/twelvedata_adapter.py',
]

results = []
for path in adapters:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
            content = fp.read()
            lines = content.split('\n')
            # Check if volume handling is present
            has_volume_fill = False
            for line in lines:
                if 'volume' in line.lower() and 'fillna' in line.lower():
                    has_volume_fill = True
                    break
            if not has_volume_fill:
                results.append(f"{path}: NO volume fillna fix found")
            else:
                results.append(f"{path}: HAS volume fillna")

for r in results:
    print(r)
