import assert from "node:assert/strict";
import test from "node:test";

import { decodeCanonical, encodeCanonical, Tagged } from "../src/cbor.js";
import { decodeOperatorId, deriveOperatorId, encodeOperatorId } from "../src/identity.js";

test("canonical CBOR round-trips supported deterministic values", () => {
  const value = new Map([[1, 24], [2, Buffer.from("abcd", "hex")], [3, [true, false, null, "ok"]], [4, new Tagged(18, [1])]]);
  const bytes = encodeCanonical(value, { allowTag18: true });
  assert.ok(encodeCanonical(decodeCanonical(bytes, { allowTag18: true }), { allowTag18: true }).equals(bytes));
});

test("canonical CBOR rejects non-shortest integers and unordered maps", () => {
  assert.throws(() => decodeCanonical(Buffer.from("1817", "hex")), /non-shortest/);
  assert.throws(() => decodeCanonical(Buffer.from("a202000100", "hex")), /map key order/);
});

test("derives and round-trips the approved Operator ID vector", () => {
  const binary = deriveOperatorId(Buffer.from(Array.from({ length: 32 }, (_, i) => i)));
  assert.equal(binary.toString("hex"), "56c83296d5d62b74a9f161125c5fc9b441fb8f85b174606f3379ca57503e1e86");
  const text = encodeOperatorId(binary);
  assert.equal(text, "nbsr12myr99k46c4hf203vyf9ch7fk3qlhru9k96xqmen0899w5p7r6rqgutt5k");
  assert.ok(decodeOperatorId(text).equals(binary));
  assert.throws(() => decodeOperatorId(text.toUpperCase()), /canonical lowercase/);
  assert.throws(() => decodeOperatorId(`${text.slice(0, -1)}q`), /checksum/);
});
