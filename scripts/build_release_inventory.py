"""Deterministic Stage 1 source and interface accounting, without service imports.

Inventory is not acceptance. Historical PASS labels are retained as source text,
never converted to VERIFIED. Missing reviewed dispositions fail acceptance.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/release"
STATUSES = {"IMPLEMENTED", "VERIFIED", "BLOCKED_EXTERNAL", "FAILED", "NOT_IMPLEMENTED", "NOT_APPLICABLE"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket"}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def tracked() -> list[str]:
    return sorted(set(subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                              cwd=ROOT, encoding="utf-8").splitlines()))


def identifier(kind: str, key: str) -> str:
    return "SR-" + kind + "-" + digest(key)[:16]


def row(kind: str, key: str, source: str, title: str, component: str, implementation: str,
        verification: str, status: str = "IMPLEMENTED", **extra) -> dict:
    return {"id": identifier(kind, key), "kind": kind, "source": source, "requirement": title,
            "current_implementation": implementation, "responsible_component": component,
            "verification_method": verification, "status": status, "test_evidence": [],
            "associated_commit": "BASELINE", **extra}


def document_sources(paths: list[str]) -> tuple[list[dict], list[dict]]:
    documents, rows = [], []
    for name in paths:
        p = ROOT / name
        if not p.is_file() or p.suffix.lower() not in {".md", ".txt"}:
            continue
        if name.startswith(("docs/release/", "frontend/node_modules/", "mobile/node_modules/")):
            continue
        # Product/source documentation, including superseded reports and TODOs.
        if "/" in name and not name.startswith(("docs/", "requirements/", "certification/")):
            continue
        raw = p.read_bytes()
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        text = raw.decode(encoding)
        lines = text.splitlines()
        formal = name.startswith("docs/specs/") or "Master_Blueprint" in name or "MASTER_DIRECTIVE" in name
        classification = "REQUIRED_SOURCE" if formal else "HISTORICAL_CONTEXT_REQUIRES_RECONCILIATION"
        bounds = [i for i, line in enumerate(lines) if re.match(r"^(#{1,6} .+|\d{1,3}\. [A-Z].+)$", line)]
        bounds = sorted(set([0, *bounds, len(lines)]))
        documents.append({"path": name, "sha256_lf": digest(text.replace("\r\n", "\n")), "encoding": encoding,
                          "line_count": len(lines), "classification": classification,
                          "section_count": len(bounds) - 1})
        for start, end in zip(bounds, bounds[1:]):
            body = "\n".join(lines[start:end])
            if not body.strip(): continue
            substantive = [{"line": i+1, "text": lines[i]} for i in range(start,end)
                           if lines[i].strip() and not re.fullmatch(r"[-=| :`]+", lines[i])]
            key = name + f":{start+1}"
            rows.append(row("SOURCE", key, key, next((l.strip('# ') for l in lines[start:end] if l.strip()), name),
                "Architecture / source-specific implementation review",
                "Original source retained in full. Clause-level implementation and acceptance are not established by this index.",
                "Review every retained clause against active call paths, then attach behavioral evidence to its ID.",
                "FAILED", classification=classification, failure_reason="CLAUSE_ACCEPTANCE_NOT_ESTABLISHED",
                source_sha256=digest(body), line_start=start+1, line_end=end, text=body, clauses=substantive))
    return documents, rows


def literal(node, default=None):
    try: return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError): return default


def python_interfaces(paths: list[str]) -> list[dict]:
    rows = []
    for name in paths:
        if not name.endswith(".py") or not name.startswith(("web/", "paystack/", "payments/", "admin/")):
            continue
        tree = ast.parse((ROOT/name).read_text("utf-8"))
        prefixes = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name) and node.value.func.id == "APIRouter":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            prefixes[target.id] = next((literal(k.value, "") for k in node.value.keywords if k.arg=="prefix"), "")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
            for deco in node.decorator_list:
                if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) and
                        deco.func.attr in HTTP_METHODS and deco.args): continue
                path = literal(deco.args[0])
                if not isinstance(path, str): continue
                owner = ast.unparse(deco.func.value)
                prefix = prefixes.get(owner, "")
                # Mounts on canonical web.app, not the standalone web.api app.
                if name == "web/platform_api.py": mounts = ["/api/v1"+prefix]
                elif name == "web/api.py": mounts = ["/api/v1", ""]
                else: mounts = [prefix]
                for mount in mounts:
                    endpoint = deco.func.attr.upper()+" "+mount+path
                    rows.append(row("ENDPOINT", name+":"+endpoint, f"{name}:{node.lineno}", endpoint,
                        name+"::"+node.name, "Declared handler; runtime mounting/auth/ownership and side effects require acceptance.",
                        "Test authenticated/anonymous, roles, cross-user ownership, invalid input, retries and failure recovery.",
                        endpoint=mount+path, method=deco.func.attr.upper(), handler=node.name,
                        dependencies=sorted(set(re.findall(r"Depends\(([^)]+)\)", ast.unparse(node.args))))))
    return rows


def client_interfaces(paths: list[str]) -> list[dict]:
    rows = []
    for name in paths:
        if name.startswith("frontend/src/app/") and name.endswith(("/page.tsx", "/route.ts")):
            route = "/"+str(Path(name).parent.relative_to("frontend/src/app")).replace("\\", "/").replace(".", "")
            route = re.sub(r"/\([^/]+\)", "", route)
            rows.append(row("WEB", name, name, route, "frontend / Next.js",
                "Page or route source exists; workspace mode and backend proxy determine the effective owner.",
                "Browser journey in both next and legacy workspace modes; returning PWA, keyboard, mobile and authorization.", route=route))
    # File-system catch-alls are declarations, not a route-by-route inventory.
    # Expand the actual allowlists while retaining their declaration rows above.
    public_source = "frontend/src/app/[slug]/page.tsx"
    public_names = set()
    for name in (public_source, "frontend/src/lib/public-pages.ts"):
        public_names.update(re.findall(r"^  ([a-z][a-z0-9-]*): (?:\{|page\()", (ROOT/name).read_text("utf-8"), re.M))
    workspace_source = "frontend/src/app/app/[...slug]/page.tsx"
    workspace_text = (ROOT/workspace_source).read_text("utf-8")
    section_set = re.search(r"const sections = new Set\(\[(.*?)\]\)", workspace_text, re.S)
    if not public_names or not section_set:
        raise ValueError("Client route allowlist syntax changed; update the inventory extractor")
    workspace_names = re.findall(r'"([a-z]+)"', section_set.group(1))
    concrete = [("/"+name, public_source) for name in sorted(public_names)]
    concrete += [("/app/"+name, workspace_source) for name in sorted(workspace_names)]
    if 'section === "signals" && slug.length === 2' in workspace_text:
        concrete.append(("/app/signals/{signal_id}", workspace_source))
    for route, source in concrete:
        rows.append(row("WEB", source+":"+route, source, route, "frontend / Next.js route allowlist",
            "Concrete accepted route. /privacy is owned by the recovered backend policy through the proxy; workspace mode selects Next or retained app ownership.",
            "Exercise this route in its deployed workspace mode, including anonymous, entitled and cross-user access, empty/error and responsive states.",
            route=route, route_kind="EXPANDED_ALLOWLIST"))
    shell = (ROOT/"web/platform_app/index.html").read_text("utf-8")
    for view in sorted(set(re.findall(r'id="([A-Za-z]+)View"',shell))):
        rows.append(row("WEB", "legacy:"+view, "web/platform_app/index.html", "/app?view="+view,
            "web/platform_app/app.js", "Retained workstation view; canonical platform API owns account data.",
            "Load view and exercise its reads/writes, role restrictions, expired session and failure feedback.", route="/app?view="+view))
    native = (ROOT/"mobile/App.tsx").read_text("utf-8")
    screens = re.search(r"type Screen = (.*?);", native)
    if not screens:
        raise ValueError("Native Screen union changed; update the inventory extractor")
    for view in sorted(set(re.findall(r"'([^']+)'", screens.group(1)))):
        rows.append(row("MOBILE", view, "mobile/App.tsx", view, "mobile / Expo",
            "Native screen source exists; device/build/OS behavior remains separate acceptance.",
            "Type check, JS export and installed iOS/Android journey with device credential and push tests."))
    return rows


def catalogue_interfaces() -> list[dict]:
    rows = []
    commands = json.loads((ROOT/"requirements/command_registry.yaml").read_text("utf-8"))["commands"]
    for c in commands:
        name = c["canonical_name"]
        rows.append(row("COMMAND", name, "; ".join(c["sources"]), "/"+name,
            "signalrank_telegram::"+c["handler"], "Registered command; minimum tier "+c["minimum_tier"]+"; role "+c["role_scope"],
            "Registry/runtime match; positive/negative role and account scope; real dedicated-bot round trip.",
            minimum_tier=c["minimum_tier"], role_scope=c["role_scope"]))
    callbacks = json.loads((ROOT/"requirements/callback_registry.yaml").read_text("utf-8"))["callbacks"]
    for c in callbacks:
        rows.append(row("CALLBACK", c["name"], c["source"], c["pattern"], c["handler"],
            "Registered callback pattern; untrusted payload requires ownership and role validation.",
            "Runtime registration, stale/replayed/cross-user callback rejection and immediate acknowledgement.", capabilities=c))
    providers = json.loads((ROOT/"requirements/provider_registry.yaml").read_text("utf-8"))["providers"]
    for p in providers:
        rows.append(row("PROVIDER", p["key"], "data/provider_catalog.py", p["display_name"], p.get("connector_module") or "Unimplemented connector",
            "Catalogue declaration; "+", ".join(p["asset_classes"])+"; credentials/entitlements/current freshness not certified here.",
            "Exact-environment provider and market-class certification using observed timestamps and eligible sessions.",
            "IMPLEMENTED" if p.get("connector_module") else "NOT_IMPLEMENTED", capabilities=p))
    tree = ast.parse((ROOT/"services/broker_connections.py").read_text("utf-8"))
    catalogue = next(literal(n.value) for n in tree.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=="_PLATFORM_CATALOG")
    for broker in catalogue:
        ready = broker["execution_adapter"]=="ready"
        rows.append(row("BROKER", broker["platform"], "services/broker_connections.py::_PLATFORM_CATALOG", broker["name"],
            "services/broker_signal_router.py / execution/service.py",
            "Catalogue adapter state: "+broker["execution_adapter"]+". Connection support is not permission or execution evidence.",
            "Owned account identity; explicit authorization; order/modify/partial-fill/close/restart/reconciliation, loss-limit and kill-switch demo evidence.",
            "IMPLEMENTED" if ready else "NOT_IMPLEMENTED", capabilities=broker))
    return rows


def preserved_registries() -> list[dict]:
    rows = []
    for r in json.loads((ROOT/"requirements/requirements.yaml").read_text("utf-8"))["requirements"]:
        rows.append(row("V7", r["id"], "; ".join(r["source_references"]), r["statement"],
            "; ".join(r["implementation_modules"]), "Historical mapping: "+r["title"]+". Fresh acceptance remains required.",
            "; ".join(r["acceptance_criteria"]), "FAILED", historical_id=r["id"], historical_mapping=r))
    for r in json.loads((ROOT/"certification/completion_matrix.json").read_text("utf-8"))["entries"]:
        a=r["acceptance"]
        rows.append(row("PRESERVED", r["id"], r["source"]+":"+str(r["line_start"]), r["heading"],
            "; ".join(a["canonical_paths"]) or "Source-specific acceptance review",
            a["current_behavior"], "; ".join(a["missing_acceptance"]) or "Revalidate source-specific acceptance at the current baseline.",
            "BLOCKED_EXTERNAL" if a["status"]=="BLOCKED_EXTERNAL" else "FAILED",
            historical_id=r["id"], source_sha256=r["source_sha256"], text=r["text"],
            subrequirements=r["subrequirements"], historical_acceptance=a))
    history=OUT/"evidence/historical-sources.json"
    for r in json.loads(history.read_text("utf-8"))["sources"]:
        rows.append(row("HISTORY", r["path"]+":"+r["sha256_lf"], r["commits"][0]+":"+r["path"],
            r["path"], "Historical branch reconciliation", "Historical source retained verbatim; may be superseded by current specifications.",
            "Reconcile historical clauses; do not reactivate stale runtime policy or infer previous PASS claims.",
            "FAILED", classification="HISTORICAL_CONTEXT_REQUIRES_RECONCILIATION", historical_source=r))
    for filename,kind in [("github-issues.jsonl","ISSUE"),("github-pulls.jsonl","PR")]:
        for line in (OUT/"evidence"/filename).read_text("utf-8-sig").splitlines():
            r=json.loads(line)
            rows.append(row(kind, str(r["number"]), r.get("url") or r.get("html_url") or f"https://github.com/theocriloxr/SignalRankAI/{'issues' if kind=='ISSUE' else 'pull'}/{r['number']}",
                r["title"], "Repository change history", "Issue/PR state is historical metadata, not functional acceptance.",
                "Trace requested behavior to its merge/change and current acceptance tests; closed does not mean VERIFIED.",
                "FAILED", classification="HISTORICAL_CONTEXT_REQUIRES_RECONCILIATION", historical_record=r))
    historical_index = json.loads((OUT/"evidence/historical-documentation-index.json").read_text("utf-8"))
    for r in historical_index["versions"]:
        rows.append(row("HISTORICAL_VERSION", r["path"]+":"+r["git_blob"], r["commits"][0]+":"+r["path"],
            r["path"], "Historical specification and source review",
            "Historical version retained in the indexed archive; original Git provenance retained. Credential-shaped material is redacted.",
            "Reconcile changed/removed clauses against current requirements and implementation; superseded reports are not acceptance.",
            "FAILED", classification="HISTORICAL_CONTEXT_REQUIRES_RECONCILIATION", historical_record=r,
            archive=historical_index["archive"]))
    return rows


def effective_endpoints() -> list[dict]:
    result=[]
    schema=json.loads((ROOT/"openapi.json").read_text("utf-8"))
    for path, methods in sorted(schema["paths"].items()):
        for method, operation in sorted(methods.items()):
            if method not in HTTP_METHODS: continue
            result.append(row("API", method+" "+path, "openapi.json::paths::"+path, method.upper()+" "+path,
                operation.get("operationId", "web.app"), "Mounted in the generated canonical application schema; auth and behavior require separate tests.",
                "OpenAPI regeneration parity plus actual request/ownership/side-effect and failure-path tests.",
                endpoint=path, method=method.upper(), operation=operation))
    return result


def strategy_interfaces(paths: list[str]) -> list[dict]:
    rows = []
    for name in paths:
        if not name.endswith(".py") or not name.startswith(("strategies/", "engine/adaptive/components/")):continue
        tree = ast.parse((ROOT/name).read_text("utf-8"))
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and not node.name.startswith("_"):
                if name.endswith(("helpers.py","base.py","capabilities.py")):continue
                rows.append(row("STRATEGY_CALLABLE", name+":"+node.name, f"{name}:{node.lineno}", node.name,
                    name, "Declared strategy/component callable; dispatch, asset/timeframe compatibility and quantitative validity require review.",
                    "Replay real captured inputs; geometry/causality/fees/slippage; supported asset/timeframe/regime matrix; OOS, walk-forward and forward shadow acceptance."))
    for group in ["trend","momentum","volatility","structure","liquidity","fibonacci","tradingview","stock"]:
        rows.append(row("STRATEGY",group,"strategies/capabilities.py::CAPABILITY_MATRIX",group,
            "strategies/__init__.py::run_all_strategies", "Declared strategy family. Stock is equity-only, 15m/1h/4h/1d; other families declare all canonical asset classes and six engine timeframes.",
            "Verify dispatcher selection, profile eligibility, causal replay and independent strategy/regime/asset/timeframe performance."))
    for tf in ["1m","5m","15m","1h","4h","1d"]:
        rows.append(row("TIMEFRAME",tf,"strategies/capabilities.py::ALL_TIMEFRAMES",tf,"strategies/capabilities.py / data/provider_catalog.py",
            "Declared engine strategy capability. Provider-specific coverage and profile eligibility may be narrower.",
            "Closed-bar, session/calendar, freshness, resampling and provider/strategy compatibility tests."))
    return rows


def escape(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def build() -> dict:
    paths = tracked()
    sources, requirements = document_sources(paths)
    requirements += preserved_registries()
    requirements += json.loads((OUT/"canonical_requirements.json").read_text("utf-8"))["requirements"]
    interfaces = python_interfaces(paths)+effective_endpoints()+client_interfaces(paths)+catalogue_interfaces()+strategy_interfaces(paths)
    baseline = json.loads((OUT/"baseline.json").read_text("utf-8"))
    for entry in requirements+interfaces:
        if entry["associated_commit"] == "BASELINE": entry["associated_commit"] = baseline["code_baseline"]
        if entry["status"] not in STATUSES: raise ValueError("Invalid requirement status: "+entry["id"])
        if entry["status"] == "VERIFIED": raise ValueError("This inventory does not certify acceptance; use retained scoped evidence receipts before adding a verified disposition")
    if len({r["id"] for r in requirements+interfaces}) != len(requirements+interfaces):
        raise ValueError("Duplicate requirement/interface IDs")
    return {"schema_version":1,"status_vocabulary":sorted(STATUSES),"baseline":baseline,
            "inventory_is_verification":False,"source_policy":"Historical statements and examples are context, not new permission or independently validated obligations. Specific current requirements supersede conflicting old architecture claims; no source text is discarded.",
            "summary":{"documents":len(sources),"requirements_and_source_sections":len(requirements),"source_clauses":sum(len(r.get("clauses",[])) for r in requirements),
                       "interfaces":dict(Counter(r["kind"] for r in interfaces))},
            "sources":sources,"requirements":requirements,"interfaces":interfaces}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--check",action="store_true");args=parser.parse_args()
    data=build()
    rows=["# Requirements traceability", "", "Generated by `python -m scripts.build_release_inventory`. Complete source text, clauses, hashes and all required fields are in [requirements.json](requirements.json).", "",
          "`FAILED` on a source section means its clause-specific acceptance review has not passed; it does not assert absent functionality. `IMPLEMENTED` on an interface means a declaration exists, not end-to-end verification. No historical report is promoted to VERIFIED. Source rows include historical context that may be superseded, contradictory or optional and must not be treated as new user requirements.", "",
          "| ID | Source | Requirement / interface | Current implementation | Component | Status | Verification method | Evidence | Associated commit |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in data["requirements"]+data["interfaces"]:
        rows.append("| "+" | ".join(escape(v) for v in [r["id"],r["source"],r["requirement"][:180],r["current_implementation"],r["responsible_component"],r["status"],r["verification_method"],"; ".join(r["test_evidence"]) or "None claimed",r["associated_commit"]])+" |")
    outputs={"requirements.json":json.dumps(data,indent=2,ensure_ascii=False)+"\n","REQUIREMENTS_TRACEABILITY.md":"\n".join(rows)+"\n"}
    for name,text in outputs.items():
        path=OUT/name
        if args.check:
            if not path.is_file() or path.read_text("utf-8")!=text:
                raise SystemExit("Release inventory stale: "+name)
        else:path.write_text(text,encoding="utf-8",newline="\n")
    print(json.dumps(data["summary"]))
    return 0


if __name__=="__main__":raise SystemExit(main())
