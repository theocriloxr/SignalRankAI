/** Browser transport for the canonical cookie-authenticated platform API.
 * All endpoints stay same-origin and no access/refresh token enters JS storage. */
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
let pendingRefresh: Promise<boolean> | null = null;

export function csrfCookie(cookie: string): string | null {
  const value = cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("sr_csrf="));
  if (!value) return null;
  try { return decodeURIComponent(value.slice("sr_csrf=".length)) || null; }
  catch { return null; }
}

/** Single-flight web-cookie refresh, initiated only for a failed idempotent read.
 * A mutation is NEVER automatically replayed after a 401: doing so could double
 * payments, broker operations, support writes or simulation state changes. */
async function refreshCookieSession(requestUrl: string): Promise<boolean> {
  if(typeof document==="undefined") return false;
  const csrf=csrfCookie(document.cookie);
  if(!csrf) return false;
  if(!pendingRefresh){
    const destination=new URL("/api/v1/platform/auth/refresh",requestUrl);
    const task=(async()=>{
      try{
        const result=await fetch(new Request(destination.href,{
          method:"POST",
          credentials:"include",
          headers:{"Content-Type":"application/json","X-CSRF-Token":csrf,"X-SignalRank-Client":"web-next"},
          body:JSON.stringify({client_type:"web"}),
        }));
        return result.ok;
      }catch{return false;}
    })();
    pendingRefresh=task;
    void task.finally(()=>{if(pendingRefresh===task)pendingRefresh=null;});
  }
  return pendingRefresh;
}

export async function platformFetch(input: Request): Promise<Response> {
  const headers = new Headers(input.headers);
  const method=input.method.toUpperCase();
  if (!SAFE_METHODS.has(method) && typeof document !== "undefined") {
    const proof = csrfCookie(document.cookie);
    if (proof) headers.set("X-CSRF-Token", proof);
  }
  const first=await fetch(new Request(input, {credentials: "include", headers}));
  if(first.status!==401||!SAFE_METHODS.has(method)||typeof document==="undefined")return first;
  const path=new URL(input.url).pathname;
  if(!path.startsWith("/api/v1/platform/")||path.startsWith("/api/v1/platform/auth/"))return first;
  const refreshed=await refreshCookieSession(input.url);
  if(!refreshed)return first;
  // One retry of an idempotent read only, using newly rotated HttpOnly cookies.
  // Another 401 remains 401; refresh loops and replay of writes are forbidden.
  return fetch(new Request(input, {credentials:"include",headers}));
}
