import { createHash, createPublicKey, verify } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { decodeDeterministic, encodeDeterministic } from "../tools/core-v02-node-verifier/lib/cbor.mjs";

const root = process.argv[2] ?? "vectors/wp8-f75-route-open";
const profile = "nbsr-federation-dev-v1";
const sha256 = (value) => createHash("sha256").update(value).digest();
const artifact = (name) => readFile(join(root, name));

const [context, routeGrant, expectedBinding, expectedTranscript, signature, bodyWire, publicHex] = await Promise.all([
  artifact("federation-context.cbor"),
  artifact("route-grant.cose"),
  artifact("federation-binding.cbor"),
  artifact("transcript.cbor"),
  artifact("signature.bin"),
  artifact("route-open-body.cbor"),
  readFile("vectors/core-v0.2/keys/test-only-session-ed25519-public.hex", "ascii"),
]);

const routeGrantDigest = sha256(routeGrant);
const contextDigest = sha256(context);
const binding = new Map([
  [0, 1], [1, 1], [2, 1], [3, profile], [4, routeGrantDigest], [5, contextDigest],
]);
const bindingWire = encodeDeterministic(binding);
if (!bindingWire.equals(expectedBinding)) throw new Error("independent federation binding encoding diverged");

const body = decodeDeterministic(bodyWire);
if (!(body instanceof Map) || body.get(0) !== 2 || !body.get(2).equals(routeGrant)) {
  throw new Error("ROUTE_OPEN v2 body is inconsistent with carried RouteGrant bytes");
}
const transcript = [
  "NBSR-FED-ROUTE-OPEN",
  2,
  2,
  [1, 1, 1, profile],
  Buffer.from("101112131415161718191a1b1c1d1e1f", "hex"),
  Buffer.from("000102030405060708090a0b0c0d0e10", "hex"),
  body.get(1),
  Buffer.from("202122232425262728292a2b2c2d2e2f", "hex"),
  "destination.edge",
  body.get(3),
  body.get(4),
  "service.example",
  body.get(5),
  routeGrantDigest,
  body.get(6),
  contextDigest,
];
const transcriptWire = encodeDeterministic(transcript);
if (!transcriptWire.equals(expectedTranscript)) throw new Error("independent F75 transcript encoding diverged");

const rawPublic = Buffer.from(publicHex.trim(), "hex");
const spki = Buffer.concat([Buffer.from("302a300506032b6570032100", "hex"), rawPublic]);
const publicKey = createPublicKey({ key: spki, format: "der", type: "spki" });
if (!verify(null, transcriptWire, publicKey, signature)) throw new Error("F75 signature did not verify");

console.log("F75 Node parity verified: binding, transcript, digest, and signature");
