"""Headless visual/DOM smoke test for the evidence workspace."""

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "web" / "platform_app"
OUTPUT = ROOT / "deployment_evidence" / "ui-evidence-workspace.png"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 1050}, device_scale_factor=1)
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.route("**/app-assets/styles.css", lambda route: route.fulfill(body=(APP / "styles.css").read_text(encoding="utf-8"), content_type="text/css"))
        page.route("**/app-assets/app.js", lambda route: route.fulfill(body="", content_type="text/javascript"))
        page.route("**/app-assets/icon.svg", lambda route: route.fulfill(body="<svg xmlns='http://www.w3.org/2000/svg'/>", content_type="image/svg+xml"))
        page.goto((APP / "index.html").as_uri(), wait_until="domcontentloaded")
        page.evaluate(
            """() => {
                document.body.classList.add('session-active');
                document.querySelector('#authShell').hidden = true;
                document.querySelector('#appShell').hidden = false;
                document.querySelector('#sessionNav').hidden = false;
                document.querySelectorAll('.view').forEach(node => node.hidden = true);
                document.querySelector('#evidenceView').hidden = false;
                document.querySelector('[data-view="evidence"]').classList.add('active');
                document.querySelector('#evidenceAsset').textContent = 'BTC / USD';
                document.querySelector('#evidenceTimeframe').textContent = '1h';
                document.querySelector('#evidenceFreshness').textContent = 'Data current · paper mode';
            }"""
        )
        assert page.locator("#evidenceView").is_visible()
        assert page.get_by_text("NO FUTURE DATA USED").is_visible()
        assert page.get_by_text("AWAITING CONFIRMATION").is_visible()
        assert page.locator(".spine-step").count() == 5
        page.screenshot(path=str(OUTPUT), full_page=True)
        browser.close()
    if console_errors:
        raise AssertionError(f"browser console errors: {console_errors}")
    print(f"PASS screenshot={OUTPUT}")


if __name__ == "__main__":
    main()
