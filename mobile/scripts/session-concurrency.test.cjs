const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}
function response(status, payload) { return {status, ok: status >= 200 && status < 300, json: async () => payload}; }
function client(fetch, options = {}) {
  const tokens = new Map([['signalrank.access_token', 'old-access'], ['signalrank.refresh_token', 'old-refresh']]);
  const source = fs.readFileSync(path.join(__dirname, '../src/api.ts'), 'utf8');
  const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
  const exports = {};
  vm.runInNewContext(compiled, {exports, process: {env: {EXPO_PUBLIC_API_URL: 'https://local.test'}}, fetch,
    require: name => {
      assert.equal(name, 'expo-secure-store');
      return {getItemAsync: async key => tokens.get(key) || null,
        setItemAsync: async (key, value) => {if (options.failRefreshWrite && key.endsWith('refresh_token')) throw new Error('device locked'); tokens.set(key, value);},
        deleteItemAsync: async key => {tokens.delete(key);}};
    }});
  return {api: exports, tokens};
}

test('concurrent expired requests share one refresh and preserve rotating tokens', async () => {
  const refreshing = deferred(), started = deferred();
  let refreshCalls = 0, oldCalls = 0;
  const {api, tokens} = client(async (url, init) => {
    if (url.endsWith('/auth/refresh')) {refreshCalls++; started.resolve(); await refreshing.promise; return response(200, {access_token: 'new-access', refresh_token: 'new-refresh'});}
    if (init.headers.Authorization === 'Bearer old-access') {oldCalls++; return response(401, {detail: 'expired'});}
    assert.equal(init.headers.Authorization, 'Bearer new-access');
    return response(200, {user: {id: 123}});
  });
  const one = api.api('/me'), two = api.api('/account');
  await started.promise;
  await new Promise(done => setImmediate(done));
  assert.equal(oldCalls, 2);
  assert.equal(refreshCalls, 1);
  refreshing.resolve();
  const results = await Promise.all([one, two]);
  assert.ok(results.every(result => result.user.id === 123));
  assert.equal(tokens.get('signalrank.refresh_token'), 'new-refresh');
});

test('logout invalidates an in-flight refresh and never restores tokens', async () => {
  const refreshing = deferred(), started = deferred();
  const {api, tokens} = client(async url => {
    if (url.endsWith('/auth/refresh')) {started.resolve(); await refreshing.promise; return response(200, {access_token: 'late-access', refresh_token: 'late-refresh'});}
    return response(401, {detail: 'expired'});
  });
  const pending = api.api('/me');
  const rejected = assert.rejects(pending, error => error.code === 'session_changed');
  await started.promise;
  await api.clearSession();
  refreshing.resolve();
  await rejected;
  assert.equal(tokens.size, 0);
});

test('late account responses cannot become data for a newly signed-in account', async () => {
  const oldRequest = deferred(), started = deferred();
  const {api, tokens} = client(async url => {
    if (url.endsWith('/auth/login')) return response(200, {user: {id: 456}, access_token: 'actor-456', refresh_token: 'refresh-456'});
    started.resolve(); await oldRequest.promise;
    return response(200, {user: {id: 123}});
  });
  const pending = api.api('/me');
  const rejected = assert.rejects(pending, error => error.code === 'session_changed');
  await started.promise;
  assert.equal((await api.login('new@test.local', 'fixture-only')).user.id, 456);
  oldRequest.resolve();
  await rejected;
  assert.equal(tokens.get('signalrank.access_token'), 'actor-456');
});

test('a login response arriving after logout cannot reauthenticate', async () => {
  const loggingIn = deferred(), started = deferred();
  const {api, tokens} = client(async () => {started.resolve(); await loggingIn.promise; return response(200, {access_token: 'late-access', refresh_token: 'late-refresh'});});
  const pending = api.login('test@test.local', 'fixture-only');
  const rejected = assert.rejects(pending, error => error.code === 'session_changed');
  await started.promise;
  await api.clearSession();
  loggingIn.resolve();
  await rejected;
  assert.equal(tokens.size, 0);
});

test('transient refresh failures retain the session for a later retry', async () => {
  const {api, tokens} = client(async url => response(url.endsWith('/auth/refresh') ? 503 : 401, {detail: 'temporarily unavailable'}));
  await assert.rejects(api.api('/me'), error => error.status === 503);
  assert.equal(tokens.get('signalrank.access_token'), 'old-access');
  assert.equal(tokens.get('signalrank.refresh_token'), 'old-refresh');
  assert.equal(api.getSessionGeneration(), 0);
});

test('invalid refresh tokens clear credentials and report the expired generation', async () => {
  const {api, tokens} = client(async () => response(401, {detail: 'invalid token'}));
  await assert.rejects(api.api('/me'), error => error.status === 401 && error.code === 'session_expired' && error.generation === api.getSessionGeneration());
  assert.equal(tokens.size, 0);
});

test('partial secure-store writes fail closed and cannot authorize a request', async () => {
  let authorization;
  const {api, tokens} = client(async (_url, init) => {authorization = init.headers.Authorization; return response(401, {detail: 'sign in'});}, {failRefreshWrite: true});
  await assert.rejects(api.storeSession({access_token: 'partial-access', refresh_token: 'partial-refresh'}), error => error.code === 'session_storage_failed');
  assert.equal(tokens.size, 0);
  await assert.rejects(api.api('/me'), error => error.status === 401);
  assert.equal(authorization, undefined);
});
