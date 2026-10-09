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
                diagnostics = context.request.get(base + '/api/v1/platform/operator/diagnostics')
                assert diagnostics.status == 200
                health = diagnostics.json()['adaptive_health']
                assert health['status'] == 'UNAVAILABLE' and health['fresh'] is False
                assert health['broker_fills_certified'] is False
                page.locator('#operatorDiagnostics').get_by_text('Adaptive health check', exact=True).wait_for()
                page.locator('#adaptiveHealthEvidence').get_by_text('Profile coverage unavailable').wait_for()
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
                page.wait_for_function("getComputedStyle(document.querySelector('#toast')).opacity === '0'")
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
                # Keep real HTTP authentication and other diagnostics; only
                # this health report is an explicitly synthetic display fixture.
                fixture = {**health, 'status': 'COMPLETED', 'fresh': True, 'evaluated_profile_count': 23,
                    'delivery_evidence_counts': {'UNAVAILABLE': 21, 'INSUFFICIENT': 1, 'OBSERVED': 0, 'INVALID': 1},
                    'diagnostics_truncated': True, 'profile_diagnostics': [
                        {'profile_id': 'synthetic-empty', 'asset': 'Synthetic <img src=x onerror=window.healthInjected=true>',
                         'profile_state': 'CANARY', 'sample_size': 0, 'delivery_evidence_status': 'UNAVAILABLE',
                         'coverage_reason': 'no_eligible_delivery_outcomes', 'expectancy_r': None, 'reasons': []},
                        {'profile_id': 'synthetic-small', 'asset': 'SMALL', 'profile_state': 'LIMITED_LIVE',
                         'sample_size': 1, 'delivery_evidence_status': 'INSUFFICIENT',
                         'coverage_reason': 'minimum_delivery_sample_not_met', 'reasons': []},
                        {'profile_id': 'synthetic-invalid', 'asset': 'INVALID', 'profile_state': 'APPROVED',
                         'sample_size': 2, 'delivery_evidence_status': 'INVALID',
                         'reasons': ['invalid_delivery_health_observations']}]}
                body = diagnostics.json()
                page.route('**/api/v1/platform/operator/diagnostics', lambda route: route.fulfill(status=200,
                    content_type='application/json', body=json.dumps({**body, 'adaptive_health': fixture})))
                page.locator('#refreshOperatorDiagnostics').click()
                panel = page.locator('#adaptiveHealthEvidence')
                panel.get_by_text('23 active profiles checked', exact=True).wait_for()
                assert 'no eligible delivery outcomes' in panel.inner_text()
                assert 'minimum delivery sample not met' in panel.inner_text()
                assert 'Showing 3 profiles' in panel.inner_text()
                assert panel.locator('tbody tr').count() == 3 and panel.locator('img').count() == 0
                assert page.evaluate('window.healthInjected') is None
                assert 'certify strategy health' in panel.inner_text()
                panel.get_by_text('Monitor current', exact=True).wait_for()
                assert 'HEALTHY' not in panel.inner_text().upper()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'health table must fit viewport'
                if label == 'mobile':
                    bounds = panel.locator('.adaptive-health-table-wrap').bounding_box()
                    assert bounds is not None
                    for row in panel.locator('tbody tr').all():
                        for cell in row.locator('td').all():
                            box = cell.bounding_box()
                            assert box is not None and box['x'] >= bounds['x'] - 2
                            assert box['x'] + box['width'] <= bounds['x'] + bounds['width'] + 2, 'every health metric must fit the mobile card'
                panel.screenshot(path=str(out / f'health-{label}-{theme}.png'))
                (out / f'health-{label}-{theme}.json').write_text(json.dumps({
                    'scope': 'SYNTHETIC_HEALTH_DISPLAY_FIXTURE', 'rendered_text': panel.inner_text(),
                    'monitor_text': panel.locator('.status-pill').text_content()}, indent=2) + '\n', encoding='utf-8')
                fixture.update(status='STALE', fresh=False)
                page.locator('#refreshOperatorDiagnostics').click()
                panel.get_by_text('Monitor STALE', exact=True).wait_for()
                assert 'Last reported evidence may be stale' in panel.inner_text()
                page.unroute('**/api/v1/platform/operator/diagnostics')
                report['checks'].append({'name': f'{label}_{theme}_synthetic_health_coverage_staleness_xss', 'pass': True})
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
