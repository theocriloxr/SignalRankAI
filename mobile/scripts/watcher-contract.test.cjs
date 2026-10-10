const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { createRequire } = require('node:module');
const test = require('node:test');

const metroRequire = createRequire(require.resolve('metro-file-map'));
const { includedByGlob } = metroRequire('./watchers/common.js');
const matcher = metroRequire('micromatch');

for (const [description, type, globs, dot, file, expected] of [
  ['included JavaScript', 'f', ['**/*.js'], false, 'src/feed.js', true],
  ['excluded extension', 'f', ['**/*.js'], false, 'src/feed.json', false],
  ['root pattern does not match nested file', 'f', ['*.js'], false, 'src/feed.js', false],
  ['brace alternatives', 'f', ['**/*.{js,ts}'], false, 'src/feed.ts', true],
  ['extended pattern', 'f', ['**/*.@(js|ts)'], false, 'src/feed.ts', true],
  ['hidden file excluded', 'f', ['**/*'], false, 'src/.feed.js', false],
  ['hidden file enabled', 'f', ['**/*'], true, 'src/.feed.js', true],
  ['empty filter still excludes hidden', 'f', [], false, '.env', false],
  ['empty filter includes visible', 'f', [], false, 'src/feed.js', true],
  ['directories bypass extension', 'd', ['**/*.js'], false, 'src/assets', true],
  ['hidden directory excluded', 'd', ['**/*.js'], false, '.cache', false],
  ['hidden directory enabled', 'd', ['**/*.js'], true, '.cache', true],
  ['negation matcher', 'f', ['!**/*.json'], false, 'src/feed.ts', true],
]) {
  test(`installed Metro watcher preserves ${description}`, () => {
    assert.equal(includedByGlob(type, globs, dot, file), expected);
  });
}

test('watcher adapter supports path lists and rejects API drift and excessive inputs', () => {
  assert.equal(matcher.some(['src/feed.ts', 'src/feed.json'], '**/*.ts'), true);
  assert.equal(matcher.some('src/feed.ts', []), false);
  assert.throws(() => matcher.some('feed.ts', '*.ts', { ignore: '*.ts' }), TypeError);
  assert.throws(() => matcher.some('feed.ts', '*.ts', { dot: 'yes' }), TypeError);
  assert.throws(() => matcher.some('a'.repeat(4097), '**/*'), TypeError);
  assert.throws(() => matcher.some('feed.ts', Array(257).fill('**/*')), TypeError);
});

test('hostile watcher patterns are rejected before stack exhaustion or glob compilation', () => {
  const script = `const assert=require('node:assert/strict'); const m=require(${JSON.stringify(metroRequire.resolve('micromatch'))});
    for (const depth of [65,12000]) assert.throws(()=>m.some('feed.ts','{'.repeat(depth)+'a'+'}'.repeat(depth)),/pattern/);`;
  const result = spawnSync(process.execPath, ['--max-old-space-size=128', '-e', script], { encoding: 'utf8', timeout: 5000 });
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stderr);
});
