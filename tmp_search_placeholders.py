import os
import re
from pathlib import Path

patterns = [r'TODO', r'FIXME', r'placeholder', r'dummy', r'mock', r'stub', r'temp', r'fallback']
files_found = {}

for pyfile in Path('.').rglob('*.py'):
    if '.venv' in str(pyfile) or '__pycache__' in str(pyfile):
        continue
    try:
        content = pyfile.read_text(encoding='utf-8', errors='ignore')
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                if str(pyfile) not in files_found:
                    files_found[str(pyfile)] = []
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    line_num = content[:match.start()].count('\n') + 1
                    files_found[str(pyfile)].append((line_num, pattern))
    except Exception as e:
        pass

for f, matches in sorted(files_found.items())[:100]:
    print(f'\n{f}:')
    for line, pat in set(matches):
        print(f'  Line {line}: {pat}')
