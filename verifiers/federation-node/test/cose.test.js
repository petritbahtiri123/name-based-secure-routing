import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { publicKeyFromRaw, verifySign1 } from "../src/cose.js";
const PUBLIC_KEY=publicKeyFromRaw(Buffer.from("43046bfe4092b3e94994eada15dcc20d8aaa07b658fd3954eb8e0efb8bdca5de","hex"));

const vectorsPath = path.resolve(import.meta.dirname, "../../../vectors/federation-v0.1/signed-vectors.json");

test("cryptographically verifies all valid signed vectors", async () => {
  const fixture = JSON.parse(await readFile(vectorsPath, "utf8"));
  const publicKey = PUBLIC_KEY;
  for (const vector of fixture.vectors.filter((item) => item.expected === "ACCEPT")) {
    const result = verifySign1(Buffer.from(vector.cose_sign1_hex, "hex"), publicKey);
    assert.equal(result.kid.toString("hex"), vector.kid_hex);
    assert.equal(result.payloadDigest, vector.payload_sha256);
  }
});

test("rejects mutated payload, signature, and malformed Sign1", async () => {
  const fixture = JSON.parse(await readFile(vectorsPath, "utf8"));
  const publicKey = PUBLIC_KEY;
  const bytes = Buffer.from(fixture.vectors[0].cose_sign1_hex, "hex");
  for (const offset of [Math.floor(bytes.length / 2), bytes.length - 1]) {
    const changed = Buffer.from(bytes); changed[offset] ^= 1;
    assert.throws(() => verifySign1(changed, publicKey));
  }
  assert.throws(() => verifySign1(Buffer.from("d284", "hex"), publicKey), /CBOR/);
});
