"""Local browser acceptance of consent UX and failure feedback, using a fake API.

This does not certify account persistence, email, billing or a deployed website.
"""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'artifacts/stage1-20261014/browser'
    output.mkdir(parents=True, exist_ok=True)
    executable = Path(os.environ['LOCALAPPDATA']) / 'ms-playwright/chromium-1223/chrome-win64/chrome.exe'
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=str(executable))
        try:
            for width in (1440,390):
                page = browser.new_page(viewport={'width': width, 'height': 900})
                requests = []
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                def intercept(route):
                    if route.request.url.endswith('/auth/register'):
                        requests.append(route.request.post_data_json)
                        route.fulfill(status=503, json={'detail':'Synthetic unavailable service'})
                    else:
                        route.fulfill(status=401, json={'detail':'Synthetic anonymous account'})
                page.route('**/api/v1/platform/**', intercept)
                page.goto('http://127.0.0.1:3016/login')
                page.wait_for_load_state('networkidle')
                page.get_by_role('button', name='New to SignalRank? Create an account').click()
                page.get_by_label('Email address').fill('stage1-browser@example.invalid')
                page.get_by_label('Password', exact=True).fill('Isolated-test-password-1234')
                page.get_by_label('Confirm password').fill('Isolated-test-password-1234')
                assert page.locator('input[type=checkbox]').count() == 4
                assert page.locator('input[type=checkbox]:checked').count() == 0
                page.get_by_role('button', name='Create account', exact=True).click()
                assert requests == []
                checks.append(f'{width}: absent required consent prevents submission')
                for name in ('platform_terms_accepted','privacy_acknowledged','age_eligibility_confirmed'):
                    page.locator(f'input[name={name}]').check()
                assert not page.locator('input[name=marketing_consent]').is_checked()
                assert page.get_by_role('link', name='Terms of Use').get_attribute('href') == '/terms'
                assert page.get_by_role('link', name='Privacy Notice').get_attribute('href') == '/privacy'
                page.screenshot(path=str(output/f'consent-{width}.png'),full_page=True)
                page.get_by_role('button', name='Create account', exact=True).click()
                expect(page.get_by_role('status')).to_contain_text('Secure account services are unavailable')
                assert len(requests) == 1
                payload = requests[0]
                assert all(payload[k] is True for k in ('platform_terms_accepted','privacy_acknowledged','age_eligibility_confirmed'))
                assert payload['marketing_consent'] is False
                checks.append(f'{width}: explicit booleans sent and optional marketing stays off')
                assert errors == [], errors
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                checks.append(f'{width}: no uncaught browser errors or horizontal overflow')
                page.close()
        finally:
            browser.close()
    report={'result':'PASS','checks':checks,'scope':'Desktop/mobile browser UI with intercepted API; not backend persistence or deployment acceptance'}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
