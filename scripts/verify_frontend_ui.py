"""Rendered Next production-build acceptance with real local HTTP/SQL state."""
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit, quote

from playwright.sync_api import sync_playwright, expect

base = os.environ['FRONTEND_BROWSER_BASE_URL']
if os.environ.get('APP_ENV') != 'test' or urlsplit(base).hostname not in {'127.0.0.1', 'localhost'}:
    raise RuntimeError('browser drill only supports an owned local server')
out = Path(os.environ['FRONTEND_BROWSER_OUTPUT_DIR']).resolve()
report = {'git_sha': os.environ['BROWSER_CANDIDATE_SHA'],
          'candidate_dirty': os.environ['BROWSER_CANDIDATE_DIRTY'] == '1',
          'scope': 'NEXT_PRODUCTION_BUILD_REAL_FASTAPI_POSTGRES_SYNTHETIC_ACCOUNTS',
          'native_devices_verified': False, 'checks': [], 'routes': [], 'errors': []}


def save():
    (out/'browser-results.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


def visit(page, path):
    response = page.goto(base+path)
    page.wait_for_load_state('networkidle')
    assert response.status == 200, (path, response.status)
    return response


def login(page, tier='admin', return_path='/app'):
    visit(page, '/login?returnTo='+quote(return_path, safe=''))
    page.get_by_label('Email address', exact=True).fill(f'research-{tier}@example.test')
    page.get_by_label('Password', exact=True).fill('LocalDrill-Only-20261003!')
    page.get_by_role('button', name='Sign in', exact=True).click()
    page.wait_for_url(base+return_path)
    page.wait_for_load_state('networkidle')
    expect(page.locator('.sr-loading')).to_have_count(0)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width':1440, 'height':1000})
    page = context.new_page()
    pending_requests = {}
    recent_responses = []
    page.on('request', lambda request: pending_requests.update({id(request):
        {'path': urlsplit(request.url).path, 'started': time.monotonic()}}))
    page.on('requestfinished', lambda request: pending_requests.pop(id(request), None))
    page.on('requestfailed', lambda request: pending_requests.pop(id(request), None))
    page.on('response', lambda response: recent_responses.append(
        {'path': urlsplit(response.url).path, 'status': response.status}))
    page.on('pageerror', lambda error: report['errors'].append(str(error)))
    try:
        for health_path in ('/frontend_health', '/frontend-health'):
            health = context.request.get(base+health_path)
            assert health.status == 200
            assert health.json()['commit'] == report['git_sha']
            assert health.json()['financial_readiness_certified'] is False
            assert 'no-store' in health.headers['cache-control']
        report['checks'].append('both frontend health URLs prove candidate identity without financial certification')
        signup_context = browser.new_context()
        try:
            signup_page = signup_context.new_page()
            visit(signup_page, '/login')
            signup_page.get_by_role('button', name='New to SignalRank? Create an account').click()
            signup_page.get_by_label('Email address', exact=True).fill('stage1-signup@example.test')
            signup_page.get_by_label('Password', exact=True).fill('LocalDrill-Only-20261003!')
            signup_page.get_by_label('Confirm password', exact=True).fill('LocalDrill-Only-20261003!')
            for field in ('platform_terms_accepted','privacy_acknowledged','age_eligibility_confirmed'):
                signup_page.locator(f'input[name={field}]').check()
            assert not signup_page.locator('input[name=marketing_consent]').is_checked()
            signup_page.get_by_role('button', name='Create account', exact=True).click()
            signup_page.wait_for_url(base+'/app', timeout=30000)
            signup_me = signup_context.request.get(base+'/api/v1/platform/me')
            assert signup_me.status == 200 and signup_me.json()['user']['primary_email'] == 'stage1-signup@example.test'
            report['checks'].append('explicit consent registration creates a real isolated database account and verified cookie session')
        finally:
            signup_context.close()
        anonymous = context.request.get(base+'/api/v1/platform/me')
        assert anonymous.status == 401
        assert 'no-store' in anonymous.headers.get('cache-control', '')
        response = visit(page, '/')
        policy = response.headers.get('content-security-policy', '')
        nonce = re.search(r"'nonce-([^']+)'", policy).group(1)
        assert "'unsafe-eval'" not in policy and "script-src 'self' 'nonce-" in policy
        assert response.headers.get('x-frame-options') == 'DENY'
        assert response.headers.get('x-content-type-options') == 'nosniff'
        assert 'x-powered-by' not in response.headers
        assert page.locator('script').evaluate_all('(nodes) => nodes.every(node => node.nonce.length > 0)')
        second = context.request.get(base+'/', headers={'x-nonce':'attacker-selected', 'content-security-policy':"script-src * 'unsafe-inline'"})
        second_nonce = re.search(r"'nonce-([^']+)'", second.headers['content-security-policy']).group(1)
        assert second_nonce != nonce and second_nonce != 'attacker-selected'
        # Simulate attacker-controlled markup, not debugger JS (which is trusted
        # and can itself create trusted scripts under strict-dynamic).
        def injected_markup(route):
            upstream = route.fetch()
            route.fulfill(response=upstream, body=upstream.text().replace('</head>',
                '<script>window.unsafeScriptRan=true</script></head>'))
        page.route(base+'/?cspProbe=1', injected_markup)
        visit(page, '/?cspProbe=1')
        assert page.evaluate('window.unsafeScriptRan === undefined')
        page.unroute(base+'/?cspProbe=1', injected_markup)
        report['checks'].append('fresh nonces, caller nonce rejected, unauthorized inline script blocked')

        public_paths = sorted(set(page.locator('a[href^="/"]').evaluate_all('(nodes)=>nodes.map(n=>n.getAttribute("href").split("#")[0])')))
        for path in public_paths:
            if path and not path.startswith('/app'):
                visit(page, path)
                assert page.get_by_role('link', name=re.compile(r'^CRILOX Solutions')).count() >= 1
                report['routes'].append({'path':path, 'status':200, 'scope':'public'})

        visit(page, '/app/watchlists')
        expect(page.get_by_role('heading',name='Sign in required',exact=True)).to_be_visible()
        assert (context.request.get(base+'/api/v1/platform/me')).status == 401
        expect(page.get_by_role('link',name='Sign in securely',exact=True)).to_have_attribute('href','/login?returnTo=%2Fapp%2Fwatchlists')
        login(page, return_path='/app/watchlists')
        cookies = {c['name']: c for c in context.cookies()}
        assert cookies['sr_access']['httpOnly'] and cookies['sr_refresh']['httpOnly']
        assert not cookies['sr_csrf']['httpOnly']
        assert page.evaluate("Object.keys(localStorage).every(k=>k==='signalrank.theme')")
        report['checks'].append('real account login, HttpOnly session cookies, no browser-storage tokens')

        for section in ('', 'signals', 'markets', 'research', 'watchlists', 'alerts', 'notifications',
                        'paper', 'portfolio', 'performance', 'journal', 'brokers', 'billing', 'support', 'settings', 'operations'):
            path = '/app'+('/'+section if section else '')
            response = visit(page, path)
            expect(page.locator('.sr-loading')).to_have_count(0)
            assert 'no-store' in response.headers.get('cache-control','')
            assert 'noindex' in response.headers.get('x-robots-tag','')
            state = page.locator('.sr-access-state').inner_text() if page.locator('.sr-access-state').count() else 'account data rendered'
            report['routes'].append({'path':path,'status':200,'state':state,'scope':'authenticated'})
            save()

        visit(page, '/app/watchlists')
        page.get_by_label('Watchlist name', exact=True).fill('Browser acceptance watchlist')
        page.get_by_role('button',name='Create watchlist',exact=True).click()
        expect(page.get_by_text('Browser acceptance watchlist',exact=True)).to_be_visible()
        page.reload()
        page.wait_for_load_state('networkidle')
        expect(page.get_by_text('Browser acceptance watchlist',exact=True)).to_be_visible()
        account_response = context.request.get(base+'/api/v1/platform/watchlists')
        assert 'no-store' in account_response.headers.get('cache-control', '')
        payload = account_response.json()
        assert 'Browser acceptance watchlist' in json.dumps(payload)
        denied = context.request.post(base+'/api/v1/platform/watchlists',data={'name':'Missing CSRF should fail'})
        assert denied.status == 403
        assert 'no-store' in denied.headers.get('cache-control', '')
        report['checks'].append('watchlist UI write persisted after refresh; missing CSRF rejected by backend')

        context.clear_cookies(name='sr_access')
        visit(page, '/app/watchlists')
        expect(page.get_by_text('Browser acceptance watchlist',exact=True)).to_be_visible()
        assert any(c['name']=='sr_access' for c in context.cookies())
        report['checks'].append('expired access cookie renewed by authenticated refresh without losing account state')

        for width in (320,360,390,430,768,1024,1280,1440,1920):
            page.set_viewport_size({'width':width,'height':1000})
            for theme in ('dark','light'):
                visit(page, '/app/watchlists')
                page.get_by_label('Color theme',exact=True).select_option(theme)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (width,theme,'workspace overflow')
                if width in (390,1440):
                    page.screenshot(path=str(out/f'workspace-{width}-{theme}.png'),full_page=True)
                visit(page, '/')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (width,theme,'public overflow')
                assert page.evaluate('document.documentElement.dataset.theme') == theme
                if width in (390,1440):
                    page.screenshot(path=str(out/f'home-{width}-{theme}.png'),full_page=True)
        report['checks'].append('public and workspace fit nine viewport widths in both themes; theme persists across routes')

        page.emulate_media(reduced_motion='reduce')
        visit(page,'/')
        assert page.get_by_role('heading',level=1).is_visible()
        page.set_viewport_size({'width':1440,'height':1000})
        visit(page,'/app/watchlists')
        page.get_by_role('button',name='Sign out securely',exact=True).click()
        page.wait_for_url(base+'/login')
        assert context.request.get(base+'/api/v1/platform/me').status == 401
        report['checks'].append('logout invalidates account access')

        other = browser.new_context(viewport={'width':1440,'height':1000})
        other_page = other.new_page()
        login(other_page,'free')
        assert 'Browser acceptance watchlist' not in json.dumps(other.request.get(base+'/api/v1/platform/watchlists').json())
        visit(other_page,'/app/operations')
        expect(other_page.get_by_role('heading',name='Access restricted',exact=True)).to_be_visible()
        assert other.request.get(base+'/api/v1/platform/operator/overview').status == 403
        other.close()
        report['checks'].append('second account cannot see first account watchlist; customer denied operator API and UI')
        linked = browser.new_context(viewport={'width':390,'height':844}, timezone_id='Africa/Lagos')
        linked_page = linked.new_page()
        login(linked_page,'linked')
        visit(linked_page,'/app/settings')
        expect(linked_page.get_by_text('Telegram is connected to this account. You do not need to link it again.',exact=True)).to_be_visible()
        assert linked_page.get_by_role('button',name='Link Telegram',exact=True).count() == 0
        assert linked_page.get_by_role('button',name='Request email verification',exact=True).count() == 0
        linked.close()
        report['checks'].append('already-linked Telegram account and verified email are not prompted to reconnect or verify again')
        assert not report['errors'], report['errors']
        report['status'] = 'PASS'
    except Exception as exc:
        report['status'] = 'FAIL'
        report['failure'] = str(exc)
        report['pending_requests'] = [{'path': item['path'],
            'age_seconds': round(time.monotonic()-item['started'], 2)}
            for item in pending_requests.values()]
        report['recent_response_statuses'] = recent_responses[-40:]
        page.screenshot(path=str(out/'failure.png'),full_page=True)
        raise
    finally:
        save()
        context.close()
        browser.close()
