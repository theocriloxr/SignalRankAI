import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';

const source = readFileSync(new URL('../web/platform_app/service-worker.js', import.meta.url), 'utf8');
function worker({ offline = false, response = { ok: true, redirected: false, type: 'basic', clone() { return this; } } } = {}) {
  const listeners = {}, writes = [], deleted = [], lookups = [];
  const cache = { async put(request) { writes.push(request.url); }, async match(request) { lookups.push(request); return { cached: true }; } };
  runInNewContext(source, {
    URL, Set, Response,
    self: { location: { origin: 'https://example.test' }, addEventListener(name, handler) { listeners[name] = handler; }, clients: { async claim() {} } },
    caches: { async open() { return cache; }, async keys() { return ['unrelated-app-cache', 'signalrank-shell-v38', 'signalrank-shell-v39']; }, async delete(key) { deleted.push(key); } },
    async fetch() { if (offline) throw new Error('offline'); return response; },
  });
  async function request(path, { method = 'GET', mode = 'cors' } = {}) {
    let pending;
    listeners.fetch({ request: { url: new URL(path, 'https://example.test').href, method, mode }, respondWith(value) { pending = value; } });
    if (pending) await pending;
    return Boolean(pending);
  }
  return { request, writes, lookups, deleted, async activate() { let pending; listeners.activate({ waitUntil(value) { pending = value; } }); await pending; } };
}

test('private data, diagnostics and third-party requests bypass offline storage', async () => {
  const w = worker();
  for (const path of ['/api/v1/platform/me', '/readyz', '/auth/callback?token=private', '/unrelated', 'https://third-party.test/app-assets/app.js?v=39']) {
    assert.equal(await w.request(path), false, path);
  }
  assert.equal(await w.request('/app-assets/app.js?v=39', { method: 'POST' }), false);
  assert.deepEqual(w.writes, []);
});
test('only successful nonredirected public assets are refreshed', async () => {
  const w = worker();
  assert.equal(await w.request('/app-assets/styles.css?v=39'), true);
  assert.equal(w.writes.length, 1);
  await w.request('/app?token=private', { mode: 'navigate' });
  assert.equal(w.writes.length, 1);
  for (const response of [{ ok: false, redirected: false, type: 'basic' }, { ok: true, redirected: true, type: 'basic' }]) {
    const invalid = worker({ response });
    await invalid.request('/app-assets/app.js?v=39');
    assert.deepEqual(invalid.writes, []);
  }
});
test('offline navigation uses the public shell; assets use their own cached content', async () => {
  const w = worker({ offline: true });
  await w.request('/app?activation_token=private', { mode: 'navigate' });
  assert.equal(w.lookups[0], '/app');
  await w.request('/app-assets/styles.css?v=39');
  assert.equal(w.lookups[1].url, 'https://example.test/app-assets/styles.css?v=39');
});
test('activation retires only this apps old shell caches', async () => {
  const w = worker(); await w.activate();
  assert.deepEqual(w.deleted, ['signalrank-shell-v38']);
});
