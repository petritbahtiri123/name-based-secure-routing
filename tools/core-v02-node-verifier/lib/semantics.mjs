import path from "node:path";

import {
  CborError,
  decodeDeterministic,
  encodeDeterministic,
} from "./cbor.mjs";
import {
  CryptoVerificationError,
  loadPublicKeyHex,
  sha256,
  verifyCoseSign1,
  verifyProof,
} from "./crypto.mjs";

export const ERROR = Object.freeze({
  PROFILE: "NBSR_E_PROFILE_UNSUPPORTED",
  CAPACITY: "NBSR_E_OVER_CAPACITY",
  GRANT_INVALID: "NBSR_E_GRANT_INVALID",
  GRANT_EXPIRED: "NBSR_E_GRANT_EXPIRED",
  PROOF_INVALID: "NBSR_E_PROOF_INVALID",
  ROUTE_DENIED: "NBSR_E_ROUTE_DENIED",
  DOWNGRADE: "NBSR_E_DOWNGRADE",
});

export const FIXTURE_CONTEXT = Object.freeze({
  protocolVersion: 2,
  alpn: "nbsr-quic-1",
  now: 1_893_456_000,
  authorizedTransport: "tcp",
  authorizedPort: 8443,
  recordSequence: 42,
  maxClockSkewSeconds: 60,
  sourceOperatorId: "source.operator",
  sourceEdgeId: "source.edge",
  destinationOperatorId: "destination.operator",
  destinationEdgeId: "destination.edge",
  routeGrantKid: Buffer.from("nbsr-test-route-grant-key", "ascii"),
});

export class SemanticError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "SemanticError";
    this.code = code;
  }
}

class GenericClose extends Error {}

const TEXT_ID = /^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$/u;
const ENVELOPE_KEYS = [0, 1, 2, 3, 4, 5];
const BODY_KEYS = Object.freeze({
  1: [0, 1, 2, 3, 4, 5, 6, 7],
  2: [0, 1, 2, 3, 4, 5, 6],
  3: [0, 1, 2, 3, 4, 5, 6, 7],
  4: [0, 1, 2, 3, 4],
  5: [0, 1, 2, 3, 4],
  6: [0, 1, 2, 3, 4, 5, 6],
  7: [0, 1, 2, 3, 4],
  8: [0, 1, 2, 3, 4],
});
const ROUTE_GRANT_KEYS = Object.freeze([
  0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
]);

function reject(code, message) {
  throw new SemanticError(code, message);
}

function exactMap(value, keys, label) {
  if (!(value instanceof Map) || value.size !== keys.length) {
    reject(ERROR.PROFILE, `invalid ${label}`);
  }
  for (const key of keys) {
    if (!value.has(key)) {
      reject(ERROR.PROFILE, `invalid ${label}`);
    }
  }
  for (const key of value.keys()) {
    if (typeof key !== "number" || !Number.isSafeInteger(key) || !keys.includes(key)) {
      reject(ERROR.PROFILE, `invalid ${label}`);
    }
  }
  return value;
}

function uint(value, minimum = 0, maximum = 0xffffffffffffffffn) {
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value < minimum || BigInt(value) > maximum) {
      reject(ERROR.PROFILE, "invalid unsigned integer");
    }
    return value;
  }
  if (typeof value === "bigint" && value >= BigInt(minimum) && value <= maximum) {
    return value;
  }
  reject(ERROR.PROFILE, "invalid unsigned integer");
}

function bytes(value, length, label = "byte string") {
  if (!Buffer.isBuffer(value) || value.length !== length) {
    reject(ERROR.PROFILE, `invalid ${label}`);
  }
  return value;
}

function nonzeroBytes(value, length, label) {
  bytes(value, length, label);
  if (value.every((byte) => byte === 0)) {
    reject(ERROR.PROFILE, `invalid ${label}`);
  }
  return value;
}

function textId(value) {
  if (
    typeof value !== "string"
    || Buffer.byteLength(value, "ascii") !== Buffer.byteLength(value, "utf8")
    || value.length < 1
    || value.length > 64
    || !TEXT_ID.test(value)
  ) {
    reject(ERROR.PROFILE, "invalid textual identifier");
  }
  return value;
}

function timestamp(value) {
  return uint(value, 0, 253_402_300_799n);
}

function port(value) {
  return uint(value, 1, 65_535n);
}

function nearNow(value, context) {
  const valid = timestamp(value);
  if (typeof valid !== "number" || Math.abs(valid - context.now) > context.maxClockSkewSeconds) {
    reject(ERROR.PROFILE, "timestamp outside fixture skew");
  }
  return valid;
}

function orderedUniqueArray(value, itemValidator, minimum, maximum) {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) {
    reject(ERROR.PROFILE, "invalid ordered array");
  }
  let previous = null;
  for (const item of value) {
    itemValidator(item);
    const encoded = encodeDeterministic(item);
    if (previous !== null && Buffer.compare(previous, encoded) >= 0) {
      reject(ERROR.PROFILE, "array must be deterministic, ordered, and unique");
    }
    previous = encoded;
  }
  return value;
}

function validateProtocolError(value, requestId) {
  if (!(value instanceof Map) || ![4, 5].includes(value.size)) {
    reject(ERROR.PROFILE, "invalid ProtocolError");
  }
  const required = [0, 1, 2, 3];
  for (const key of required) {
    if (!value.has(key)) {
      reject(ERROR.PROFILE, "invalid ProtocolError");
    }
  }
  if (value.size === 5 && !value.has(4)) {
    reject(ERROR.PROFILE, "invalid ProtocolError");
  }
  if (value.get(0) !== 1) {
    reject(ERROR.PROFILE, "invalid ProtocolError version");
  }
  uint(value.get(1), 1, 19n);
  if (!bytes(value.get(2), 16).equals(requestId) || typeof value.get(3) !== "boolean") {
    reject(ERROR.PROFILE, "invalid ProtocolError binding");
  }
  if (value.has(4)) {
    uint(value.get(4), 1, 3_600n);
    if (value.get(3) !== true) {
      reject(ERROR.PROFILE, "invalid retry-after");
    }
  }
}

function validateRouteGrant(payload, context, checkCurrent = true) {
  const value = exactMap(decodeDeterministic(payload), ROUTE_GRANT_KEYS, "RouteGrant");
  if (value.get(0) !== 1) {
    reject(ERROR.PROFILE, "invalid RouteGrant version");
  }
  const grant = {
    routeId: bytes(value.get(1), 16, "route ID"),
    nameDigest: bytes(value.get(2), 32, "name digest"),
    serviceId: textId(value.get(3)),
    sourceOperatorId: textId(value.get(4)),
    sourceEdgeId: textId(value.get(5)),
    destinationOperatorId: textId(value.get(6)),
    destinationEdgeSet: orderedUniqueArray(value.get(7), textId, 1, 16),
    allowedTransports: orderedUniqueArray(value.get(8), textId, 1, 1),
    allowedPorts: orderedUniqueArray(value.get(9), port, 1, 32),
    clientSessionKeyThumbprint: bytes(value.get(10), 32, "session thumbprint"),
    notBefore: timestamp(value.get(11)),
    expiresAt: timestamp(value.get(12)),
    leaseId: bytes(value.get(13), 16, "lease ID"),
    recordSequence: uint(value.get(14), 1),
    policyHash: bytes(value.get(15), 32, "policy hash"),
    uniqueNonce: bytes(value.get(16), 16, "unique nonce"),
  };
  if (grant.allowedTransports.length !== 1 || grant.allowedTransports[0] !== "tcp") {
    reject(ERROR.PROFILE, "unsupported RouteGrant transport");
  }
  if (
    typeof grant.notBefore !== "number"
    || typeof grant.expiresAt !== "number"
    || grant.expiresAt <= grant.notBefore
    || grant.expiresAt - grant.notBefore > 600
  ) {
    reject(ERROR.GRANT_INVALID, "invalid RouteGrant validity window");
  }
  if (checkCurrent && (context.now < grant.notBefore || context.now >= grant.expiresAt)) {
    reject(ERROR.GRANT_EXPIRED, "RouteGrant is outside its validity interval");
  }
  if (
    grant.recordSequence !== context.recordSequence
    || grant.sourceOperatorId !== context.sourceOperatorId
    || grant.sourceEdgeId !== context.sourceEdgeId
    || grant.destinationOperatorId !== context.destinationOperatorId
    || !grant.destinationEdgeSet.includes(context.destinationEdgeId)
    || !grant.clientSessionKeyThumbprint.equals(sha256(context.sessionPublicKey))
    || !grant.policyHash.equals(context.policyHash)
  ) {
    reject(ERROR.GRANT_INVALID, "RouteGrant does not match the trust context");
  }
  return grant;
}

function verifyGrant(grantWire, context) {
  let verified;
  try {
    verified = verifyCoseSign1(grantWire, context.routeGrantPublicKey);
  } catch (error) {
    if (error instanceof CryptoVerificationError) {
      reject(
        error.kind === "signature" || error.kind === "key"
          ? ERROR.GRANT_INVALID
          : ERROR.PROFILE,
        "invalid RouteGrant COSE",
      );
    }
    throw error;
  }
  if (!verified.kid.equals(context.routeGrantKid)) {
    reject(ERROR.GRANT_INVALID, "RouteGrant kid does not match trust context");
  }
  return {
    grant: validateRouteGrant(verified.payload, context),
    payload: verified.payload,
  };
}

function validateProofTranscript(transcript) {
  const value = decodeDeterministic(transcript);
  if (!Array.isArray(value) || value.length !== 13 || value[0] !== "NBSR-ROUTE-OPEN-v2" || value[1] !== 2) {
    reject(ERROR.PROFILE, "invalid Route Open transcript");
  }
  bytes(value[2], 16);
  bytes(value[3], 16);
  bytes(value[4], 16);
  bytes(value[5], 16);
  textId(value[6]);
  textId(value[7]);
  bytes(value[8], 32);
  if (textId(value[9]) !== "tcp") {
    reject(ERROR.PROFILE, "unsupported proof transport");
  }
  port(value[10]);
  bytes(value[11], 32);
  timestamp(value[12]);
  return value;
}

function validateRouteOpen(body, requestId, sessionId, context) {
  nonzeroBytes(body.get(1), 16, "channel ID");
  const grantWire = body.get(2);
  if (!Buffer.isBuffer(grantWire) || grantWire.length < 1 || grantWire.length > 32_768) {
    reject(ERROR.PROFILE, "invalid RouteGrant wrapper");
  }
  const edgeNonce = nonzeroBytes(body.get(3), 32, "edge nonce");
  const transport = textId(body.get(4));
  if (transport !== "tcp") {
    reject(ERROR.PROFILE, "unsupported transport");
  }
  const requestedPort = port(body.get(5));
  const openedAt = nearNow(body.get(6), context);
  const proofSignature = bytes(body.get(7), 64, "proof signature");
  const {grant} = verifyGrant(grantWire, context);

  if (!grant.allowedTransports.includes(transport) || !grant.allowedPorts.includes(requestedPort)) {
    reject(ERROR.ROUTE_DENIED, "requested route is not authorized");
  }
  const grantDigest = sha256(grantWire);
  const transcript = encodeDeterministic([
    "NBSR-ROUTE-OPEN-v2",
    2,
    sessionId,
    requestId,
    body.get(1),
    grant.routeId,
    grant.serviceId,
    context.destinationEdgeId,
    edgeNonce,
    transport,
    requestedPort,
    grantDigest,
    openedAt,
  ]);
  try {
    verifyProof(transcript, proofSignature, context.sessionPublicKey);
  } catch (error) {
    if (error instanceof CryptoVerificationError) {
      reject(ERROR.PROOF_INVALID, "invalid Route Open proof");
    }
    throw error;
  }
}

function validateBody(messageType, body, requestId, sessionId, context) {
  exactMap(body, BODY_KEYS[messageType], "message body");
  if (body.get(0) !== 1) {
    reject(ERROR.PROFILE, "invalid body version");
  }
  if (messageType === 1) {
    if (
      textId(body.get(1)) !== context.sourceOperatorId
      || textId(body.get(2)) !== context.sourceEdgeId
      || textId(body.get(3)) !== context.destinationOperatorId
      || textId(body.get(4)) !== context.destinationEdgeId
    ) {
      reject(ERROR.ROUTE_DENIED, "HELLO identity mismatch");
    }
    nonzeroBytes(body.get(5), 32, "client nonce");
    if (!bytes(body.get(6), 32, "session public key").equals(context.sessionPublicKey)) {
      reject(ERROR.ROUTE_DENIED, "session public key mismatch");
    }
    nearNow(body.get(7), context);
    return;
  }
  if (messageType === 2) {
    if (textId(body.get(1)) !== context.sourceEdgeId || textId(body.get(2)) !== context.destinationEdgeId) {
      reject(ERROR.ROUTE_DENIED, "EDGE_HELLO identity mismatch");
    }
    nonzeroBytes(body.get(3), 32, "client nonce");
    nonzeroBytes(body.get(4), 32, "edge nonce");
    bytes(body.get(5), 32, "session thumbprint");
    nearNow(body.get(6), context);
    return;
  }
  if (messageType === 3) {
    validateRouteOpen(body, requestId, sessionId, context);
    return;
  }
  if (messageType === 4 || messageType === 5) {
    bytes(body.get(1), 16, "channel ID");
    bytes(body.get(2), 16, "route ID");
    bytes(body.get(3), 32, "RouteGrant digest");
    if (messageType === 4) {
      nearNow(body.get(4), context);
    } else {
      validateProtocolError(body.get(4), requestId);
    }
    return;
  }
  const streamId = uint(body.get(1), 4, (1n << 62n) - 1n);
  if (typeof streamId !== "number" || streamId % 4 !== 0) {
    reject(ERROR.PROFILE, "invalid source bidirectional QUIC stream");
  }
  bytes(body.get(2), 16, "channel ID");
  bytes(body.get(3), 16, "route ID");
  if (messageType === 6) {
    bytes(body.get(4), 32, "RouteGrant digest");
    if (textId(body.get(5)) !== "tcp") {
      reject(ERROR.PROFILE, "unsupported transport");
    }
    port(body.get(6));
  } else if (messageType === 7) {
    nearNow(body.get(4), context);
  } else {
    validateProtocolError(body.get(4), requestId);
  }
}

function validateEnvelope(wire, context) {
  const envelope = exactMap(decodeDeterministic(wire), ENVELOPE_KEYS, "ControlEnvelope");
  const version = envelope.get(0);
  if (
    (typeof version !== "number" && typeof version !== "bigint")
    || typeof version === "boolean"
  ) {
    reject(ERROR.PROFILE, "invalid protocol version");
  }
  uint(version);
  if (version !== 1 && version !== 2) {
    throw new GenericClose("unknown protocol version");
  }
  if (version !== 2) {
    reject(ERROR.DOWNGRADE, "Core version mismatch");
  }
  const messageType = uint(envelope.get(1), 1, 17n);
  if (typeof messageType !== "number" || !BODY_KEYS[messageType]) {
    reject(ERROR.PROFILE, "message has no approved Core v0.2 schema");
  }
  const requestId = bytes(envelope.get(2), 16, "request ID");
  const sessionId = bytes(envelope.get(3), 16, "session ID");
  uint(envelope.get(4), 1);
  validateBody(messageType, envelope.get(5), requestId, sessionId, context);
}

function mapCborFailure(error) {
  if (error instanceof CborError) {
    return {
      outcome: "reject",
      error: error.kind === "capacity" ? ERROR.CAPACITY : ERROR.PROFILE,
    };
  }
  throw error;
}

export async function createVerifierContext(vectorRoot, artifacts) {
  const routeGrantPublicKey = await loadPublicKeyHex(
    path.join(vectorRoot, "keys", "test-only-route-grant-ed25519-public.hex"),
  );
  const sessionPublicKey = await loadPublicKeyHex(
    path.join(vectorRoot, "keys", "test-only-session-ed25519-public.hex"),
  );
  const context = {
    ...FIXTURE_CONTEXT,
    routeGrantPublicKey,
    sessionPublicKey,
    policyHash: sha256(Buffer.from("nbsr-test-policy-v2", "ascii")),
    proofTranscript: artifacts.get("route-open-proof-transcript"),
  };
  return Object.freeze(context);
}

export function evaluateVector(entry, wire, context) {
  try {
    if (entry.id === "route-grant-payload") {
      validateRouteGrant(wire, context);
    } else if (entry.id === "route-grant-sign1") {
      verifyGrant(wire, context);
    } else if (entry.id === "route-open-proof-transcript") {
      validateProofTranscript(wire);
    } else if (entry.id === "route-open-proof-signature") {
      try {
        verifyProof(context.proofTranscript, wire, context.sessionPublicKey);
      } catch (error) {
        if (error instanceof CryptoVerificationError) {
          reject(ERROR.PROOF_INVALID, "invalid proof signature");
        }
        throw error;
      }
    } else if (entry.id === "client-hello-body") {
      validateBody(1, decodeDeterministic(wire), Buffer.alloc(16), Buffer.alloc(16), context);
    } else if (entry.id === "edge-hello-body") {
      validateBody(2, decodeDeterministic(wire), Buffer.alloc(16), Buffer.alloc(16), context);
    } else {
      validateEnvelope(wire, context);
    }
    return {outcome: "accept", error: null};
  } catch (error) {
    if (error instanceof GenericClose) {
      return {outcome: "close", error: null};
    }
    if (error instanceof SemanticError) {
      return {outcome: "reject", error: error.code};
    }
    return mapCborFailure(error);
  }
}
