import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = path => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");
const tokens = read("styles/tokens.css");

function luminance(hex) {
  const channels = [0, 2, 4].map(i => parseInt(hex.slice(1 + i, 3 + i), 16) / 255)
    .map(c => c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
function block(selector) {
  const start = tokens.indexOf(selector);
  assert.ok(start >= 0, selector);
  return tokens.slice(start, tokens.indexOf("}", start));
}
function value(css, name) {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
  assert.ok(match, name);
  return match[1];
}

test("muted text meets WCAG AA (4.5:1) on every surface in both themes", () => {
  for (const selector of [":root {", '[data-theme="light"]']) {
    const css = block(selector);
    for (const text of ["text-2", "text-3"]) {
      for (const surface of ["bg", "bg-raised", "surface", "surface-2", "surface-3"]) {
        const ratio = contrast(value(css, text), value(css, surface));
        assert.ok(ratio >= 4.5, `${selector} --${text} on --${surface} is ${ratio.toFixed(2)}:1`);
      }
    }
  }
});

test("public pages start with a working skip link", () => {
  assert.match(read("components/PublicNav.tsx"), /<a className="skip-link" href="#page-content">Skip to content<\/a>/);
  assert.match(read("app/page.tsx"), /id="page-content" tabIndex=\{-1\}/);
  assert.match(read("components/PublicEditorial.tsx"), /id="page-content" tabIndex=\{-1\}/);
  assert.match(read("components/AppShell.tsx"), /<a className="skip-link" href="#ws-main">/);
});

test("the menu's accessible name starts with its visible word (WCAG 2.5.3)", () => {
  const menu = read("components/ResponsiveDisclosure.tsx");
  assert.doesNotMatch(menu, /<summary[^>]*aria-label/);
  assert.match(menu, /<span>Menu<\/span><span className="visually-hidden">: \{label\}<\/span>/);
});
