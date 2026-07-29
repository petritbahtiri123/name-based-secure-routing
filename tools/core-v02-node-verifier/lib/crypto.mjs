import {
  createHash,
  createPublicKey,
  verify as verifySignature,
} from "node:crypto";
import { readFile } from "node:fs/promises";

import {
  CborError,
  CborTag,
  decodeDeterministic,
  encodeDeterministic,
} from "./cbor.mjs";

const ED25519_SPKI_PREFIX = Buffer.from("302a300506032b6570032100", "hex");

export class CryptoVerificationError extends Error {
  constructor(kind, message) {
    super(message);
    this.name = "CryptoVerificationError";
    this.kind = kind;
  }
}

function fail(kind, message) {
  throw new CryptoVerificationError(kind, message);
}

export function sha256(data) {
  if (!Buffer.isBuffer(data)) {
    fail("profile", "SHA-256 input must be a Buffer");
  }
  return createHash("sha256").update(data).digest();
}

export async function loadPublicKeyHex(filePath) {
  let text;
  try {
    text = await readFile(filePath, "utf8");
  } catch {
    fail("key", "unable to read public key");
  }
  if (!/^[0-9a-f]{64}\n$/u.test(text)) {
    fail("key", "invalid public-key file format");
  }
  return Buffer.from(text.slice(0, -1), "hex");
}

export function importRawEd25519PublicKey(raw) {
  if (!Buffer.isBuffer(raw) || raw.length !== 32) {
    fail("key", "Ed25519 public key must be 32 bytes");
  }
  try {
    return createPublicKey({
      key: Buffer.concat([ED25519_SPKI_PREFIX, raw]),
      format: "der",
      type: "spki",
    });
  } catch {
    fail("key", "invalid Ed25519 public key");
  }
}

function verifyEd25519(message, signature, publicKey) {
  if (!Buffer.isBuffer(message) || !Buffer.isBuffer(signature) || signature.length !== 64) {
    fail("profile", "invalid Ed25519 message or signature");
  }
  const key = importRawEd25519PublicKey(publicKey);
  let valid;
  try {
    valid = verifySignature(null, message, key, signature);
  } catch {
    fail("signature", "Ed25519 verification failed");
  }
  if (!valid) {
    fail("signature", "invalid Ed25519 signature");
  }
}

export function verifyCoseSign1(wire, publicKey) {
  let tagged;
  try {
    tagged = decodeDeterministic(wire, {allowTag18: true});
  } catch (error) {
    if (error instanceof CborError) {
      fail("profile", "invalid COSE CBOR profile");
    }
    throw error;
  }
  if (!(tagged instanceof CborTag) || tagged.tag !== 18) {
    fail("profile", "COSE Sign1 requires tag 18");
  }
  if (!Array.isArray(tagged.value) || tagged.value.length !== 4) {
    fail("profile", "COSE Sign1 must be a four-item array");
  }
  const [protectedBytes, unprotected, payload, signature] = tagged.value;
  if (!Buffer.isBuffer(protectedBytes) || protectedBytes.length === 0) {
    fail("profile", "COSE protected headers must be embedded bytes");
  }
  if (!(unprotected instanceof Map) || unprotected.size !== 0) {
    fail("profile", "COSE unprotected headers must be empty");
  }
  if (!Buffer.isBuffer(payload)) {
    fail("profile", "COSE payload must be embedded");
  }
  if (!Buffer.isBuffer(signature) || signature.length !== 64) {
    fail("profile", "COSE signature must be 64 bytes");
  }

  let protectedHeaders;
  try {
    protectedHeaders = decodeDeterministic(protectedBytes);
  } catch (error) {
    if (error instanceof CborError) {
      fail("profile", "invalid protected COSE headers");
    }
    throw error;
  }
  if (
    !(protectedHeaders instanceof Map)
    || protectedHeaders.size !== 2
    || protectedHeaders.get(1) !== -8
  ) {
    fail("profile", "COSE protected headers require only alg and kid");
  }
  const kid = protectedHeaders.get(4);
  if (!Buffer.isBuffer(kid) || kid.length < 1 || kid.length > 64) {
    fail("profile", "COSE kid must be an opaque byte string of 1 through 64 bytes");
  }

  const sigStructure = encodeDeterministic([
    "Signature1",
    protectedBytes,
    Buffer.alloc(0),
    payload,
  ]);
  verifyEd25519(sigStructure, signature, publicKey);
  return {
    payload: Buffer.from(payload),
    kid: Buffer.from(kid),
  };
}

export function verifyProof(transcript, signature, publicKey) {
  try {
    decodeDeterministic(transcript);
  } catch (error) {
    if (error instanceof CborError) {
      fail("profile", "invalid proof transcript");
    }
    throw error;
  }
  verifyEd25519(transcript, signature, publicKey);
}
