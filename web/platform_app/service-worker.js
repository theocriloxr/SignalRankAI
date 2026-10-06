const CACHE='signalrank-shell-v43';
const ASSETS=['/app','/app-assets/styles.css?v=43','/app-assets/app.js?v=43','/app-assets/icon.svg?v=43','/app-assets/logo.svg?v=43','/app/manifest.webmanifest?v=43'];
const SHELL_ASSETS=new Set(ASSETS.filter(path=>path!=='/app'));
const isWorkspacePath=path=>path==='/app'||path.startsWith('/app/');
self.addEventListener('install',event=>event.waitUntil((async()=>{
  const cache=await caches.open(CACHE);
  await cache.addAll(ASSETS);
  await self.skipWaiting();
})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{
  const keys=await caches.keys();
  await Promise.all(keys.filter(key=>key.startsWith('signalrank-shell-')&&key!==CACHE).map(key=>caches.delete(key)));
  await self.clients.claim();
})()));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
  const navigation=event.request.mode==='navigate'&&isWorkspacePath(url.pathname);
  const publicAsset=SHELL_ASSETS.has(url.pathname+url.search);
  // Never intercept API, authentication, diagnostic, third-party or user data.
  if(!navigation&&!publicAsset)return;
  event.respondWith((async()=>{
    try{
      const response=await fetch(event.request);
      if(publicAsset&&response.ok&&!response.redirected&&response.type==='basic'){
        const cache=await caches.open(CACHE);
        await cache.put(event.request,response.clone());
      }
      return response;
    }catch{
      const cache=await caches.open(CACHE);
      const cached=await cache.match(navigation?'/app':event.request);
      return cached||Response.error();
    }
  })());
});
