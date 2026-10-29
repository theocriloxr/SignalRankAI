"""Automated WCAG 2.2 A/AA audit of the rendered web app with axe-core (29 Oct 2026).

Runs axe-core from ``frontend/node_modules`` in headless Chromium (Playwright)
against every public page and every workspace section, in light and dark
colour schemes, at desktop and phone widths. Signs in with a local test
account from ``A11Y_EMAIL`` / ``A11Y_PASSWORD``; refuses any host that is not
local, so it can never touch staging or production.

    python scripts/a11y_audit.py --base http://localhost:3100 --out audit.json

CSP is bypassed only inside this throwaway browser context so the audit
script can be injected; the pages themselves are unchanged. Automated rules
find roughly a third of WCAG issues; a 320 px pass adds reflow, skip-link and
focus-indicator checks. Screen-reader, full keyboard-only and
zoom checks still need a person.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
AXE = ROOT / "frontend" / "node_modules" / "axe-core" / "axe.min.js"
PUBLIC = ["/", "/login", "/recover", "/magic-login", "/pricing", "/methodology", "/risk", "/security",
          "/providers", "/status", "/docs", "/product", "/features", "/markets", "/strategies", "/ai",
          "/privacy", "/faq", "/contact",
          # Static legal pages served by the backend through the same origin.
          "/terms", "/cookies", "/billing-policy", "/risk-disclosure", "/accessibility"]
WORKSPACE = ["/app", "/app/signals", "/app/markets", "/app/research", "/app/watchlists", "/app/alerts",
             "/app/notifications", "/app/paper", "/app/portfolio", "/app/performance", "/app/journal",
             "/app/brokers", "/app/billing", "/app/support", "/app/settings", "/app/operations"]
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _summarise(results: dict) -> list[dict]:
    out = []
    for violation in results.get("violations", []):
        out.append({
            "id": violation["id"],
            "impact": violation.get("impact"),
            "help": violation.get("help"),
            "nodes": len(violation.get("nodes", [])),
            "targets": [" ".join(map(str, n.get("target", []))) for n in violation.get("nodes", [])[:5]],
            "summary": (violation.get("nodes") or [{}])[0].get("failureSummary", "")[:300],
        })
    return out


def _settle(page) -> None:
    page.wait_for_load_state("networkidle", timeout=20000)
    # Workspace sections show a skeleton until their data arrives.
    page.wait_for_function(
        "() => !document.querySelector('[role=status] .ui-skeleton-stack, .ui-skeleton-stack')", timeout=20000)


KEYBOARD_PROBE = """() => {
  const el = document.activeElement;
  if (!el || el === document.body) return {focused: null};
  const style = getComputedStyle(el);
  const indicator = (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0) || style.boxShadow !== 'none';
  const box = el.getBoundingClientRect();
  return {focused: (el.textContent || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 60),
          href: el.getAttribute('href'), indicator, on_screen: box.width > 0 && box.height > 0 && box.top >= 0,
          before_heading: focusablesBeforeHeading()};
}"""
FOCUSABLES_BEFORE_HEADING = """function focusablesBeforeHeading() {
  const h1 = document.querySelector('h1');
  if (!h1) return 0;
  const selector = 'a[href],button,input,select,textarea,summary,[tabindex]:not([tabindex="-1"])';
  return [...document.querySelectorAll(selector)].filter(el =>
    el.getClientRects().length && (el.compareDocumentPosition(h1) & Node.DOCUMENT_POSITION_FOLLOWING)).length;
}"""
# Styles settle on the next frames (reduced motion still runs 0.01 ms transitions).
TWO_FRAMES = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


def _keyboard_and_reflow(page) -> list[dict]:
    """WCAG 1.4.10 reflow at 320 CSS px; 2.4.1 a working skip link where there is navigation; 2.4.7 visible focus."""
    problems = []
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    if overflow > 1:
        problems.append({"id": "reflow-horizontal-scroll", "impact": "serious", "nodes": 1,
                         "help": f"Page scrolls sideways by {overflow}px at 320 CSS px (WCAG 1.4.10)"})
    page.keyboard.press("Tab")
    page.evaluate(TWO_FRAMES)
    first = page.evaluate("() => { " + FOCUSABLES_BEFORE_HEADING + " return (" + KEYBOARD_PROBE + ")(); }")
    is_skip = bool(first.get("focused")) and str(first.get("href") or "").startswith("#")
    if not is_skip:
        # A skip link is required when a block of controls precedes the content (WCAG 2.4.1);
        # a lone logo link before the heading is not a repeated block.
        if int(first.get("before_heading") or 0) >= 3:
            problems.append({"id": "skip-link-not-first", "impact": "moderate", "nodes": 1,
                             "help": f"First Tab stop is {first.get('focused')!r}, not a skip link (WCAG 2.4.1)"})
        return problems
    if not (first.get("indicator") and first.get("on_screen")):
        problems.append({"id": "focus-not-visible", "impact": "serious", "nodes": 1,
                         "help": "Focused skip link has no visible indicator or is off screen (WCAG 2.4.7)"})
    target = str(first["href"])[1:]
    page.keyboard.press("Enter")
    page.evaluate(TWO_FRAMES)
    landed = page.evaluate("id => { const t = document.getElementById(id); const a = document.activeElement;"
                           " return !!t && (a === t || t.contains(a)); }", target)
    if not landed:
        problems.append({"id": "skip-link-target", "impact": "serious", "nodes": 1,
                         "help": f"Activating the skip link did not move focus to #{target} (WCAG 2.4.1)"})
    return problems


def _sign_in(page, base: str, email: str, password: str) -> None:
    page.goto(base + "/login?returnTo=%2Fapp", wait_until="networkidle")
    page.fill("input[type=email]", email)
    page.fill("input[type=password]", password)
    page.click("button[type=submit]")
    page.wait_for_url("**/app**", timeout=20000)


def audit(base: str, email: str | None, password: str | None) -> dict:
    from playwright.sync_api import sync_playwright

    host = urlparse(base).hostname
    if host not in LOCAL_HOSTS:
        raise SystemExit(f"refusing non-local host {host!r}: this audit signs in and is for local stacks only")
    report: dict = {"base": base, "tags": TAGS, "axe": json.loads((ROOT / "frontend/node_modules/axe-core/package.json")
                                                                  .read_text(encoding="utf-8"))["version"], "runs": []}
    axe_source = AXE.read_text(encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for scheme in ("light", "dark"):
            for label, viewport in (("desktop", {"width": 1280, "height": 900}), ("mobile", {"width": 375, "height": 812})):
                context = browser.new_context(bypass_csp=True, color_scheme=scheme, viewport=viewport,
                                              reduced_motion="reduce")
                page = context.new_page()
                paths = list(PUBLIC)
                if email and password:
                    _sign_in(page, base, email, password)
                    paths += WORKSPACE
                for path in paths:
                    entry = {"path": path, "scheme": scheme, "viewport": label}
                    try:
                        response = page.goto(base + path, wait_until="domcontentloaded", timeout=30000)
                        entry["status"] = response.status if response else None
                        _settle(page)
                        page.add_script_tag(content=axe_source)
                        results = page.evaluate(
                            "tags => axe.run(document, {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations']})",
                            TAGS)
                        entry["violations"] = _summarise(results)
                    except Exception as exc:  # report and continue with the next page
                        entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                    report["runs"].append(entry)
                context.close()
        # Keyboard and reflow pass: 320 CSS px equals 400% zoom of a 1280 px window.
        context = browser.new_context(bypass_csp=True, viewport={"width": 320, "height": 800}, reduced_motion="reduce")
        page = context.new_page()
        paths = list(PUBLIC)
        if email and password:
            _sign_in(page, base, email, password)
            paths += WORKSPACE
        for path in paths:
            entry = {"path": path, "scheme": "light", "viewport": "320px-keyboard"}
            try:
                page.goto(base + path, wait_until="domcontentloaded", timeout=30000)
                _settle(page)
                entry["violations"] = _keyboard_and_reflow(page)
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            report["runs"].append(entry)
        context.close()
        browser.close()
    totals: dict[str, int] = {}
    for run in report["runs"]:
        for violation in run.get("violations", []):
            totals[violation["id"]] = totals.get(violation["id"], 0) + violation["nodes"]
    report["summary"] = {
        "pages_audited": len({run["path"] for run in report["runs"]}),
        "runs": len(report["runs"]),
        "runs_with_errors": sum(1 for run in report["runs"] if "error" in run),
        "runs_with_violations": sum(1 for run in report["runs"] if run.get("violations")),
        "violating_nodes_by_rule": dict(sorted(totals.items(), key=lambda kv: -kv[1])),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://localhost:3100")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.base.rstrip("/"), os.getenv("A11Y_EMAIL"), os.getenv("A11Y_PASSWORD"))
    args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=1))
    return 1 if report["summary"]["runs_with_violations"] or report["summary"]["runs_with_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
