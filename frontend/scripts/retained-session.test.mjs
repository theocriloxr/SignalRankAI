import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const script=fs.readFileSync(new URL('../public/retained-session-compat-v1.js',import.meta.url),'utf8');
function adapter(fetch) {
 const window={fetch,location:{href:'https://web.example.test/app',origin:'https://web.example.test'}};
 vm.runInNewContext(script,{window,Request,URL,setTimeout,clearTimeout});
 return window.fetch;
}
test('failed refresh cleanup completes its stream and preserves the original error response',async()=>{
 let reads=0,calls=0;
 const stream=new ReadableStream({pull(controller){reads++;
  if(reads===1)controller.enqueue(new TextEncoder().encode('{"detail":'));
  else if(reads===2)controller.enqueue(new TextEncoder().encode('"expired"}'));
  else controller.close();}});
 const original=new Response(stream,{status:401,headers:{'Cache-Control':'no-store'}});
 const fetch=adapter(async()=>{calls++;return original;});
 const response=await fetch('/api/v1/platform/auth/refresh',{method:'POST'});
 assert.equal(calls,1);assert.equal(reads,3);assert.equal(response,original);
 assert.equal(response.bodyUsed,false);assert.equal(response.status,401);
 assert.deepEqual(await response.json(),{detail:'expired'});
});
test('other requests and successful refreshes retain their original unused body and are never replayed',async()=>{
 for(const [url,method,status] of [
  ['/api/v1/platform/brokers','POST',401],['/api/v1/platform/auth/refresh','GET',401],
  ['https://other.example.test/api/v1/platform/auth/refresh','POST',401],
  ['/api/v1/platform/auth/refresh','POST',200],
 ]) {
  let clones=0,calls=0;const original=new Response('original',{status});
  original.clone=()=>{clones++;throw new Error('must not consume');};
  const options={method};const fetch=adapter(async(input,init)=>{calls++;assert.equal(input,url);assert.equal(init,options);return original;});
  assert.equal(await fetch(url,options),original);assert.equal(calls,1);assert.equal(clones,0);assert.equal(original.bodyUsed,false);
 }
});
