import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { evaluateStaticVector } from "../src/schema.js";
import { evaluateThresholdVector } from "../src/threshold.js";
import { evaluateCapabilityVector } from "../src/capability.js";
import { loadAuthorities } from "../src/registry.js";
import { verifySignedFixture } from "../src/signed.js";
import { verifyStateFixture } from "../src/state.js";
import { verifyPrecedenceFixture } from "../src/precedence.js";
import { decodeCanonical, encodeCanonical } from "../src/cbor.js";

const dir=path.resolve(import.meta.dirname,"../../../vectors/federation-v0.1");
const load=async(name)=>JSON.parse(await readFile(path.join(dir,name),"utf8"));

test("threshold decisions do not depend on vector name or expected fields",async()=>{
  const authorities=await loadAuthorities(dir),fixture=await load("threshold-vectors.json"),vector=fixture.vectors.find(v=>v.id==="threshold-014-invalid-duplicate-signer");
  const renamed={...vector,name:"valid-renamed",expected_decision:"ACCEPT",expected_reason:"NONE"};
  assert.deepEqual(evaluateThresholdVector(vector,authorities),{outcome:"REJECT",reason:"ERR_AUTHORITY",mutation:false,enforcement:"DENY_NEW_USE"});
  assert.deepEqual(evaluateThresholdVector(renamed,authorities),evaluateThresholdVector(vector,authorities));
});

test("state decisions do not depend on descriptive object_kind labels",async()=>{
  const fixture=await load("stateful-scenarios.json"),copy=structuredClone(fixture);
  for(const [index,item] of copy.event_vectors.entries())if(item.federation_event.validation_failures.length)item.federation_event.object_kind=`renamed-${index}`;
  assert.equal(verifyStateFixture(copy),43);
});

test("schema recursively validates collection items and nested bounds",async()=>{
  const authorities=await loadAuthorities(dir),fixture=await load("static-vectors.json");
  const vector=fixture.vectors.find(v=>v.object_class==="ConsistencyProof"&&v.expected==="ACCEPT"),object=decodeCanonical(Buffer.from(vector.canonical_cbor_hex,"hex"));
  object.get(40).push(Buffer.alloc(31));
  const mutated={...vector,canonical_cbor_hex:encodeCanonical(object).toString("hex")};
  assert.deepEqual(evaluateStaticVector(mutated,authorities),{outcome:"REJECT",reason:"ERR_SCHEMA"});
});

test("signed verification rejects trusted signer identity mutation",async()=>{
  const fixture=await load("signed-vectors.json");
  const changed=structuredClone(fixture);changed.trusted_signers[0].operator_id="00".repeat(32);
  assert.throws(()=>verifySignedFixture(changed),/ERR_IDENTITY/);
});

test("signed payload digest remains a comparison oracle",async()=>{
  const fixture=await load("signed-vectors.json"),changed=structuredClone(fixture);changed.vectors[0].payload_sha256="00".repeat(32);
  assert.throws(()=>verifySignedFixture(changed),/payload digest oracle mismatch/);
});

test("signed authority JSON and hex fail closed",async()=>{
  const fixture=await load("signed-vectors.json");
  const mutations=[
    copy=>{copy.vectors[0].cose_sign1_hex+="0";},
    copy=>{copy.trusted_signers[0].unexpected=true;},
    copy=>{copy.trusted_signers[0].not_before+=0.5;},
    copy=>{copy.trusted_signers[0].generation+=0.5;copy.authority_state.generation+=0.5;},
    copy=>{copy.trusted_signers[0].revoked=0;},
    copy=>{copy.trusted_signers[1].signing_public_key=copy.trusted_signers[0].signing_public_key;},
  ];
  for(const mutate of mutations){const copy=structuredClone(fixture);mutate(copy);assert.throws(()=>verifySignedFixture(copy),/signed fixture|trusted signer inventory|canonical COSE hex/);}
});

test("capability replay decisions do not depend on case or expected fields",async()=>{
  const fixture=await load("capability-vectors.json"),vector=fixture.vectors.find(v=>v.id==="capability-12-different-session-replay"),renamed={...vector,case:"valid-renamed",expected_outcome:"ACCEPT",expected_reason:"NONE"};
  assert.deepEqual(evaluateCapabilityVector(renamed),evaluateCapabilityVector(vector));
  assert.deepEqual(evaluateCapabilityVector(vector),{outcome:"REJECT",reason:"ERR_REPLAY",enforcement:"DENY_NEW_USE",mutation:false});
});

test("static decisions do not depend on vector case or expected fields",async()=>{
  const authorities=await loadAuthorities(dir),fixture=await load("static-vectors.json"),vector=fixture.vectors.find(v=>v.id==="schema-oracle-unknown-critical-extension");
  const renamed={...vector,case:"canonical-encoding",expected:"ACCEPT",expected_reason:"NONE"};
  assert.deepEqual(evaluateStaticVector(renamed,authorities),evaluateStaticVector(vector,authorities));
  assert.deepEqual(evaluateStaticVector(vector,authorities),{outcome:"REJECT",reason:"ERR_UNSUPPORTED_CRITICAL"});
});

test("precedence is pinned independently of fixture ranks",async()=>{
  const fixture=await load("error-precedence.json"),copy=structuredClone(fixture);copy.precedence[0].rank=11;
  assert.throws(()=>verifyPrecedenceFixture(copy),/frozen precedence mismatch/);
});

test("state byte identifiers require canonical lowercase 32-byte hex",async()=>{
  const fixture=await load("stateful-scenarios.json");
  for(const mutate of [
    e=>{e.object_digest="AA".repeat(32);},e=>{e.operator_id="00".repeat(31);},e=>{e.dependencies=["zz".repeat(32)];},e=>{e.replay_digest="0".repeat(63);}
  ]){const copy=structuredClone(fixture);mutate(copy.event_vectors[0].federation_event);assert.throws(()=>verifyStateFixture(copy),/invalid state event .*hex/);}
});
