import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = path => readFileSync(new URL("../"+path,import.meta.url),"utf8");

test("public site is a navigable product experience, not a fake trading terminal",()=>{
  const page=read("src/app/page.tsx");
  assert.match(page,/<SignalLifecycleExperience\s*\/>/);
  assert.match(page,/NOT LIVE|NOT LIVE MARKET DATA|NOT A LIVE|NOT LIVE\/NO ORDER CLAIM|SCHEMATIC \/ NOT LIVE/);
  assert.match(page,/href="\/login"/);
  assert.ok(page.includes('href:"/app/signals"')||page.includes('href="/app/signals"'));
  assert.ok(page.includes('href:"/app/paper"')||page.includes('href="/app/paper"'));
  assert.ok(page.includes('href:"/app/brokers"')||page.includes('href="/app/brokers"'));
  assert.doesNotMatch(page,/\b(?:client|fetch)\.(?:POST|PUT|PATCH|DELETE)\s*\(/);
});

test("four schematic decision gates remain accessible without fictitious signal metrics",()=>{
  const story=read("src/components/SignalLifecycleExperience.tsx");
  for(const step of ["INGEST / VERIFY","RESEARCH / EVALUATE","RISK / REJECT","DELIVER / TRACE"]){
    assert.ok(story.includes(step),step+" phase exists");
  }
  assert.match(story,/IntersectionObserver/);
  assert.match(story,/prefers-reduced-motion/);
  assert.match(story,/scrollIntoView/);
  assert.match(story,/aria-current/);
  assert.match(story,/NOT LIVE|NOT LIVE MARKET DATA|NO LIVE PRICE/);
  assert.doesNotMatch(story,/win rate.*\d+%|\bBTC.*\$[\d,.]+|client\.(POST|PATCH|DELETE|PUT)\(/i);
});

test("CRILOX credit is present and securely links to approved site in all shared shells",()=>{
  const credit=read("src/components/SiteCredit.tsx");
  assert.ok(credit.includes("Powered by"));
  assert.ok(credit.includes("https://www.criloxsolutions.com"));
  assert.ok(credit.includes('rel="noopener noreferrer"'));
  for(const file of ["src/app/page.tsx","src/components/PublicEditorial.tsx","src/components/AppShell.tsx","src/components/AccountEntry.tsx"]){
    const view=read(file);
    assert.ok(view.includes("<SiteCredit"),"Shared credit missing from "+file);
  }
});

test("core user journeys keep existing authorization and data fetch boundaries",()=>{
  const live=read("src/components/WorkspaceLive.tsx");
  const account=read("src/components/AccountEntry.tsx");
  const shell=read("src/components/AppShell.tsx");
  assert.ok(live.includes('client.GET("/api/v1/platform/me")'));
  assert.ok(live.includes('client.GET("/api/v1/platform/broker/connections")'));
  assert.ok(live.includes('client.GET("/api/v1/platform/signals"'));
  assert.ok(live.includes('statusText(state.status)'));
  assert.ok(account.includes('client.POST("/api/v1/platform/auth/login"'));
  assert.ok(shell.includes("<OperationsNavLink"));
  assert.doesNotMatch(live,/localStorage|sessionStorage|client\.(POST|PATCH|DELETE|PUT)\(/);
});

test("design system handles mobile, themes, reduced motion and forced colors rather than hiding content",()=>{
  const styles=["tokens","base","ui","marketing","workspace"].map(name=>read(`src/styles/${name}.css`)).join("\n");
  const layout=read("src/app/layout.tsx");
  for(const name of ["tokens","base","ui","marketing","workspace"]){
    assert.ok(layout.includes(`import "../styles/${name}.css"`),"layout must load "+name+".css");
  }
  for(const breakpoint of ["1023px","980px","680px","390px"]){
    assert.ok(styles.includes(breakpoint),"responsive breakpoint missing: "+breakpoint);
  }
  assert.ok(styles.includes("prefers-reduced-motion"));
  assert.ok(styles.includes("forced-colors: active"));
  // Theme: explicit choice wins, otherwise OS preference, applied before paint by the layout script.
  assert.ok(styles.includes(':root[data-theme="light"]'));
  assert.ok(styles.includes(':root:not([data-theme="dark"])'));
  assert.ok(layout.includes("signalrank.theme"));
  assert.ok(styles.includes(".mk-lifecycle-nav button.is-active"));
  assert.ok(styles.includes('.ws-nav-group a[aria-current="page"]'));
  assert.ok(styles.includes(":focus-visible"));
});

test("public header keeps the Menu button on screen at 320-390 px",()=>{
  // At 320 px the header's Open workspace button pushed Menu off-screen (x 328-398),
  // leaving small phones with no site navigation. The menu panel repeats the link.
  const css=read("src/styles/marketing.css");
  const nav=read("src/components/PublicNav.tsx");
  const narrow=css.slice(css.indexOf("@media (max-width: 390px)"));
  assert.match(narrow.slice(0,narrow.indexOf("}\n")+1),/\.mk-nav-actions > \.ui-btn--primary \{ display: none; \}/);
  assert.match(nav,/mk-menu-actions[\s\S]*href="\/app">Open workspace/);
});
