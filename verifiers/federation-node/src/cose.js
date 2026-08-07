import { createHash, createPublicKey, verify } from "node:crypto";
import { decodeCanonical, encodeCanonical, Tagged } from "./cbor.js";

export function publicKeyFromRaw(raw) {
  if (!Buffer.isBuffer(raw) || raw.length !== 32) throw new Error("Ed25519 public key must be 32 bytes");
  return createPublicKey({ key: Buffer.concat([Buffer.from("302a300506032b6570032100", "hex"), raw]), format: "der", type: "spki" });
}
export function verifySign1(bytes, publicKey, expectedPayload = null) {
  const tagged = decodeCanonical(bytes, { allowTag18: true });
  if (!(tagged instanceof Tagged) || tagged.tag !== 18 || !Array.isArray(tagged.value) || tagged.value.length !== 4) throw new Error("malformed tagged COSE Sign1");
  const [protectedBytes, unprotected, payload, signature] = tagged.value;
  if (!Buffer.isBuffer(protectedBytes) || !(unprotected instanceof Map) || unprotected.size !== 0 || !Buffer.isBuffer(payload) || !Buffer.isBuffer(signature) || signature.length !== 64) throw new Error("malformed COSE Sign1 fields");
  const protectedMap = decodeCanonical(protectedBytes);
  if (!(protectedMap instanceof Map) || protectedMap.size !== 2 || protectedMap.get(1) !== -8) throw new Error("unsupported COSE protected algorithm/fields");
  const kid = protectedMap.get(4);
  if (!Buffer.isBuffer(kid) || kid.length === 0) throw new Error("COSE protected kid required");
  if (protectedMap.has(2)) throw new Error("unsupported COSE critical semantics");
  if (expectedPayload && !payload.equals(expectedPayload)) throw new Error("COSE payload binding mismatch");
  const structure = encodeCanonical(["Signature1", protectedBytes, Buffer.alloc(0), payload]);
  if (!verify(null, structure, publicKey, signature)) throw new Error("COSE Ed25519 signature invalid");
  return { kid, payload, protectedBytes, payloadDigest: createHash("sha256").update(payload).digest("hex") };
}
