"""Inventory UI dependencies and Telegram destinations without importing runtime services.

This proves that a declared route exists, never that an action or entitlement was
accepted. Browser and production evidence must be recorded independently.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def build() -> dict:
    tree = ast.parse((ROOT/'web/platform_api.py').read_text(encoding='utf-8'))
    routes = {}
    for node in tree.body:
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Attribute)
                    and isinstance(decorator.func.value,ast.Name) and decorator.func.value.id == 'router'
                    and decorator.args and isinstance(decorator.args[0],ast.Constant)):
                key = (decorator.func.attr.upper(),'/api/v1/platform'+str(decorator.args[0].value))
                routes[key] = {'handler':node.name,'source':f'web/platform_api.py:{node.lineno}'}
    dependencies = []
    for file in sorted((ROOT/'frontend/src').rglob('*.tsx')):
        for match in re.finditer(r'client\.(GET|POST|PUT|PATCH|DELETE)\(\s*["\']([^"\']+)["\']',file.read_text('utf-8')):
            key = match.group(1),match.group(2)
            if key not in routes:
                raise ValueError(f'Frontend dependency does not exist: {key} in {file.relative_to(ROOT)}')
            dependencies.append({'component':file.relative_to(ROOT).as_posix(),'method':key[0],
                                 'endpoint':key[1],**routes[key],
                                 'status':'IMPLEMENTED','runtime_acceptance':'NOT_PROVEN_BY_INVENTORY'})
    catalogue = next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='command_catalog')
    maps = {target.id:ast.literal_eval(node.value) for node in catalogue.body if isinstance(node,ast.Assign)
            for target in node.targets if isinstance(target,ast.Name) and target.id in {'section_views','command_views'}}
    command_tree = ast.parse((ROOT/'signalrank_telegram/command_catalog.py').read_text('utf-8'))
    commands = []
    for node in ast.walk(command_tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='CommandSpec':
            name,description,tier,section = [ast.literal_eval(arg) for arg in node.args[:4]]
            commands.append({'command':name,'description':description,'minimum_tier':tier,'section':section,
                             'retained_web_view':maps['command_views'].get(name) or maps['section_views'].get(section,'tools'),
                             'status':'IMPLEMENTED','end_to_end_parity':'NOT_PROVEN_BY_DESTINATION_MAPPING'})
    shell = (ROOT/'web/platform_app/index.html').read_text('utf-8')
    views = sorted(set(re.findall(r'id="([a-z]+)View"',shell)))
    master = json.loads((ROOT/'certification/master_requirement_registry.json').read_text('utf-8'))
    historical_routes = [entry for entry in master['entries'] if entry['section']=='16']
    return {'schema_version':'1.0','inventory_is_verification':False,
            'financial_readiness_certified':False,'backend_route_count':len(routes),
            'frontend_dependencies':dependencies,'telegram_web_destinations':commands,
            'retained_workspace_views':views,'historical_route_requirements':historical_routes,
            'cutover_mode':'Public website on Next; existing workspace retained until full parity is verified'}


def main() -> int:
    result = build()
    directory = ROOT/'docs/frontend-integration-20261012'
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'contract-inventory.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines = ['# Telegram and web destination inventory','',
             'Generated from the canonical command catalogue and backend mappings. A mapped destination is not end-to-end feature acceptance.', '',
             '| Command | Minimum tier | Section | Existing web view |','| --- | --- | --- | --- |']
    lines.extend(f"| `/{row['command']}` | {row['minimum_tier']} | {row['section']} | {row['retained_web_view']} |"
                 for row in result['telegram_web_destinations'])
    (directory/'telegram-web-matrix.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'frontend_dependencies':len(result['frontend_dependencies']),
                      'telegram_commands':len(result['telegram_web_destinations']),
                      'retained_views':len(result['retained_workspace_views']),
                      'financial_readiness_certified':False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
