"""Verify public-site cutover without replacing the mature backend workspace.

Only an owned local FastAPI/Postgres instance is supported; no external account,
webhook, order or payment is used. Backend failures are never synthesized as success.
"""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

base = os.environ['FRONTEND_BROWSER_BASE_URL']
if (os.environ.get('APP_ENV') != 'test' or os.environ.get('FRONTEND_BROWSER_WORKSPACE_MODE') != 'legacy'
        or urlsplit(base).hostname not in {'127.0.0.1','localhost'}):
    raise RuntimeError('legacy cutover drill requires an owned local test server')
out = Path(os.environ['FRONTEND_BROWSER_OUTPUT_DIR'])
report = {'git_sha':os.environ['BROWSER_CANDIDATE_SHA'],
          'candidate_dirty':os.environ['BROWSER_CANDIDATE_DIRTY'] == '1',
          'scope':'NEXT_PUBLIC_SITE_RETAINED_FASTAPI_WORKSPACE_REAL_LOCAL_BACKEND',
          'checks':[], 'errors':[], 'native_devices_verified':False}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width':1440,'height':1000})
    page = context.new_page()
    page.on('pageerror',lambda error:report['errors'].append(str(error)))
    try:
        for health_path in ('/frontend_health', '/frontend-health'):
            health = context.request.get(base+health_path)
            assert health.status == 200
            assert health.json()['commit'] == report['git_sha']
            assert health.json()['financial_readiness_certified'] is False
            assert 'no-store' in health.headers['cache-control']
        report['checks'].append('both frontend health URLs prove candidate identity without financial certification')
        response = page.goto(base+'/')
        page.wait_for_load_state('networkidle')
        assert response.status == 200 and "'nonce-" in response.headers['content-security-policy']
        assert page.locator('.sr-cinema-hero').count() == 1
        page.get_by_role('link',name='Workspace',exact=True).first.click()
        page.wait_for_load_state('networkidle')
        expect(page.locator('#authShell')).to_be_visible()
        assert page.locator('#loginForm').count() == 1, 'retained workspace did not load'
        assert page.locator('.sr-app-shell').count() == 0, 'uncertified replacement workspace was served'
        report['checks'].append('public homepage navigation performs full handoff to the existing workspace')

        page.locator('#loginForm input[name=email]').fill('research-admin@example.test')
        page.locator('#loginForm input[name=password]').fill('LocalDrill-Only-20261003!')
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#appShell')).to_be_visible(timeout=30000)
        assert context.request.get(base+'/api/v1/platform/me').status == 200
        assert {c['name']:c for c in context.cookies()}['sr_access']['httpOnly']
        report['checks'].append('existing workspace login and same-origin HttpOnly session work through the frontend proxy')

        for path,view in [('/app/signals','signals'),('/app/paper','paper'),('/app/brokers','account'),
                          ('/app/operations','ops'),('/app/settings','account')]:
            response = page.goto(base+path)
            page.wait_for_load_state('networkidle')
            assert response.status == 200
            expect(page.locator(f'#{view}View')).to_be_visible(timeout=15000)
            assert 'no-store' in response.headers.get('cache-control',''), (path,response.headers.get('cache-control'))
        report['checks'].append('workspace deep links map to existing signal, paper, broker, owner and account views')

        for path,content in [('/app/service-worker.js','signalrank-shell-v44'),
                             ('/app/manifest.webmanifest','SignalRank'),('/app-assets/app.js','const API=')]:
            response = context.request.get(base+path)
            assert response.status == 200 and content in response.text(),path
            if path.endswith('service-worker.js'):
                assert response.headers.get('service-worker-allowed') == '/app'
        report['checks'].append('installed workspace PWA, assets and service-worker scope remain available')

        csrf = next(c['value'] for c in context.cookies() if c['name']=='sr_csrf')
        saved = context.request.post(base+'/api/v1/platform/watchlists',data={'name':'Proxy acceptance'},headers={'X-CSRF-Token':csrf})
        assert saved.status == 201, saved.text()
        assert 'Proxy acceptance' in context.request.get(base+'/api/v1/platform/watchlists').text()
        assert context.request.post(base+'/api/v1/platform/watchlists',data={'name':'No proof'}).status == 403
        assert context.request.post(base+'/webhooks/paystack',data={}).status in (400,401,403,503)
        for path in ['/healthz','/version','/activate','/billing/complete']:
            assert context.request.get(base+path).status == 200,path
        report['checks'].append('API mutations persist with CSRF; missing proof fails; webhook rejects unsigned input; callback and health routes survive')

        page.goto(base+'/status')
        page.wait_for_load_state('networkidle')
        expect(page.get_by_role('heading',name='Check the connection.')).to_be_visible()
        expect(page.get_by_text('Account API',exact=True)).to_be_visible()
        for width in (320,390,768,1024,1440,1920):
            page.set_viewport_size({'width':width,'height':1000})
            for path in ['/','/features','/status']:
                page.goto(base+path);page.wait_for_load_state('networkidle')
                for theme in ('light','dark'):
                    page.get_by_label('Color theme',exact=True).select_option(theme)
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(path,width,theme)
                assert page.get_by_role('link',name=re.compile('^CRILOX Solutions')).count() >= 1
        page.screenshot(path=str(out/'public-cutover-1920.png'),full_page=True)
        report['checks'].append('public pages, live sanitized status, footer and both themes fit six viewport widths')
        assert not report['errors'],report['errors']
        report['status'] = 'PASS'
    except Exception as exc:
        report['status']='FAIL'; report['failure']=str(exc)
        page.screenshot(path=str(out/'failure.png'),full_page=True)
        raise
    finally:
        (out/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        context.close();browser.close()
