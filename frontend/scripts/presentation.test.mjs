import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  record, rows, display, finite, numberLabel, probabilityLabel,
  moneyLabel, timeLabel, brokerMode, statusText,
} from "../src/lib/presentation.ts";

test("unavailable money and market values never turn into fabricated zeros", () => {
  for (const input of [null, undefined, "", "NaN", "Infinity", {}, []]) {
    assert.equal(finite(input), null);
    assert.equal(numberLabel(input), "Unavailable");
    assert.equal(moneyLabel(input, "USD"), "Unavailable");
  }
  assert.equal(moneyLabel(200, null), "Unavailable");
  assert.equal(moneyLabel(200, "NOT-A-CURRENCY"), "Unavailable");
  assert.match(moneyLabel(125.5, "USD"), /USD/);
  assert.match(moneyLabel("100", "NGN"), /NGN/);
  assert.equal(numberLabel(0), "0");
});

test("probabilities are normalized fractions and invalid values stay unavailable", () => {
  assert.equal(probabilityLabel(0.625), "62.5%");
  assert.equal(probabilityLabel("0.93"), "93.0%");
  assert.equal(probabilityLabel(0), "0.0%");
  for (const value of [null, "", 1.7, -0.2, "unknown", 85]) {
    assert.equal(probabilityLabel(value), "Unavailable");
  }
});

test("broker connection environment is never inferred from account labels", () => {
  assert.equal(brokerMode({ account_label:"Demo trading", environment:"unknown" }), "Environment unverified");
  assert.equal(brokerMode({ environment:"demo" }), "DEMO");
  assert.equal(brokerMode({ environment:"live" }), "LIVE — certification required");
  assert.equal(brokerMode({}), "Environment unverified");
});

test("lists and identity fields are narrowed without serializing private objects", () => {
  assert.deepEqual(rows([{asset:"BTC"},{asset:"ETH"},null, 0, "oops"]),[{asset:"BTC"},{asset:"ETH"}]);
  assert.deepEqual(record(null), {});
  assert.equal(display({secret:"test"}), "Unavailable");
  assert.equal(display(" XAUUSD "), "XAUUSD");
  assert.equal(timeLabel("not-a-date"), "Unavailable");
});

test("denied, expired and unavailable API responses are separate states", () => {
  assert.match(statusText(401), /expired|not signed in/i);
  assert.match(statusText(403), /permission/i);
  assert.match(statusText(429), /rate-limited/i);
  assert.match(statusText(503), /unavailable/i);
});

test("workspace never calls an order or high-risk mutation from a read-only view", () => {
  const src = readFileSync(new URL("../src/components/WorkspaceLive.tsx", import.meta.url), "utf8");
  assert.match(src, /api\/v1\/platform\/me/);
  assert.ok(src.includes('client.GET("/api/v1/platform/signals"'));
  assert.doesNotMatch(src, /client\.(POST|PUT|DELETE|PATCH)\(/);
  assert.doesNotMatch(src, /localStorage|sessionStorage/);
});


test("safe account form actions are limited to owned watchlists support and journal", () => {
  const source=readFileSync(new URL("../src/components/AccountCreation.tsx", import.meta.url),"utf8");
  const targets=[...source.matchAll(/client\.POST\("([^"]+)"/g)].map(match=>match[1]).sort();
  assert.deepEqual(targets, [
    "/api/v1/platform/journal",
    "/api/v1/platform/support/tickets",
    "/api/v1/platform/watchlists",
  ]);
  assert.doesNotMatch(source,/\/broker\/|\/execute|kill-switch|\/billing\/checkout|localStorage|sessionStorage/);
});

test("one-time email links only consume tokens after explicit confirmation", () => {
  const source=readFileSync(new URL("../src/components/AccountEmailLink.tsx", import.meta.url),"utf8");
  assert.match(source,/onClick=\{consume\}/);
  assert.match(source,/onSubmit=\{verifyMfa\}/);
  assert.ok(source.includes('client.POST("/api/v1/platform/auth/email-verification/complete"'));
  assert.ok(source.includes('client.POST("/api/v1/platform/auth/magic-link/complete"'));
  assert.ok(source.includes('client.POST("/api/v1/platform/auth/mfa/complete"'));
  assert.doesNotMatch(source,/localStorage|sessionStorage/);
});


test("magic link request is non-enumerating and never persists proof",()=>{
  const source=readFileSync(new URL("../src/components/MagicSignIn.tsx",import.meta.url),"utf8");
  assert.ok(source.includes('client.POST("/api/v1/platform/auth/magic-link/request"'));
  assert.match(source,/If this address has an active account/);
  assert.doesNotMatch(source,/localStorage|sessionStorage|client\.(PUT|DELETE|PATCH)\(/);
});

test("operations navigation checks server-issued operator authority",()=>{
  const nav=readFileSync(new URL("../src/components/AppShell.tsx",import.meta.url),"utf8");
  const control=readFileSync(new URL("../src/components/OperationsNavLink.tsx",import.meta.url),"utf8");
  assert.ok(nav.includes("<OperationsNavLink"));
  assert.ok(control.includes('client.GET("/api/v1/platform/me")'));
  assert.ok(control.includes('authority==="OWNER"||authority==="ADMIN"'));
  assert.doesNotMatch(nav,/\["Operations","\/app\/operations"\]/);
  assert.doesNotMatch(control,/localStorage|sessionStorage|client\.(POST|PUT|DELETE|PATCH)\(/);
});


test("entitled signal details render receipt lifecycle and outcome proof, never claim broker fills",()=>{
  const evidence=readFileSync(new URL("../src/components/SignalEvidence.tsx",import.meta.url),"utf8");
  const workspace=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  assert.match(evidence,/proof\.access_proven/);
  assert.match(evidence,/proof\.delivery_proven/);
  assert.match(evidence,/proof\.web_delivery_proven/);
  assert.match(evidence,/signal\.ml_probability_calibrated/);
  assert.match(evidence,/signal\.lifecycle_state/);
  assert.match(evidence,/signal\.canonical_outcome/);
  assert.match(evidence,/events\.map/);
  assert.match(evidence,/broker order or trade fill/);
  assert.match(evidence,/Not determined by signal evidence/);
  assert.match(workspace,/<SignalEvidence data=\{data\}/);
  assert.doesNotMatch(evidence,/client\.(POST|PUT|DELETE|PATCH)\(|localStorage|sessionStorage/);
});


test("browser account API uses same-origin CSRF and server-owned trusted rewrite",()=>{
  const client = readFileSync(new URL("../src/lib/client.ts", import.meta.url),"utf8");
  const config = readFileSync(new URL("../next.config.ts", import.meta.url),"utf8");
  const transport = readFileSync(new URL("../src/lib/transport.ts", import.meta.url),"utf8");
  assert.match(client,/const baseUrl = ""/);
  assert.doesNotMatch(client,/NEXT_PUBLIC_SIGNALRANK_API_BASE_URL/);
  assert.match(config,/SIGNALRANK_PLATFORM_API_ORIGIN/);
  assert.match(config,/url\.protocol === "https:"/);
  assert.ok(config.includes('source: "/api/v1/platform/:path*"'));
  assert.match(config,/return origin/);
  assert.match(transport,/csrfCookie\(document\.cookie\)/);
  assert.match(transport,/credentials: "include"/);
});


test("notification actions require canonical read receipts and preserve unselected channel settings",()=>{
  const view=readFileSync(new URL("../src/components/NotificationCenter.tsx",import.meta.url),"utf8");
  const preferences=readFileSync(new URL("../src/components/NotificationPreferences.tsx",import.meta.url),"utf8");
  assert.ok(view.includes('client.POST("/api/v1/platform/notifications/{notification_id}/read"'));
  assert.ok(view.includes("r.data.read===true") || view.includes("result.data.read===true"));
  assert.ok(preferences.includes('client.GET("/api/v1/platform/notifications/preferences"'));
  assert.ok(preferences.includes('client.PUT("/api/v1/platform/notifications/preferences"'));
  assert.match(preferences,/choices\[c\.key\]!=="keep"/);
  assert.doesNotMatch(view+preferences,/\/broker\/|\/execute|kill.switch|localStorage|sessionStorage/);
});

test("watchlist search uses backend-returned instrument identity, not freeform broker symbols",()=>{
  const view=readFileSync(new URL("../src/components/WatchlistsView.tsx",import.meta.url),"utf8");
  assert.ok(view.includes('client.GET("/api/v1/platform/instruments/search"'));
  assert.ok(view.includes('client.POST("/api/v1/platform/watchlists/{watchlist_id}/items"'));
  assert.match(view,/instrument\.instrument_id/);
  assert.match(view,/r\.data\.added===true/);
  assert.doesNotMatch(view,/client\.(DELETE|PATCH|PUT)\(|localStorage|sessionStorage|\/execute/);
});


test("signal filters paginate canonical delivered receipts without changing generation thresholds",()=>{
  const src=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  assert.ok(src.includes('limit: 30, offset, ...filters'));
  assert.ok(src.includes("setSignalOffset(0)"));
  assert.ok(src.includes("setSignalOffset"));
  assert.ok(src.includes("total count not reported"));
  assert.doesNotMatch(src,/client\.(POST|PATCH|PUT|DELETE)\(/);
});


test("journal deletion needs explicit user confirmation and a verified account-owned response",()=>{
  const src=readFileSync(new URL("../src/components/JournalView.tsx",import.meta.url),"utf8");
  assert.ok(src.includes('client.DELETE("/api/v1/platform/journal/{journal_entry_id}"'));
  assert.match(src,/if\(!id\|\|busy\|\|!confirming\)return/);
  assert.match(src,/result\.data\.deleted===true/);
  assert.match(src,/Confirm deletion/);
  assert.match(src,/Keep entry/);
  assert.doesNotMatch(src,/localStorage|sessionStorage|\/execute|kill.switch/);
});


test("personal signal preferences use authoritative tier limits and never alter execution controls",()=>{
  const code=readFileSync(new URL("../src/components/TradingPreferences.tsx",import.meta.url),"utf8");
  const app=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  assert.ok(code.includes('client.PUT("/api/v1/platform/trading-profile"'));
  assert.ok(code.includes('minimum_signal_score'));
  assert.ok(code.includes('daily_signal_limit'));
  assert.ok(code.includes('response.data.preferences'));
  assert.match(code,/classes\.length === 0/);
  assert.match(code,/allowedClasses\.includes/);
  assert.match(app,/<TradingPreferences data=\{state\.data\}/);
  assert.doesNotMatch(code,/client\.(POST|DELETE|PATCH)\(|\/broker\/|\/signal\/execute|kill.switch|localStorage|sessionStorage/);
});


test("support conversations require an entitled ticket and server-confirmed reply",()=>{
  const s=readFileSync(new URL("../src/components/SupportCenter.tsx",import.meta.url),"utf8");
  const view=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  assert.ok(s.includes('client.GET("/api/v1/platform/support/tickets/{ticket_id}"'));
  assert.ok(s.includes('client.POST("/api/v1/platform/support/tickets/{ticket_id}/messages"'));
  assert.ok(s.includes('detail.ticket.status==="closed"'));
  assert.ok(s.includes('response.response.ok && response.data'));
  assert.ok(s.includes('params:{path:{ticket_id:selected}}'));
  assert.match(view,/<SupportCenter data=\{state\.data\}/);
  assert.doesNotMatch(s,/localStorage|sessionStorage|client\.(PUT|PATCH|DELETE)\(|\/execute|\/broker\//);
});


test("market-alert rules and notification receipts are separate canonical services",()=>{
  const rule=readFileSync(new URL("../src/components/AlertRules.tsx",import.meta.url),"utf8");
  const workspace=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  const shell=readFileSync(new URL("../src/components/AppShell.tsx",import.meta.url),"utf8");
  assert.ok(workspace.includes('case "alerts": return client.GET("/api/v1/platform/alerts")'));
  assert.ok(workspace.includes('case "notifications": return client.GET("/api/v1/platform/notifications")'));
  assert.ok(shell.includes('["Alerts","/app/alerts"]'));
  assert.ok(shell.includes('["Notifications","/app/notifications"]'));
  assert.ok(rule.includes('client.POST("/api/v1/platform/alerts"'));
  assert.ok(rule.includes('client.DELETE("/api/v1/platform/alerts/{alert_id}"'));
  assert.ok(rule.includes('response.data.disabled===true'));
  assert.match(rule,/confirmId!==id/);
  assert.ok(rule.includes('condition:needsPrice(kind)?{value:price}:{}'));
  assert.doesNotMatch(rule,/\/broker\/|\/execute|client\.PUT\(|localStorage|sessionStorage/);
});


test("public redesign covers seven reference routes with canonical semantics and one shared design",()=>{
  const routes=readFileSync(new URL("../src/app/[slug]/page.tsx",import.meta.url),"utf8");
  const editorial=readFileSync(new URL("../src/components/PublicEditorial.tsx",import.meta.url),"utf8");
  const styles=readFileSync(new URL("../src/app/public-design.css",import.meta.url),"utf8");
  const layout=readFileSync(new URL("../src/app/layout.tsx",import.meta.url),"utf8");
  for(const slug of ["pricing","methodology","risk","security","status","docs","providers"]){
    assert.ok(routes.includes(slug+": {"),"missing public route: "+slug);
  }
  assert.ok(routes.includes("generateStaticParams"));
  assert.ok(routes.includes("generateMetadata"));
  assert.ok(routes.includes("<PublicEditorial page={page}/>"));
  assert.ok(editorial.includes("page.details.map"));
  assert.ok(editorial.includes("page.note"));
  assert.ok(styles.includes(".sr-editorial-content"));
  assert.ok(styles.includes("@media(max-width:600px)"));
  assert.ok(styles.includes("@media(forced-colors:active)"));
  assert.ok(layout.includes('import "./public-design.css"'));
});

test("home page includes truthful market/workflow boundaries without fake live status",()=>{
  const home=readFileSync(new URL("../src/app/page.tsx",import.meta.url),"utf8");
  const css=readFileSync(new URL("../src/app/public-design.css",import.meta.url),"utf8");
  assert.ok(home.includes("NOT LIVE MARKET DATA"));
  assert.ok(home.includes("CONCEPTUAL VISUALIZATION — NOT A CHART"));
  assert.ok(home.includes("NO TRADE"));
  assert.ok(home.includes("paper") || home.includes("simulated"));
  assert.ok(home.includes("/risk"));
  assert.ok(home.includes("/login"));
  assert.ok(css.includes(".sr-public-home"));
  assert.doesNotMatch(home,/Math.random|fakeSignal|livePrice|localStorage|sessionStorage/);
});


test("paper desk uses account-scoped simulation routes with explicit confirmations and bounded risk",()=>{
  const src=readFileSync(new URL("../src/components/PaperDesk.tsx",import.meta.url),"utf8");
  const workspace=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  assert.ok(src.includes('client.GET("/api/v1/platform/paper/detail"'));
  assert.ok(src.includes('client.PUT("/api/v1/platform/paper/settings"'));
  assert.ok(src.includes('client.POST("/api/v1/platform/paper/close-all"'));
  assert.ok(src.includes('client.POST("/api/v1/platform/paper/reset"'));
  assert.ok(src.includes('client.POST("/api/v1/platform/paper/retry"'));
  assert.ok(src.includes("CLOSE PAPER POSITIONS"));
  assert.ok(src.includes("RESET PAPER ACCOUNT"));
  assert.ok(src.includes("RETRY PAPER SIGNAL"));
  assert.ok(src.includes("n<0.1||n>10"));
  assert.ok(src.includes("allow_last_mark_fallback:false"));
  assert.match(src,/response\.data\.snapshot/);
  assert.match(src,/response\.data\.accepted===true/);
  assert.ok(workspace.includes("<PaperDesk onChanged="));
  assert.doesNotMatch(src,/\/broker\/|live.financial|global.kill|\/operator\/|localStorage|sessionStorage/);
});


test("portfolio chart never synthesizes missing broker balances or a fake equity curve",()=>{
  const chart=readFileSync(new URL("../src/components/PaperEquityChart.tsx",import.meta.url),"utf8");
  const workspace=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  assert.ok(chart.includes("finite(row.balance_after)"));
  assert.ok(chart.includes("Date.parse(row.created_at)"));
  assert.ok(chart.includes("samples.length<2"));
  assert.ok(chart.includes("ledger.slice")||chart.includes("series.slice(-250)"));
  assert.ok(chart.includes('role="img"'));
  assert.ok(chart.includes("Inspect ledger rows"));
  assert.ok(workspace.includes("<PaperEquityChart ledger={rows(data.equity_curve)}"));
  assert.doesNotMatch(chart,/Math\.random|crypto\.random|client\.(POST|PUT|DELETE|PATCH)\(/);
});


test("public and private mobile disclosures close on route change outside touch and Escape",()=>{
  const menu=readFileSync(new URL("../src/components/ResponsiveDisclosure.tsx",import.meta.url),"utf8");
  const publicNav=readFileSync(new URL("../src/components/PublicNav.tsx",import.meta.url),"utf8");
  const shell=readFileSync(new URL("../src/components/AppShell.tsx",import.meta.url),"utf8");
  assert.match(menu,/usePathname\(\)/);
  assert.match(menu,/document\.addEventListener\("pointerdown"/);
  assert.match(menu,/event\.key!=="Escape"/);
  assert.match(menu,/el\.closest\("a\[href\]"\)/);
  assert.match(menu,/element\.open=false/);
  assert.ok(publicNav.includes("<ResponsiveDisclosure"));
  assert.ok(shell.includes("<ResponsiveDisclosure"));
  assert.doesNotMatch(menu,/localStorage|sessionStorage|client\.(POST|PUT|DELETE|PATCH)\(/);
});


test("broker account inspection remains separate by canonical connection and never enables execution",()=>{
  const source=readFileSync(new URL("../src/components/BrokerAccounts.tsx",import.meta.url),"utf8");
  const workspace=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  assert.ok(source.includes("item.connection_id"));
  assert.ok(source.includes('client.GET("/api/v1/platform/broker/connections/{connection_id}/policy"'));
  assert.ok(source.includes('client.GET("/api/v1/platform/broker/connections/{connection_id}/ledger"'));
  assert.ok(source.includes('client.POST("/api/v1/platform/broker/connections/{connection_id}/verify"'));
  assert.ok(source.includes('client.POST("/api/v1/platform/broker/connections/{connection_id}/safety-freeze"'));
  assert.ok(source.includes("FREEZE ACCOUNT"));
  assert.ok(source.includes("frozen:true,confirm:true"));
  assert.ok(source.includes("result.data.execution_enabled===false"));
  assert.ok(workspace.includes("<BrokerAccounts data={state.data}"));
  assert.doesNotMatch(source,/\/execution"|\/trade"|\/place.order|\/broker\/exchange|\/broker\/metatrader\//);
});


test("market directory searches all entitled asset classes without fabricating live market data",()=>{
  const source=readFileSync(new URL("../src/components/MarketDirectory.tsx",import.meta.url),"utf8");
  const workspace=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  assert.ok(source.includes('client.GET("/api/v1/platform/instruments/search"'));
  assert.ok(source.includes("instrument.provider_count"));
  assert.ok(source.includes("instrument.discovery_status"));
  assert.ok(source.includes("instrument.tradable===true"));
  assert.ok(source.includes("global universe count not provided"));
  for(const kind of ["crypto","fx","stock","index","commodity"]) assert.ok(source.includes(kind));
  assert.ok(workspace.includes("<MarketDirectory/>"));
  assert.doesNotMatch(source,/client\.(POST|PUT|DELETE|PATCH)\(|\/broker\/|\/execute|Math\.random/);
});


test("settings security center keeps identity, devices, MFA and session revocation server-owned",()=>{
  const source=readFileSync(new URL("../src/components/AccountSecurity.tsx",import.meta.url),"utf8");
  const workspace=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  for(const route of ["/api/v1/platform/me","/api/v1/platform/devices","/api/v1/platform/security/mfa","/api/v1/platform/security/mfa/setup","/api/v1/platform/security/mfa/enable","/api/v1/platform/profile","/api/v1/platform/auth/logout-all","/api/v1/platform/devices/{session_id}","/api/v1/platform/auth/email-verification/request"]){
    assert.ok(source.includes(route),route);
  }
  assert.ok(source.includes("REVOKE SESSION"));
  assert.ok(source.includes("SIGN OUT ALL DEVICES"));
  assert.ok(source.includes('r.data?.revoked===true'));
  assert.ok(source.includes('r.data?.logged_out===true'));
  assert.ok(source.includes("setRecoveryCodes(null)"));
  assert.ok(workspace.includes("<AccountSecurity onChanged="));
  assert.doesNotMatch(source,/localStorage|sessionStorage|\/broker\/|\/operator\/|auto.execution|kill.switch/);
});


test("broker percentage risk fields are decimal fractions, never raw percent values",()=>{
  assert.equal(probabilityLabel("0.005"),"0.5%");
  assert.equal(probabilityLabel("0.02"),"2.0%");
  assert.equal(probabilityLabel("0.06"),"6.0%");
  const broker=readFileSync(new URL("../src/components/BrokerAccounts.tsx",import.meta.url),"utf8");
  for(const field of ["max_risk_per_trade_pct","max_daily_loss_pct","max_total_drawdown_pct"]){
    assert.ok(broker.includes(`probabilityLabel(policy.${field})`),field);
  }
});


test("demo broker setup uses provider-hosted credentials and never starts live execution",()=>{
  const source=readFileSync(new URL("../src/components/DemoBrokerConnection.tsx",import.meta.url),"utf8");
  const workspace=readFileSync(new URL("../src/components/WorkspaceLive.tsx",import.meta.url),"utf8");
  assert.ok(source.includes('client.GET("/api/v1/platform/broker/metatrader/servers"'));
  assert.ok(source.includes('client.POST("/api/v1/platform/broker/metatrader/secure-link"'));
  assert.ok(source.includes('environment:"demo",ttl_days:3'));
  assert.ok(source.includes('data.configuration_link'));
  assert.ok(source.includes('url.hostname'));
  assert.ok(source.includes('uri.protocol!=="https:"'));
  assert.ok(source.includes('rel="noopener noreferrer"'));
  assert.ok(source.includes('execution disabled') || source.includes('does not turn on auto-execution'));
  assert.ok(workspace.includes("<DemoBrokerConnection onChanged="));
  assert.doesNotMatch(source,/password\s*[:=]|api_secret|api_key|localStorage|sessionStorage|\/execution"|\/orders|enable.execution/);
});
