const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const test = require('node:test');

const native = readFileSync(join(__dirname,'../App.tsx'),'utf8');
const helper = readFileSync(join(__dirname,'../src/presentation.ts'),'utf8');
const tabs = readFileSync(join(__dirname,'../src/MobileNavigation.tsx'),'utf8');

test('native account monetary labels never invent USD or turn missing balance into zero',()=>{
  assert.match(helper,/export function finiteNumber/);
  assert.match(helper,/export function currencyLabel/);
  assert.match(helper,/typeof code === "string"/);
  assert.match(helper,/return "Unavailable"/);
  assert.ok(native.includes('currencyLabel(account.cash_balance??snapshot.cash_balance,currency)'));
  assert.ok(native.includes('quantityLabel(summary.paper_cash)'));
  assert.doesNotMatch(native,/Number\(s\.paper_cash\|\|0\)/);
  assert.doesNotMatch(native,/Number\(data\.equity\|\|0\)/);
  assert.doesNotMatch(native,/\$\{Number\(.*\|\|0\)/);
});
test('native signal evidence distinguishes delivered receipts from brokerage execution',()=>{
  assert.ok(native.includes('function NativeSignalEvidence'));
  assert.ok(native.includes('proof.access_proven'));
  assert.ok(native.includes('percentLabel(signal.ml_probability_calibrated)'));
  assert.ok(native.includes('Delivery proof does not certify broker execution'));
  assert.ok(native.includes("api<T>(route)"));
});
test('mobile account reads have retry, loading and actual error states',()=>{
  assert.ok(native.includes('function useAccountData'));
  assert.ok(native.includes('function AccountDataState'));
  assert.ok(native.includes('retry:()=>setVersion'));
  assert.ok(native.includes('Account information unavailable'));
  assert.ok(native.includes('No delivered signals were returned'));
});
test('native bottom navigation retains all twelve screens without unscrollable oversized tabs',()=>{
  assert.ok(native.includes('<MobileNavigation active={screen} onSelect={setScreen}/>'));
  for(const route of ['overview','signals','markets','paper','portfolio','performance','journal','support','account','brokers','notifications','watchlists'])
    assert.ok(tabs.includes("screen:'"+route+"'"),route);
  assert.ok(tabs.includes('accessibilityState={{selected:active===item.screen}}'));
  assert.ok(tabs.includes('accessibilityState={{expanded:more}}'));
  assert.doesNotMatch(native,/screens\.map\(item=><Pressable/);
});
test('native uses approved emerald-slate identity for primary surfaces',()=>{
  for(const value of ['#08120f','#101e19','#294036','#4ce0a4','#e6eeea'])
    assert.ok(native.includes(value),value);
  assert.ok(tabs.includes('#4ce0a4'));
});

test('native broker, notification and watchlist views are authenticated and never enable trading',()=>{
  const pages=readFileSync(join(__dirname,'../src/AccountScreens.tsx'),'utf8');
  for(const path of ['/broker/connections','/notifications?limit=50','/watchlists','/instruments/search'])
    assert.ok(pages.includes(path),'missing canonical account route: '+path);
  assert.ok(pages.includes("result.read===true"));
  assert.ok(pages.includes("result.added===true"));
  assert.ok(pages.includes("result.watchlist_id"));
  assert.match(pages,/encodeURIComponent\(selected\)/);
  assert.doesNotMatch(pages,/\/execute|\/broker\/order|localStorage|AsyncStorage|kill.switch/);
});


test('Expo automatic light and dark appearance is honored by native screens and tab navigation',()=>{
  const tab=readFileSync(join(__dirname,'../src/MobileNavigation.tsx'),'utf8');
  const aux=readFileSync(join(__dirname,'../src/AccountScreens.tsx'),'utf8');
  const app=JSON.parse(readFileSync(join(__dirname,'../app.json'),'utf8'));
  assert.equal(app.expo.userInterfaceStyle,'automatic');
  for(const source of [native,tab,aux]){
    assert.ok(source.includes('useColorScheme'),"missing OS appearance subscription");
    assert.ok(source.includes("'light'?lightStyles:darkStyles"),"missing theme-aware style selection");
    assert.ok(source.includes('#4ce0a4'),"approved dark-mode accent missing");
    assert.ok(source.includes('#08754e'),"approved light-mode accent missing");
  }
  assert.ok(native.includes("scheme==='light'?'dark':'light'"));
});

test('mobile billing displays recorded currency and does not fabricate missing receipt amounts',()=>{
  assert.ok(native.includes('currencyLabel(product.price_ngn,product.currency||"NGN")'));
  assert.ok(native.includes('currencyLabel(receipt.amount,receipt.currency)'));
  assert.doesNotMatch(native,/Number\(receipt\.amount\|\|0\)/);
  assert.doesNotMatch(native,/Number\(product\.price_ngn\|\|0\)/);
});
