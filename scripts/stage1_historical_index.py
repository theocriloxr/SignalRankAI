"""Preserve every discoverable historical documentation blob, with secrets redacted.

Versions are historical context, not additional approved product requirements.
The original Git blob IDs allow exact provenance without republishing credentials.
"""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.secret_scan import PATTERNS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/release/evidence'


def main():
    history = subprocess.check_output(['git','log','--all','--format=commit:%H','--raw',
        '--no-abbrev','--no-renames','--diff-filter=AM','--','*.md','*.txt'],cwd=ROOT,text=True,encoding='utf-8')
    versions = {}
    commit = None
    for line in history.splitlines():
        if line.startswith('commit:'):
            commit = line[7:]
        elif line.startswith(':') and '\t' in line:
            fields, name = line.split('\t',1)
            if name.startswith('docs/release/') or ('/' in name and not name.startswith(('docs/','requirements/','certification/'))):
                continue
            blob = fields.split()[3]
            record = versions.setdefault((name,blob), {'path':name,'git_blob':blob,'commits':[]})
            if commit not in record['commits']:
                record['commits'].append(commit)
    archive = OUT/'historical-documentation.jsonl.gz'
    process = subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    records=[]
    try:
        with archive.open('wb') as raw_output, gzip.GzipFile(fileobj=raw_output,mode='wb',mtime=0,filename='') as output:
            for key in sorted(versions):
                record=versions[key]
                process.stdin.write((record['git_blob']+'\n').encode()); process.stdin.flush()
                header=process.stdout.readline().decode().split()
                if len(header)!=3 or header[1]!='blob': raise RuntimeError('Historical source blob unavailable')
                raw=process.stdout.read(int(header[2])); assert process.stdout.read(1)==b'\n'
                encoding='utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
                try: text=raw.decode(encoding)
                except UnicodeDecodeError:
                    encoding='latin-1'; text=raw.decode(encoding)
                spans=[]
                # Conservatively redact all credential-shaped assignments, even
                # fixtures. Original content remains in Git; no values are logged.
                for label,pattern in PATTERNS:
                    spans.extend((m.start(),m.end()) for m in pattern.finditer(text))
                merged=[]
                for start,end in sorted(spans):
                    if merged and start<=merged[-1][1]: merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
                    else:merged.append((start,end))
                for start,end in reversed(merged):text=text[:start]+'[CREDENTIAL-SHAPED SOURCE REDACTED]'+text[end:]
                record.update(original_sha256=hashlib.sha256(raw).hexdigest(),original_bytes=len(raw),
                    encoding=encoding,credential_shaped_redactions=len(merged),
                    archived_text_sha256=hashlib.sha256(text.encode()).hexdigest(),line_count=len(text.splitlines()))
                output.write((json.dumps({**record,'text':text},ensure_ascii=False)+'\n').encode())
                records.append(record)
    finally:
        process.stdin.close(); process.stdout.close();process.wait(timeout=15)
    index={'scope':'All distinct root/docs/requirements/certification Markdown/text versions reachable from fetched refs; historical context is not automatically an active requirement.',
        'archive':archive.relative_to(ROOT).as_posix(),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'versions':records}
    (OUT/'historical-documentation-index.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'historical_versions':len(records),'distinct_paths':len({r['path'] for r in records}),
        'redactions':sum(r['credential_shaped_redactions'] for r in records),'archive_bytes':archive.stat().st_size}))


if __name__=='__main__':main()
