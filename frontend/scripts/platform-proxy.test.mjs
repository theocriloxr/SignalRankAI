import assert from 'node:assert/strict';
import test from 'node:test';
import {proxyPlatformRequest} from '../src/lib/platform-proxy.ts';

test('account proxy preserves method, body, authority and separate refresh cookies at one fixed origin',async()=>{
 const old=process.env.SIGNALRANK_PLATFORM_API_ORIGIN;
 process.env.SIGNALRANK_PLATFORM_API_ORIGIN='https://backend.example.test';
 try {
  let calls=0;
  const response=await proxyPlatformRequest(new Request('https://web.example.test/api/v1/platform/watchlists?tag=%26%23',
   {method:'POST',body:'{"name":"Owned watchlist"}',headers:{Cookie:'sr_access=synthetic',
    Authorization:'Bearer synthetic',Origin:'https://web.example.test','X-CSRF-Token':'synthetic-proof',
    'Idempotency-Key':'synthetic-once','X-Private-Backend-Override':'https://evil.test'}}),async(url,options)=>{
    calls++;assert.equal(url.href,'https://backend.example.test/api/v1/platform/watchlists?tag=%26%23');
    assert.equal(options.method,'POST');assert.equal(options.redirect,'manual');assert.equal(options.cache,'no-store');
    assert.equal(options.headers.get('cookie'),'sr_access=synthetic');
    assert.equal(options.headers.get('authorization'),'Bearer synthetic');
    assert.equal(options.headers.get('x-csrf-token'),'synthetic-proof');
    assert.equal(options.headers.get('origin'),'https://web.example.test');
    assert.equal(options.headers.get('idempotency-key'),'synthetic-once');
    assert.equal(options.headers.get('x-private-backend-override'),null);
    assert.equal(await new Response(options.body).text(),'{"name":"Owned watchlist"}');
    const headers=new Headers({'Content-Type':'application/json','Cache-Control':'public, max-age=3600',
      Connection:'keep-alive, x-hop-secret','X-Hop-Secret':'private'});
    headers.append('Set-Cookie','sr_access=first; HttpOnly; Secure; Path=/');
    headers.append('Set-Cookie','sr_refresh=second; Expires=Wed, 14 Oct 2026 00:00:00 GMT; HttpOnly; Secure; Path=/');
    return new Response('{"saved":true}',{status:201,headers});
   });
  assert.equal(calls,1);assert.equal(response.status,201);assert.deepEqual(await response.json(),{saved:true});
  assert.equal(response.headers.getSetCookie().length,2);
  assert.match(response.headers.get('cache-control'),/private, no-store/);
  assert.equal(response.headers.get('connection'),null);assert.equal(response.headers.get('x-hop-secret'),null);
  assert.equal(response.headers.get('x-content-type-options'),'nosniff');
 } finally {if(old===undefined)delete process.env.SIGNALRANK_PLATFORM_API_ORIGIN;else process.env.SIGNALRANK_PLATFORM_API_ORIGIN=old;}
});

test('upstream errors and redirects are returned once with private cache policy',async()=>{
 const old=process.env.SIGNALRANK_PLATFORM_API_ORIGIN;
 process.env.SIGNALRANK_PLATFORM_API_ORIGIN='https://backend.example.test';
 try {
  for(const status of [302,401,403,429,503]) {
   let calls=0;
   const response=await proxyPlatformRequest(new Request('https://web.example.test/api/v1/platform/me'),async()=>{
    calls++;return new Response('upstream',{status,headers:{Location:'https://another.example.test/'}});
   });
   assert.equal(calls,1);assert.equal(response.status,status);
   assert.match(response.headers.get('cache-control'),/no-store/);
  }
  const unavailable=await proxyPlatformRequest(new Request('https://web.example.test/api/v1/platform/me'),async()=>{throw new Error('private backend token');});
  assert.equal(unavailable.status,502);assert.doesNotMatch(await unavailable.text(),/private backend token/);
 } finally {if(old===undefined)delete process.env.SIGNALRANK_PLATFORM_API_ORIGIN;else process.env.SIGNALRANK_PLATFORM_API_ORIGIN=old;}
});

test('unconfigured destinations and normalized paths outside the account namespace never receive authority',async()=>{
 const old=process.env.SIGNALRANK_PLATFORM_API_ORIGIN;
 try {
  for(const origin of ['', 'https://user:secret@backend.example.test']) {
   process.env.SIGNALRANK_PLATFORM_API_ORIGIN=origin;
   assert.equal((await proxyPlatformRequest(new Request('https://web.example.test/api/v1/platform/me'),async()=>{throw new Error('must not send');})).status,503);
  }
  process.env.SIGNALRANK_PLATFORM_API_ORIGIN='https://backend.example.test';
  for(const path of ['/api/v1/platform-evil','/api/v1/platform/%2e%2e/operator',
    '/api/v1/platform/%2e%2e%2foperator','/api/v1/platform/%252e%252e/operator','/version']) {
   assert.equal((await proxyPlatformRequest(new Request('https://web.example.test'+path),async()=>{throw new Error('must not send');})).status,404);
  }
 } finally {if(old===undefined)delete process.env.SIGNALRANK_PLATFORM_API_ORIGIN;else process.env.SIGNALRANK_PLATFORM_API_ORIGIN=old;}
});
