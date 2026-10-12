import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = path => readFileSync(new URL("../"+path,import.meta.url),"utf8");

test("public site is a navigable product experience, not a fake trading terminal",()=>{
  const page=read("src/app/page.tsx");
  assert.match(page,/<SignalLifecycleExperience\s*\/>/);
  assert.match(page,/NOT LIVE|NOT LIVE MARKET DATA|NOT A LIVE|NOT LIVE\/NO ORDER CLAIM|SCHEMATIC \/ NOT LIVE/);
  assert.match(page,/href="\/login"/);
  assert.match(page,/href="\/app\/signals"/);
  assert.match(page,/href="\/app\/paper"/);
  assert.match(page,/href="\/app\/brokers"/);
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

test("new design handles mobile and reduced motion rather than hiding content",()=>{
  const css=read("src/app/cinematic.css");
  const layout=read("src/app/layout.tsx");
  for(const breakpoint of ["980px","680px","390px"]){
    assert.ok(css.includes(breakpoint),"responsive breakpoint missing: "+breakpoint);
  }
  assert.ok(css.includes("prefers-reduced-motion"));
  assert.ok(css.includes(".sr-cinema-gates button.is-active"));
  assert.ok(css.includes(".sr-app-shell .sr-nav-group a[aria-current=page]"));
  assert.ok(layout.includes('import "./cinematic.css"'));
});
