// Independent Node byte/transcript verification, not runtime/wire authority.
import assert from 'node:assert/strict';
import {createHash, createHmac} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {resolve, dirname, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {decodeDeterministic, encodeDeterministic} from '../tools/core-v02-node-verifier/lib/cbor.mjs';

const root = resolve(process.argv[2] ?? resolve(dirname(fileURLToPath(import.meta.url)), '../vectors/connector-registration-v1-counter'));
const manifest = JSON.parse(readFileSync(resolve(root, 'manifest.json'), 'utf8'));
const hash = b => createHash('sha256').update(b).digest();
function load(name) {
  const path = resolve(root, name);
  assert(path.startsWith(root + sep));
  const data = readFileSync(path);
  assert.equal(data.length, manifest.artifacts[name].bytes, `length ${name}`);
  assert.equal(hash(data).toString('hex'), manifest.artifacts[name].sha256, `hash ${name}`);
  return data;
}
const limits = {maxTotalBytes: 16384, maxDepth: 8, maxArrayItems: 64, maxMapPairs: 16,
  maxTextBytes: 64, maxByteStringBytes: 64};
const decode = name => decodeDeterministic(load(name));
const enc = value => encodeDeterministic(value);
assert.equal(manifest.runtime_authorized, false);
assert.equal(manifest.case_count, 24);
assert.equal(new Set(manifest.cases.map(c => c.id)).size, 24);
assert(manifest.allocation_markers.every(s => s.startsWith('UNALLOCATED_')));
for (const name of Object.keys(manifest.artifacts)) load(name);
const requestRaw = load('request.cbor');
const request = decodeDeterministic(requestRaw, {limits});
const session = Buffer.from(manifest.session_id_hex, 'hex');
const rid = Buffer.from(manifest.request_id_hex, 'hex');
assert.equal(manifest.profile, 'connector-registration-v1-draft2');
assert.deepEqual(rid.subarray(0, 8), session.subarray(0, 8));
assert.equal(rid.readBigUInt64BE(8), 1n);
const challenge = decode('challenge.cbor');
const proof = decode('proof.cbor');
const accept = decode('accept.cbor');
const get = (map, key) => map.get(key);
assert.deepEqual([...request.keys()], Array.from({length: 16}, (_, i) => i));
assert.equal(get(request, 0), 1);
assert.equal(get(request, 1), 'register');
assert.equal(get(request, 13), 60);
assert.equal(get(request, 14), 100);
assert.equal(get(request, 15), null);
assert.deepEqual(get(request, 11), hash(enc(get(request, 10))));
assert.deepEqual(get(challenge, 1), hash(requestRaw));
assert.equal(get(challenge, 3), 105);
const context = enc(['NBSR-CONNECTOR-REGISTRATION-CONTEXT-v1', 1, session, rid,
  hash(requestRaw), get(challenge, 2), get(request, 4), get(request, 5), get(request, 6), get(request, 8), get(request, 12)]);
assert.deepEqual(load('context.cbor'), context);
function expand(secret, label, context) {
  const full = Buffer.from('tls13 ' + label, 'ascii');
  const info = Buffer.concat([Buffer.from([0, 32, full.length]), full, Buffer.from([context.length]), context]);
  return createHmac('sha256', secret).update(Buffer.concat([info, Buffer.from([1])])).digest();
}
const derived = expand(load('fixture-exporter-master.bin'), 'EXPORTER-NBSR-Connector-Registration-v1', hash(Buffer.alloc(0)));
const exported = expand(derived, 'exporter', hash(context));
assert.deepEqual(load('exporter.bin'), exported);
assert.deepEqual(get(proof, 3), exported);
assert.notDeepEqual(load('invalid-exporter.bin'), exported);
assert.deepEqual(get(proof, 1), hash(requestRaw));
assert.deepEqual(get(proof, 2), get(challenge, 2));
assert.equal(get(accept, 4), 1);
assert.equal(get(accept, 5), 100);
assert.equal(get(accept, 6), 160);
assert.equal(get(accept, 7), 130);
assert.deepEqual(get(accept, 1), hash(requestRaw));
assert.deepEqual(get(accept, 8), get(request, 11));
assert.deepEqual(get(accept, 9), get(request, 12));
const ad = hash(enc(['NBSR-CONNECTOR-ACCEPT-DIGEST-v1', 1, session, rid, accept]));
assert.deepEqual(load('accept-digest.bin'), ad);
assert.deepEqual(get(decode('withdraw.cbor'), 4), ad);
const reject = decode('reject.cbor');
assert.deepEqual(get(reject, 1), hash(requestRaw));
assert.equal(get(get(reject, 2), 1), 3);
assert.deepEqual(get(get(reject, 2), 2), rid);
const framed = load('request.frame');
const width = 1 << (framed[0] >> 6);
let length = framed[0] & 63;
for (let i = 1; i < width; i++) length = length * 256 + framed[i];
assert.equal(length, requestRaw.length);
assert.equal(width, length < 64 ? 1 : length < 16384 ? 2 : 4);
assert.deepEqual(framed.subarray(width), requestRaw);
for (const name of ['invalid-trailing.cbor', 'invalid-duplicate.cbor', 'invalid-nonpreferred.cbor', 'invalid-indefinite.cbor']) {
  assert.throws(() => decodeDeterministic(load(name), {limits}), name);
}
assert.equal(typeof get(decode('invalid-bool-lease.cbor'), 13), 'boolean');
assert.equal(decode('invalid-unknown-key.cbor').size, 17);
// Independent replay/cache reference, not the Python coordinator implementation.
const traces = JSON.parse(load('counter-traces.json').toString('utf8'));
let transitions = 0;
for (const trace of traces) {
  let high = BigInt(trace.seed_high_water), pending = null, current = null;
  const retained = new Map();
  for (const step of trace.steps) {
    const id = Buffer.from(step.request_id_hex, 'hex');
    const counter = id.readBigUInt64BE(8);
    const key = counter.toString();
    let outcome;
    if (!id.subarray(0, 8).equals(session.subarray(0, 8)) || counter === 0n) outcome = 'REPLAY';
    else if (step.kind === 'request') {
      if (retained.has(key)) outcome = !step.changed_body && current === key ? 'ACCEPT' : 'REPLAY';
      else if (pending === key) outcome = step.changed_body ? 'REPLAY' : 'CHALLENGE';
      else if (counter !== high + 1n) outcome = 'REPLAY';
      else if (pending !== null) outcome = 'OVER_CAPACITY';
      else { high = counter; pending = key; outcome = 'CHALLENGE'; }
    } else {
      assert.equal(step.kind, 'proof');
      if (pending !== key) outcome = 'REPLAY';
      else {
        pending = null; current = key; retained.set(key, true);
        while (retained.size > 4) retained.delete(retained.keys().next().value);
        outcome = 'ACCEPT';
      }
    }
    assert.equal(outcome, step.expected, `${trace.name}/${transitions}`);
    assert.equal(high.toString(), step.high_water);
    assert.equal(retained.size, step.retained);
    assert.equal(pending, step.pending);
    transitions++;
  }
}
console.log(`PASS: ${Object.keys(manifest.artifacts).length} artifact hashes; canonical transcript/TLS13 exporter/ACCEPT digest/framing; ${transitions} independent replay-cache transitions across ${traces.length} traces. Not live interoperability.`);
