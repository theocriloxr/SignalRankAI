import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { safeReturnPath } from "../src/lib/return-path.ts";

test('post-login destinations stay within the workspace and retain safe deep links', () => {
  for (const value of ['https://evil.test/app','//evil.test/app','/app/../../login','/app\\evil','/application','/login','javascript:alert(1)','/app\r\nLocation:https://evil.test',null]) {
    assert.equal(safeReturnPath(value), '/app');
  }
  assert.equal(safeReturnPath('/app/signals/signal-id?tab=evidence#receipts'), '/app/signals/signal-id?tab=evidence#receipts');
});

function transport(fetch, cookie) {
  const exports = {};
  const source = fs.readFileSync(new URL("../src/lib/transport.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
  }).outputText;
  vm.runInNewContext(compiled, {
    exports, Request, Response, Headers, URL, fetch,
    ...(cookie === undefined ? {} : {document: {cookie}, window: {location: {origin: 'https://local.test'}}}),
  });
  return exports;
}

test("account reads include the cookie session without a forged bearer or write proof", async () => {
  let request;
  const api = transport(async (value) => {request = value; return new Response('{"user":{"id":1}}');}, "sr_csrf=fixture-proof");
  await api.platformFetch(new Request("https://local.test/api/v1/platform/me", {
    headers: {"X-SignalRank-Client": "web-next"},
  }));
  assert.equal(request.credentials, "include");
  assert.equal(request.redirect, "error");
  assert.equal(request.headers.get("X-SignalRank-Client"), "web-next");
  assert.equal(request.headers.get("Authorization"), null);
  assert.equal(request.headers.get("X-CSRF-Token"), null);
});

for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
  test(`${method} mutations preserve the body and use the exact CSRF cookie`, async () => {
    let request;
    const controller = new AbortController();
    const api = transport(async (value) => {request = value; return new Response("{}");}, "other_csrf=wrong; sr_csrf=encoded%2Dproof; sr_csrf_extra=wrong");
    await api.platformFetch(new Request("https://local.test/api/v1/platform/profile", {
      method, headers: {"Content-Type": "application/json"},
      body: '{"display_name":"Updated name"}', signal: controller.signal,
    }));
    assert.equal(request.method, method);
    assert.equal(request.credentials, "include");
    assert.equal(request.redirect, "error");
    assert.equal(request.headers.get("X-CSRF-Token"), "encoded-proof");
    assert.equal(await request.text(), '{"display_name":"Updated name"}');
    controller.abort();
    assert.equal(request.signal.aborted, true);
  });
}

test("missing or malformed proof is never replaced with a fabricated token", async () => {
  for (const cookie of ["", "sr_csrf_extra=wrong", "sr_csrf=", "sr_csrf=%XX"]) {
    const api = transport(async (request) => {
      assert.equal(request.headers.get("X-CSRF-Token"), null);
      return new Response("{}", {status: 403});
    }, cookie);
    assert.equal((await api.platformFetch(new Request("https://local.test/api/v1/platform/profile", {method: "PATCH"}))).status, 403);
  }
});

test("server rendering never gains browser authority implicitly", async () => {
  const api = transport(async (request) => {
    assert.equal(request.headers.get("Cookie"), null);
    assert.equal(request.headers.get("Authorization"), null);
    assert.equal(request.headers.get("X-CSRF-Token"), null);
    return new Response("{}", {status: 401});
  });
  assert.equal((await api.platformFetch(new Request("https://local.test/api/v1/platform/profile", {method: "PATCH"}))).status, 401);
});


test("401 on canonical account GET rotates cookies once with CSRF and retries only that read",async()=>{
  const calls=[];
  let reads=0;
  const api=transport(async request=>{
    calls.push({path:new URL(request.url).pathname,method:request.method,csrf:request.headers.get("X-CSRF-Token"),credentials:request.credentials,redirect:request.redirect});
    if(new URL(request.url).pathname.endsWith("/auth/refresh"))return new Response('{"authenticated":true}',{status:200});
    reads++;
    return reads===1?new Response("expired",{status:401}):new Response('{"user":{"id":1}}',{status:200});
  },"sr_csrf=refresh-proof");
  const result=await api.platformFetch(new Request("https://local.test/api/v1/platform/me"));
  assert.equal(result.status,200);
  assert.equal(reads,2);
  assert.deepEqual(calls.map(x=>[x.path,x.method]),[
    ["/api/v1/platform/me","GET"],["/api/v1/platform/auth/refresh","POST"],["/api/v1/platform/me","GET"],
  ]);
  assert.equal(calls[1].csrf,"refresh-proof");
  assert.ok(calls.every(x=>x.credentials==="include"));
  assert.ok(calls.every(x=>x.redirect==="error"));
});

test('untrusted destinations never receive cookies, CSRF proof or mutation bodies', async () => {
  let networkCalls = 0;
  const api = transport(async () => {networkCalls++; return new Response('{}');}, 'sr_csrf=private-proof');
  for (const url of [
    'https://attacker.test/api/v1/platform/profile',
    'http://local.test/api/v1/platform/profile',
    'https://local.test:444/api/v1/platform/profile',
    'https://local.test/api/v1/platform-evil/profile',
    'https://local.test/api/v1/platform/../../outside',
    'https://local.test/redirect',
  ]) {
    await assert.rejects(api.platformFetch(new Request(url, {method:'POST', body:'private-data'})),
      /same-origin platform API/);
  }
  assert.equal(networkCalls, 0);
});

test("concurrent expired reads share one refresh request without local tokens",async()=>{
  let refreshCount=0,reads=0;
  let resolveRefresh;
  const refreshGate=new Promise(resolve=>{resolveRefresh=resolve});
  const api=transport(async request=>{
    if(new URL(request.url).pathname.endsWith("/auth/refresh")){
      refreshCount++;await refreshGate;
      return new Response("{}",{status:200});
    }
    reads++;return reads<=2?new Response("expired",{status:401}):new Response("{}",{status:200});
  },"sr_csrf=proof");
  const p=Promise.all([
    api.platformFetch(new Request("https://local.test/api/v1/platform/me")),
    api.platformFetch(new Request("https://local.test/api/v1/platform/notifications")),
  ]);
  // Let both first reads arrive at the same in-flight refresh before resolving it.
  await Promise.resolve(); await Promise.resolve(); resolveRefresh();
  const res=await p;
  assert.equal(refreshCount,1);
  assert.equal(reads,4);
  assert.deepEqual(res.map(x=>x.status),[200,200]);
});

test("never replay non-idempotent account writes or refresh auth bootstrap routes",async()=>{
  const paths=[];
  const api=transport(async request=>{
    paths.push([new URL(request.url).pathname,request.method]);
    return new Response("expired",{status:401});
  },"sr_csrf=proof");
  assert.equal((await api.platformFetch(new Request("https://local.test/api/v1/platform/paper/reset",{method:"POST",body:'{"confirm":true,"starting_balance":500}'}))).status,401);
  assert.equal((await api.platformFetch(new Request("https://local.test/api/v1/platform/auth/login",{method:"POST",body:'{"email":"test"}'}))).status,401);
  assert.deepEqual(paths,[
    ["/api/v1/platform/paper/reset","POST"],["/api/v1/platform/auth/login","POST"]
  ]);
});

test("missing refresh proof leaves expired account read unauthenticated",async()=>{
  let count=0;
  const api=transport(async()=>{count++;return new Response("expired",{status:401})},"");
  assert.equal((await api.platformFetch(new Request("https://local.test/api/v1/platform/me"))).status,401);
  assert.equal(count,1);
});

test('discarded expired-read and refresh streams release their connections before replay',async()=>{
  const cancelled=[];
  function stream(name,status) {
    return new Response(new ReadableStream({cancel(){cancelled.push(name);}}),{status});
  }
  let reads=0;
  const api=transport(async request=>{
    if(new URL(request.url).pathname.endsWith('/auth/refresh'))return stream('refresh',200);
    if(++reads===1)return stream('expired',401);
    assert.deepEqual(cancelled,['refresh','expired']);
    return new Response('{"restored":true}');
  },'sr_csrf=proof');
  assert.deepEqual(await (await api.platformFetch(new Request('https://local.test/api/v1/platform/me'))).json(),{restored:true});
});

test('failed refresh releases its own stream and leaves the original error readable',async()=>{
  let cancelled=false;
  const api=transport(async request=>new URL(request.url).pathname.endsWith('/auth/refresh')?
    new Response(new ReadableStream({cancel(){cancelled=true;}}),{status:401}):new Response('expired',{status:401}),
    'sr_csrf=proof');
  const response=await api.platformFetch(new Request('https://local.test/api/v1/platform/me'));
  assert.equal(response.status,401);assert.equal(await response.text(),'expired');assert.equal(cancelled,true);
});
