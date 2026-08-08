import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { publicKeyFromRaw, verifySign1 } from "../src/cose.js";

const vectorsPath = path.resolve(import.meta.dirname, "../../../vectors/federation-v0.1/signed-vectors.json");

test("cryptographically verifies all valid signed vectors", async () => {
  const fixture = JSON.parse(await readFile(vectorsPath, "utf8"));
  const signers=new Map(fixture.trusted_signers.map(record=>[record.kid,record]));
  for (const vector of fixture.vectors.filter((item) => item.expected === "ACCEPT")) {
    const publicKey=publicKeyFromRaw(Buffer.from(signers.get(vector.kid_hex).signing_public_key,"hex"));
    const result = verifySign1(Buffer.from(vector.cose_sign1_hex, "hex"), publicKey);
    assert.equal(result.kid.toString("hex"), vector.kid_hex);
    assert.equal(result.payloadDigest, vector.payload_sha256);
  }
});

test("rejects mutated payload, signature, and malformed Sign1", async () => {
  const fixture = JSON.parse(await readFile(vectorsPath, "utf8"));
  const record=fixture.trusted_signers.find(item=>item.kid===fixture.vectors[0].kid_hex);
  const publicKey=publicKeyFromRaw(Buffer.from(record.signing_public_key,"hex"));
  const bytes = Buffer.from(fixture.vectors[0].cose_sign1_hex, "hex");
  for (const offset of [Math.floor(bytes.length / 2), bytes.length - 1]) {
    const changed = Buffer.from(bytes); changed[offset] ^= 1;
    assert.throws(() => verifySign1(changed, publicKey));
  }
  assert.throws(() => verifySign1(Buffer.from("d284", "hex"), publicKey), /CBOR/);
});
