"""Retain unique historical documentation without restoring obsolete runtime files."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    audit = json.loads((ROOT / 'docs/release/evidence/branch-audit.json').read_text('utf-8'))
    sources = {}
    for commit in audit['unique_commits']:
        for change in commit['files']:
            status, name = change.split('\t', 1)
            if status.startswith('D') or not name.endswith(('.md', '.txt')):
                continue
            if '/' in name and not name.startswith(('docs/', 'requirements/', 'certification/')):
                continue
            content = subprocess.check_output(['git', 'show', commit['sha']+':'+name], cwd=ROOT)
            value = content.decode('utf-8-sig').replace('\r\n', '\n')
            sha = hashlib.sha256(value.encode()).hexdigest()
            current = ROOT / name
            if current.exists() and current.read_text('utf-8-sig') == value:
                continue
            key = name + ':' + sha
            record = sources.setdefault(key, {'path': name, 'sha256_lf': sha, 'text': value, 'commits': []})
            record['commits'].append(commit['sha'])
    output = {'scope': 'Unique documentation versions on divergent commits; historical source, never runtime authority.',
              'sources': sorted(sources.values(), key=lambda s: (s['path'], s['sha256_lf']))}
    (ROOT / 'docs/release/evidence/historical-sources.json').write_text(json.dumps(output, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print('Retained historical documentation versions:', len(sources))


if __name__ == '__main__':
    main()
