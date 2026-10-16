const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const test = require('node:test');
const xcode = require('xcode');
// Resolve from the actual consumer, including when npm nests its dependency.
const uuid = createRequire(require.resolve('xcode'))('uuid');

test('xcode generates unique project references with its installed UUID dependency', () => {
  const project = xcode.project('dependency-contract.pbxproj');
  project.hash = { project: { objects: { PBXGroup: {} } } };
  const references = project.hash.project.objects.PBXGroup;
  for (let index = 0; index < 256; index += 1) {
    const id = project.generateUuid();
    assert.match(id, /^[A-F0-9]{24}$/);
    assert.equal(Object.hasOwn(references, id), false);
    references[id] = { isa: 'PBXGroup', children: [], sourceTree: '"<group>"' };
  }
  assert.equal(project.allUuids().length, 256);
  const serialized = project.writeSync();
  for (const id of Object.keys(references)) assert.ok(serialized.includes(id));
});

for (const version of ['v3', 'v5', 'v6']) {
  const generate = (buffer, offset) => version === 'v6'
    ? uuid.v6({}, buffer, offset)
    : uuid[version]('signalrank-dependency-contract', uuid[version].DNS, buffer, offset);

  test(`${version} rejects invalid buffer ranges without partial writes`, () => {
    for (const [size, offset] of [[15, 0], [16, -1], [16, 1]]) {
      const buffer = Buffer.alloc(size, 0xa5);
      const before = Buffer.from(buffer);
      assert.throws(() => generate(buffer, offset), RangeError);
      assert.deepEqual(buffer, before);
    }
  });

  test(`${version} writes a valid UUID within the requested buffer range`, () => {
    const buffer = Buffer.alloc(20, 0xa5);
    assert.equal(generate(buffer, 2), buffer);
    assert.deepEqual(buffer.subarray(0, 2), Buffer.alloc(2, 0xa5));
    assert.deepEqual(buffer.subarray(18), Buffer.alloc(2, 0xa5));
    assert.equal(uuid.version(uuid.stringify(buffer.subarray(2, 18))), Number(version[1]));
  });
}
