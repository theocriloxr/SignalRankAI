#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
r=subprocess.run([sys.executable,"-m","alembic","heads"],check=True,capture_output=True,text=True)
heads=[line.strip() for line in r.stdout.splitlines() if line.strip()]
if len(heads)!=1: raise SystemExit(f"expected exactly one Alembic head, found {len(heads)}: {heads}")
print(heads[0])
