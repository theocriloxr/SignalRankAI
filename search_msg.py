import os
import re

pattern = re.compile(r'No filtered candles', re.IGNORECASE)
files = []

for root, dirs, filenames in os.walk('.'):
    for f in filenames:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', encoding='utf-8') as fp:
                    content = fp.read()
                    if pattern.search(content):
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if pattern.search(line):
                                print(f'{path}:{i}: {line[:150]}')
            except Exception as e:
                print(f'Error: {path} - {e}')
