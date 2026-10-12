import assert from 'node:assert/strict';
import test from 'node:test';
import {canonicalApiOrigin,workspaceMode,backendOwnsPath} from '../src/lib/server-origin.ts';
import {observeService} from '../src/lib/public-status.ts';

test('proxy origin accepts only operator-owned HTTPS origins in production',()=>{
  const old = process.env.NODE_ENV;
  process.env.NODE_ENV = 'production';
  try {
    assert.equal(canonicalApiOrigin('https://api.example.test/'),'https://api.example.test');
    assert.equal(canonicalApiOrigin(''),null);
    for (const bad of ['http://api.example.test','http://127.0.0.1:1234','https://user:secret@api.example.test',
      'https://api.example.test/path','https://api.example.test?forward=evil','//evil.test','javascript:alert(1)']) {
      assert.throws(()=>canonicalApiOrigin(bad));
    }
  } finally {if(old===undefined)delete process.env.NODE_ENV; else process.env.NODE_ENV=old;}
});

test('public cutover preserves backend namespaces and only the configured workspace',()=>{
  for (const path of ['/api/v1/platform/me','/api/v1/telegram/webhook','/webhooks/paystack','/paystack/charge',
    '/webhook/paystack','/broker/exchange/link','/payout/request','/app-assets/app.js','/readyz','/version']) {
    assert.equal(backendOwnsPath(path,false),true,path);
  }
  for (const path of ['/app','/app/settings','/app/service-worker.js','/login','/recover','/magic-login']) {
    assert.equal(backendOwnsPath(path,true),true,path);
    assert.equal(backendOwnsPath(path,false),false,path);
  }
  for (const path of ['/product','/features','/markets','/api-evil','/app-malicious','/frontend-health']) {
    assert.equal(backendOwnsPath(path,true),false,path);
  }
  assert.equal(workspaceMode(''),'next');
  assert.equal(workspaceMode('legacy'),'legacy');
  assert.throws(()=>workspaceMode('everything-enabled'));
});

test('public status is bounded, uncached and cannot publish upstream payloads',async()=>{
  const old=process.env.SIGNALRANK_PLATFORM_API_ORIGIN;
  process.env.SIGNALRANK_PLATFORM_API_ORIGIN='https://api.example.test';
  try {
    const result=await observeService('/readyz',async(url,options)=>{
      assert.equal(url,'https://api.example.test/readyz');
      assert.equal(options.redirect,'error'); assert.equal(options.cache,'no-store');
      assert.ok(options.signal instanceof AbortSignal);
      return Response.json({status:'ready',checks:{database:true,redis:true},secret:'must never be exposed'});
    });
    assert.equal(result.state,'available');
    assert.deepEqual(Object.keys(result).sort(),['observedAt','state']);
    for (const [body,status,state] of [
      [{status:'ready',checks:{database:false}},200,'degraded'],
      [{status:'ready',checks:{}},200,'degraded'], [{},200,'unavailable'],
      [{secret:'raw-error'},503,'degraded'], [{},401,'unavailable'],
    ]) assert.equal((await observeService('/readyz',async()=>Response.json(body,{status}))).state,state);
    assert.equal((await observeService('/healthz',async()=>{throw new Error('private upstream exception')})).state,'unavailable');
    delete process.env.SIGNALRANK_PLATFORM_API_ORIGIN;
    assert.equal((await observeService('/healthz',async()=>{throw new Error('must not request')})).state,'unconfigured');
  } finally {if(old===undefined)delete process.env.SIGNALRANK_PLATFORM_API_ORIGIN; else process.env.SIGNALRANK_PLATFORM_API_ORIGIN=old;}
});
