import assert from "node:assert/strict";
import test from "node:test";
import { parseStrictJson } from "../src/strict-json.js";

test("strict JSON rejects duplicate keys, excessive depth, and trailing data",()=>{
  assert.throws(()=>parseStrictJson(Buffer.from('{"a":1,"a":2}')),/duplicate JSON key/);
  assert.throws(()=>parseStrictJson(Buffer.from('[[[0]]]'),{maxDepth:2}),/JSON depth/);
  assert.throws(()=>parseStrictJson(Buffer.from('{}x')),/trailing JSON/);
});

test("strict JSON preserves exact ordinary JSON types",()=>{
  assert.deepEqual(parseStrictJson(Buffer.from('{"a":[1,-2,true,false,null,"x\\n"]}')),{a:[1,-2,true,false,null,"x\n"]});
});

test("strict JSON rejects unsafe integer rounding",()=>{
  assert.throws(()=>parseStrictJson(Buffer.from('{"n":9007199254740993}')),/safe integer/);
  assert.throws(()=>parseStrictJson(Buffer.from('{"n":9007199254740993.0}')),/safe integer/);
  assert.throws(()=>parseStrictJson(Buffer.from('{"n":9.007199254740993e15}')),/safe integer/);
});
