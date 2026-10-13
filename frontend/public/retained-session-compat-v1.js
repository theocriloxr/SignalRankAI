/* Release failed refresh streams discarded by older retained workspaces.
 * Preserve the original response, authentication result and one request only. */
(() => {
  const send = window.fetch.bind(window);
  window.fetch = async (input, options) => {
    const response = await send(input, options);
    try {
      const request = input instanceof Request ? input : null;
      const url = new URL(request ? request.url : String(input), window.location.href);
      const method = String(options?.method || request?.method || 'GET').toUpperCase();
      if (url.origin !== window.location.origin || url.pathname !== '/api/v1/platform/auth/refresh' ||
          method !== 'POST' || response.ok) return response;
      // Reading a clone completes the browser connection while preserving the
      // original error payload for clients that do consume it. Bound both work
      // and duration; this adapter never refreshes or replays a request itself.
      const reader = response.clone().body?.getReader();
      if (!reader) return response;
      const timer = setTimeout(() => { void reader.cancel().catch(() => {}); }, 10000);
      let size = 0;
      try {
        while (true) {
          const {done,value} = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 65536) { void reader.cancel().catch(() => {}); break; }
        }
      } finally { clearTimeout(timer); }
    } catch { /* Preserve the backend response even if cleanup is interrupted. */ }
    return response;
  };
})();
