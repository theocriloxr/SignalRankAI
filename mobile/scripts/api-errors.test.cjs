const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function client(status, detail) {
  const source = fs.readFileSync(path.join(__dirname, '../src/api.ts'), 'utf8');
  const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
  const exports = {};
  vm.runInNewContext(compiled, {
    exports, process: {env: {EXPO_PUBLIC_API_URL: 'https://local.test'}},
    require: name => {
      assert.equal(name, 'expo-secure-store');
      return {getItemAsync: async () => null};
    },
    fetch: async () => ({status, ok: false, json: async () => ({detail})}),
  });
  return exports;
}

for (const code of ['telegram_already_linked', 'telegram_verified_merge_pending']) {
  test(`preserves ${code} for safe account reconciliation`, async () => {
    const api = client(409, {code, message: 'Telegram is already verified. Refresh status.'});
    await assert.rejects(api.createTelegramLink(), error => {
      assert.ok(error instanceof api.PlatformAPIError);
      assert.equal(error.status, 409);
      assert.equal(error.code, code);
      assert.equal(error.message, 'Telegram is already verified. Refresh status.');
      return true;
    });
  });
}

test('transient service failures preserve status and a readable message', async () => {
  const api = client(503, 'Account sync temporarily unavailable');
  await assert.rejects(api.api('/me'), error => {
    assert.equal(error.status, 503);
    assert.equal(error.message, 'Account sync temporarily unavailable');
    return true;
  });
});

test('unstructured validation data never becomes an object string', async () => {
  const api = client(422, [{loc: ['body'], msg: 'invalid'}]);
  await assert.rejects(api.createTelegramLink(), error => {
    assert.equal(error.status, 422);
    assert.equal(error.message, 'Request failed (422)');
    return true;
  });
});
