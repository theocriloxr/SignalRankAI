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
test('native bottom navigation retains all nine screens without unscrollable oversized tabs',()=>{
  assert.ok(native.includes('<MobileNavigation active={screen} onSelect={setScreen}/>'));
  for(const route of ['overview','signals','markets','paper','portfolio','performance','journal','support','account'])
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
