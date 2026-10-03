#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, shlex, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"certification"/"release_manifest.yaml"
def load_manifest():
    raw=MANIFEST.read_text(encoding="utf-8")
    try: data=json.loads(raw)
    except json.JSONDecodeError:
        try: import yaml
        except Exception as exc: raise RuntimeError("manifest must be JSON-compatible YAML without PyYAML") from exc
        data=yaml.safe_load(raw)
    if not isinstance(data,dict) or not isinstance(data.get("gates"),list): raise RuntimeError("invalid release manifest")
    return data
def validate(data):
    seen=set()
    for gate in data["gates"]:
        gid=str(gate.get("id") or "").strip()
        if not gid or gid in seen: raise RuntimeError(f"invalid or duplicate gate id: {gid!r}")
        seen.add(gid)
        if gate.get("required") and not str(gate.get("command") or "").strip(): raise RuntimeError(f"required gate {gid} has no command")
        if not isinstance(gate.get("environments"),list) or not gate["environments"]: raise RuntimeError(f"gate {gid} requires environments[]")
        command = str(gate.get("command") or "").strip()
        if command.startswith("manual:"):
            if not gate.get("evidence_requirements"):
                raise RuntimeError(f"manual gate {gid} requires explicit evidence requirements")
            continue
        # Validate local command inputs without executing a gate or requiring
        # every platform-specific tool to be installed on the validation host.
        current_dir = ROOT
        tokens = shlex.split(command)
        for index, token in enumerate(tokens):
            if token == "cd" and index + 1 < len(tokens):
                current_dir = (current_dir / tokens[index + 1]).resolve()
                if not current_dir.is_relative_to(ROOT) or not current_dir.is_dir():
                    raise RuntimeError(f"gate {gid} has invalid working directory")
                continue
            candidate = token.split("::", 1)[0]
            if candidate.startswith("-") or Path(candidate).suffix not in {".py", ".sh", ".txt", ".json"}:
                continue
            if index and tokens[index - 1] in {"--output", "--output-dir"}:
                continue
            path = (current_dir / candidate).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                raise RuntimeError(f"gate {gid} references missing or external input: {candidate}")
def main():
    p=argparse.ArgumentParser(); p.add_argument("--environment",default="ci"); p.add_argument("--group"); p.add_argument("--gate",action="append",default=[]); p.add_argument("--validate",action="store_true"); p.add_argument("--list",action="store_true"); a=p.parse_args()
    data=load_manifest(); validate(data)
    selected=[g for g in data["gates"] if a.environment in {str(v) for v in g.get("environments",[])} and (not a.group or g.get("group")==a.group) and (not a.gate or g.get("id") in set(a.gate)) and g.get("required",False)]
    if a.list:
        for g in selected: print(f"{g['id']}: {g['command']}")
        return 0
    if a.validate and not a.group and not a.gate:
        print(f"release manifest valid: {len(data['gates'])} gates"); return 0
    if not selected and (a.group or a.gate): raise RuntimeError("no required gates matched selection")
    for g in selected:
        cmd=str(g["command"])
        if cmd.startswith("manual:"): raise RuntimeError(f"manual gate cannot be auto-certified: {g['id']}")
        print(f"::group::{g['id']} - {g.get('description','')}",flush=True)
        cp=subprocess.run(cmd,cwd=ROOT,shell=True,env=os.environ.copy())
        print("::endgroup::",flush=True)
        if cp.returncode: print(f"release gate failed: {g['id']} exit={cp.returncode}",file=sys.stderr); return cp.returncode
    return 0
if __name__=="__main__": raise SystemExit(main())
