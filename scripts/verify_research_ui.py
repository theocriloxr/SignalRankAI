"""Operator research browser checks against an owned synthetic local fixture."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(os.environ['RESEARCH_BROWSER_OUTPUT_DIR']).resolve()
out.mkdir(parents=True, exist_ok=True)
base = os.environ['RESEARCH_BROWSER_BASE_URL']
from urllib.parse import urlparse
if os.environ.get('APP_ENV') != 'test' or urlparse(base).hostname not in {'127.0.0.1', 'localhost'}:
    raise RuntimeError('browser evidence requires a local test server')
report = {'git_sha': os.environ['BROWSER_CANDIDATE_SHA'], 'candidate_dirty': os.environ['BROWSER_CANDIDATE_DIRTY'] == '1',
          'scope': 'LOCAL_HTTP_POSTGRES_SYNTHETIC_OPERATOR_EVIDENCE', 'native_device_tested': False, 'checks': []}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        for label, viewport in [('desktop', {'width': 1440, 'height': 1000}), ('mobile', {'width': 390, 'height': 844})]:
            for theme in ('dark', 'light'):
                context = browser.new_context(viewport=viewport, color_scheme=theme)
                page = context.new_page()
                errors = []
                requests = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: requests.append(request.url))
                page.goto(base + '/app')
                page.wait_for_load_state('networkidle')
                page.locator('#loginForm [name=email]').fill('research-admin@example.test')
                page.locator('#loginForm [name=password]').fill('LocalDrill-Only-20261003!')
                page.locator('#loginForm button[type=submit]').click()
                page.locator('#appShell').wait_for(state='visible')
                page.wait_for_load_state('networkidle')
                page.evaluate("setTheme('" + theme + "')")
                if label == 'mobile':
                    page.locator('#viewSwitcher').select_option('ops')
                else:
                    page.locator('#sessionNav [data-view=ops]').click()
                page.locator('#operatorResearch').get_by_text('2 trials · 2 terminal results').wait_for()
                assert page.locator('#operatorKillSwitchOn').is_hidden()
                assert page.locator('#operatorKillSwitchOff').is_hidden()
                assert not any('/operator/maintenance' in url for url in requests), 'admin must not request owner-only maintenance'
                page.locator('.research-experiment').filter(has_text='Synthetic strategy').locator('summary').click()
                assert page.locator('#operatorResearch').get_by_text('Promotion not certified').count() == 2
                assert 'FAILED' in page.locator('#operatorResearch').inner_text()
                assert 'UNVERIFIED' in page.locator('#operatorResearch').inner_text()
                assert page.evaluate('window.injected') is None
                assert page.locator('#operatorResearch img').count() == 0, 'hypothesis text must not execute HTML'
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'page must fit viewport'
                page.locator('#toast').wait_for(state='hidden')
                page.screenshot(path=str(out / f'{label}-{theme}.png'), full_page=True)
                page.locator('#operatorResearch').screenshot(path=str(out / f'research-{label}-{theme}.png'))
                page.locator('#operatorResearchAsset').fill('AAPL')
                page.locator('#refreshOperatorResearch').click()
                page.locator('#operatorResearch').get_by_text('No recorded experiments', exact=True).wait_for()
                page.route('**/api/v1/platform/operator/research**', lambda route: route.fulfill(status=503,
                    content_type='application/json', body='{"detail":"Synthetic service unavailable"}'))
                page.locator('#refreshOperatorResearch').click()
                page.locator('#operatorResearch').get_by_text('Research evidence unavailable', exact=True).wait_for()
                assert not page.locator('#refreshOperatorResearch').is_disabled()
                page.unroute('**/api/v1/platform/operator/research**')
                page.locator('#operatorResearchAsset').fill('BTCUSDT')
                page.locator('#refreshOperatorResearch').click()
                page.locator('#operatorResearch').get_by_text('2 trials · 2 terminal results').wait_for()
                assert not errors, errors
                report['checks'].append({'name': f'{label}_{theme}_real_ledger_filter_error_retry_xss', 'pass': True})
                context.close()
        context = browser.new_context()
        page = context.new_page()
        page.goto(base + '/app')
        page.wait_for_load_state('networkidle')
        page.locator('#loginForm [name=email]').fill('research-free@example.test')
        page.locator('#loginForm [name=password]').fill('LocalDrill-Only-20261003!')
        page.locator('#loginForm button[type=submit]').click()
        page.locator('#appShell').wait_for(state='visible')
        page.wait_for_load_state('networkidle')
        assert page.locator('#opsNavButton').is_hidden()
        response = context.request.get(base + '/api/v1/platform/operator/research')
        assert response.status == 403
        report['checks'].append({'name': 'customer_operator_research_rbac', 'pass': True})
        context.close()
    finally:
        browser.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
