import os
import re
from pathlib import Path

def collect_env_vars(root: Path):
    pat_getenv = re.compile(r"os\.getenv\(\s*['\"]([A-Z0-9_]+)['\"]")
    pat_environ_get = re.compile(r"os\.environ\.get\(\s*['\"]([A-Z0-9_]+)['\"]")
    pat_environ_index = re.compile(r"os\.environ\[\s*['\"]([A-Z0-9_]+)['\"]\s*\]")
    vars_found = set()
    for p in root.rglob('*.py'):
        try:
            txt = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for pat in (pat_getenv, pat_environ_get, pat_environ_index):
            for m in pat.finditer(txt):
                vars_found.add(m.group(1))
    return sorted(vars_found)

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    all_vars = collect_env_vars(root)
    missing = [v for v in all_vars if v not in os.environ]
    print(f"TOTAL VARS: {len(all_vars)}")
    print(f"MISSING VARS: {len(missing)}")
    print("LIST MISSING:")
    for v in missing:
        print(v)
