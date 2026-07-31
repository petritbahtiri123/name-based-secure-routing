#!/usr/bin/env node

import { createHash, createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { isAbsolute, resolve, sep } from "node:path";
import process from "node:process";


const LABEL = Buffer.from("EXPORTER-NBSR-Service-Channel-v2", "ascii");
const CONTEXT_PROFILE = "NBSR-SERVICE-CHANNEL-CONTEXT-v2";
const CONTEXT_FIELDS = [
  "profile",
  "version",
  "session_id",
  "source_edge_id",
  "destination_edge_id",
  "channel_id",
  "route_id",
  "route_grant_digest",
  "service_id",
  "transport",
  "port",
  "policy_hash",
  "client_nonce",
  "edge_nonce",
];
const ARTIFACT_FIELDS = [
  "context_cbor",
  "context_hash",
  "derived_secret",
  "exporter_master_secret",
  "exporter_value",
];


function fail(reason) {
  throw new Error(reason);
}


function assert(condition, reason) {
  if (!condition) fail(reason);
}


function assertKeys(value, expected, reason) {
  assert(value !== null && typeof value === "object" && !Array.isArray(value), reason);
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  assert(JSON.stringify(actual) === JSON.stringify(wanted), reason);
}


function sha256(value) {
  return createHash("sha256").update(value).digest();
}


function hkdfExpand(secret, info, length) {
  assert(Number.isInteger(length) && length >= 0 && length <= 255 * 32, "hkdf-output-length");
  const blocks = [];
  let previous = Buffer.alloc(0);
  let produced = 0;
  for (let counter = 1; produced < length; counter += 1) {
    assert(counter <= 255, "hkdf-output-length");
    previous = createHmac("sha256", secret)
      .update(Buffer.concat([previous, info, Buffer.from([counter])]))
      .digest();
    blocks.push(previous);
    produced += previous.length;
  }
  return Buffer.concat(blocks).subarray(0, length);
}


function expandLabel(secret, label, context, length) {
  const fullLabel = Buffer.concat([Buffer.from("tls13 ", "ascii"), label]);
  assert(Number.isInteger(length) && length >= 0 && length <= 0xffff, "tls-label-output-length");
  assert(fullLabel.length <= 0xff, "tls-label-label-length");
  assert(context.length <= 0xff, "tls-label-context-length");
  const lengthBytes = Buffer.alloc(2);
  lengthBytes.writeUInt16BE(length);
  const info = Buffer.concat([
    lengthBytes,
    Buffer.from([fullLabel.length]),
    fullLabel,
    Buffer.from([context.length]),
    context,
  ]);
  return hkdfExpand(secret, info, length);
}


class PreferredCborParser {
  constructor(bytes) {
    assert(Buffer.isBuffer(bytes) && bytes.length > 0 && bytes.length <= 4096, "context-cbor-size");
    this.bytes = bytes;
    this.offset = 0;
    this.decoder = new TextDecoder("utf-8", { fatal: true });
  }

  take(length) {
    assert(Number.isInteger(length) && length >= 0, "cbor-length");
    assert(this.offset + length <= this.bytes.length, "cbor-truncated");
    const value = this.bytes.subarray(this.offset, this.offset + length);
    this.offset += length;
    return value;
  }

  argument(additional) {
    if (additional < 24) return additional;
    if (additional === 24) {
      const value = this.take(1)[0];
      assert(value >= 24, "non-canonical-cbor");
      return value;
    }
    if (additional === 25) {
      const value = this.take(2).readUInt16BE();
      assert(value > 0xff, "non-canonical-cbor");
      return value;
    }
    if (additional === 26) {
      const value = this.take(4).readUInt32BE();
      assert(value > 0xffff, "non-canonical-cbor");
      return value;
    }
    fail("unsupported-cbor-argument");
  }

  item(depth = 0) {
    assert(depth <= 2, "cbor-depth");
    const initial = this.take(1)[0];
    const major = initial >> 5;
    const additional = initial & 0x1f;
    assert(additional < 28, "unsupported-cbor-argument");
    const argument = this.argument(additional);
    if (major === 0) return { kind: "uint", value: argument };
    if (major === 2) return { kind: "bytes", value: Buffer.from(this.take(argument)) };
    if (major === 3) {
      let value;
      try {
        value = this.decoder.decode(this.take(argument));
      } catch {
        fail("invalid-utf8");
      }
      return { kind: "text", value };
    }
    if (major === 4) {
      assert(argument <= 14, "context-array-length");
      const value = [];
      for (let index = 0; index < argument; index += 1) value.push(this.item(depth + 1));
      return { kind: "array", value };
    }
    fail("unsupported-cbor-type");
  }

  parse() {
    const value = this.item();
    assert(this.offset === this.bytes.length, "cbor-trailing-bytes");
    return value;
  }
}


function kind(item, expected, reason) {
  assert(item.kind === expected, reason);
  return item.value;
}


function asciiId(value, minimum, maximum, reason) {
  assert(typeof value === "string" && value.length >= minimum && value.length <= maximum, reason);
  for (const character of value) assert(character.codePointAt(0) <= 0x7f, reason);
  return value;
}


function fixedBytes(item, length, name) {
  const value = kind(item, "bytes", `${name}-type`);
  assert(value.length === length, `${name}-length`);
  return value;
}


function parseContext(bytes) {
  const root = new PreferredCborParser(bytes).parse();
  const items = kind(root, "array", "context-array-type");
  assert(items.length === 14, "context-array-length");
  const profile = kind(items[0], "text", "profile-type");
  assert(profile === CONTEXT_PROFILE, "profile-mismatch");
  const version = kind(items[1], "uint", "version-type");
  assert(version === 2, "version-mismatch");
  const sessionId = fixedBytes(items[2], 16, "session-id");
  const sourceEdgeId = asciiId(
    kind(items[3], "text", "source-edge-id-type"),
    1,
    64,
    "source-edge-id-invalid",
  );
  const destinationEdgeId = asciiId(
    kind(items[4], "text", "destination-edge-id-type"),
    1,
    64,
    "destination-edge-id-invalid",
  );
  const channelId = fixedBytes(items[5], 16, "channel-id");
  const routeId = fixedBytes(items[6], 16, "route-id");
  const routeGrantDigest = fixedBytes(items[7], 32, "route-grant-digest");
  const serviceId = asciiId(
    kind(items[8], "text", "service-id-type"),
    1,
    255,
    "service-id-invalid",
  );
  const transport = kind(items[9], "text", "transport-type");
  assert(transport === "tcp" || transport === "udp", "transport-invalid");
  const port = kind(items[10], "uint", "port-type");
  assert(port >= 1 && port <= 65535, "port-invalid");
  const policyHash = fixedBytes(items[11], 32, "policy-hash");
  const clientNonce = fixedBytes(items[12], 32, "client-nonce");
  const edgeNonce = fixedBytes(items[13], 32, "edge-nonce");
  return {
    profile,
    version,
    session_id: sessionId.toString("hex"),
    source_edge_id: sourceEdgeId,
    destination_edge_id: destinationEdgeId,
    channel_id: channelId.toString("hex"),
    route_id: routeId.toString("hex"),
    route_grant_digest: routeGrantDigest.toString("hex"),
    service_id: serviceId,
    transport,
    port,
    policy_hash: policyHash.toString("hex"),
    client_nonce: clientNonce.toString("hex"),
    edge_nonce: edgeNonce.toString("hex"),
  };
}


function deriveServiceChannel(masterSecret, contextCbor, label = LABEL, outputLength = 32) {
  assert(Buffer.isBuffer(masterSecret) && masterSecret.length === 32, "master-secret-length");
  assert(Buffer.isBuffer(label) && label.equals(LABEL), "wrong-label");
  assert(outputLength === 32, "wrong-output-length");
  parseContext(contextCbor);
  const contextHash = sha256(contextCbor);
  const derivedSecret = expandLabel(masterSecret, LABEL, sha256(Buffer.alloc(0)), 32);
  const exporterValue = expandLabel(derivedSecret, Buffer.from("exporter", "ascii"), contextHash, 32);
  return { contextHash, derivedSecret, exporterValue };
}


function loadArtifact(packageRoot, metadata) {
  assertKeys(metadata, ["length", "path", "sha256"], "artifact-schema");
  assert(typeof metadata.path === "string" && metadata.path.length > 0, "artifact-path");
  assert(!isAbsolute(metadata.path) && !metadata.path.includes("\\"), "artifact-path");
  assert(!metadata.path.split("/").includes(".."), "artifact-path");
  const root = resolve(packageRoot);
  const artifactPath = resolve(root, ...metadata.path.split("/"));
  assert(artifactPath.startsWith(`${root}${sep}`), "artifact-path");
  const data = readFileSync(artifactPath);
  assert(Number.isInteger(metadata.length) && data.length === metadata.length, "artifact-length");
  assert(
    typeof metadata.sha256 === "string" && sha256(data).toString("hex") === metadata.sha256,
    "artifact-digest",
  );
  return data;
}


function expectReason(operation, reason) {
  try {
    operation();
  } catch (error) {
    assert(error instanceof Error && error.message === reason, `expected-${reason}-got-${error.message}`);
    return;
  }
  fail(`expected-${reason}`);
}


function verify(packageRoot) {
  const manifest = JSON.parse(readFileSync(resolve(packageRoot, "manifest.json"), "utf8"));
  assertKeys(manifest, ["invalid_cases", "profile", "schema", "valid_vectors", "version"], "manifest-schema");
  assert(manifest.schema === "nbsr-wp4-exporter-vectors" && manifest.version === 1, "manifest-version");
  assertKeys(
    manifest.profile,
    ["context_array_items", "context_profile", "exporter_label", "hash", "output_length"],
    "profile-schema",
  );
  assert(
    manifest.profile.context_array_items === 14 &&
      manifest.profile.context_profile === CONTEXT_PROFILE &&
      manifest.profile.exporter_label === LABEL.toString("ascii") &&
      manifest.profile.hash === "SHA-256" &&
      manifest.profile.output_length === 32,
    "profile-values",
  );
  assert(Array.isArray(manifest.valid_vectors) && manifest.valid_vectors.length >= 2, "valid-vector-count");
  assert(Array.isArray(manifest.invalid_cases), "invalid-case-list");

  const valid = new Map();
  for (const vector of manifest.valid_vectors) {
    assertKeys(vector, ["artifacts", "context", "id"], "valid-vector-schema");
    assert(typeof vector.id === "string" && !valid.has(vector.id), "valid-vector-id");
    assertKeys(vector.context, CONTEXT_FIELDS, "context-schema");
    assertKeys(vector.artifacts, ARTIFACT_FIELDS, "valid-artifact-schema");
    const contextCbor = loadArtifact(packageRoot, vector.artifacts.context_cbor);
    const contextHash = loadArtifact(packageRoot, vector.artifacts.context_hash);
    const derivedSecret = loadArtifact(packageRoot, vector.artifacts.derived_secret);
    const masterSecret = loadArtifact(packageRoot, vector.artifacts.exporter_master_secret);
    const exporterValue = loadArtifact(packageRoot, vector.artifacts.exporter_value);
    const decodedContext = parseContext(contextCbor);
    for (const field of CONTEXT_FIELDS) {
      assert(decodedContext[field] === vector.context[field], "context-manifest-mismatch");
    }
    const calculated = deriveServiceChannel(masterSecret, contextCbor);
    assert(calculated.contextHash.equals(contextHash), "context-hash-mismatch");
    assert(calculated.derivedSecret.equals(derivedSecret), "derived-secret-mismatch");
    assert(calculated.exporterValue.equals(exporterValue), "exporter-value-mismatch");
    valid.set(vector.id, { contextCbor, contextHash, masterSecret, exporterValue });
  }

  const categories = new Set();
  const caseIds = new Set();
  for (const testCase of manifest.invalid_cases) {
    assertKeys(
      testCase,
      ["artifact", "artifact_type", "basis_vector", "category", "expected_result", "id", "reason"],
      "invalid-case-schema",
    );
    assert(typeof testCase.id === "string" && !caseIds.has(testCase.id), "invalid-case-id");
    caseIds.add(testCase.id);
    categories.add(testCase.category);
    assert(testCase.expected_result === "reject" || testCase.expected_result === "different", "invalid-result");
    assert(typeof testCase.reason === "string" && testCase.reason.length > 0, "invalid-reason");
    const basis = valid.get(testCase.basis_vector);
    assert(basis !== undefined, "invalid-basis-vector");
    const artifact = loadArtifact(packageRoot, testCase.artifact);

    if (testCase.artifact_type === "context-cbor") {
      if (testCase.expected_result === "reject") {
        expectReason(() => deriveServiceChannel(basis.masterSecret, artifact), testCase.reason);
      } else {
        const mutated = deriveServiceChannel(basis.masterSecret, artifact);
        assert(testCase.reason === "context-hash-differs", "invalid-different-reason");
        assert(!mutated.contextHash.equals(basis.contextHash), testCase.reason);
        assert(!mutated.exporterValue.equals(basis.exporterValue), "exporter-value-differs");
      }
    } else if (testCase.artifact_type === "exporter-label-ascii") {
      assert(testCase.expected_result === "reject", "invalid-label-result");
      expectReason(
        () => deriveServiceChannel(basis.masterSecret, basis.contextCbor, artifact, 32),
        testCase.reason,
      );
    } else if (testCase.artifact_type === "output-length-u16be") {
      assert(artifact.length === 2 && testCase.expected_result === "reject", "invalid-output-length-artifact");
      expectReason(
        () => deriveServiceChannel(basis.masterSecret, basis.contextCbor, LABEL, artifact.readUInt16BE()),
        testCase.reason,
      );
    } else if (testCase.artifact_type === "exporter-master-secret") {
      assert(testCase.expected_result === "different" && testCase.reason === "exporter-value-differs", "invalid-secret-result");
      const mutated = deriveServiceChannel(artifact, basis.contextCbor);
      assert(!mutated.exporterValue.equals(basis.exporterValue), testCase.reason);
    } else {
      fail("invalid-artifact-type");
    }
  }

  for (let index = 0; index < 14; index += 1) assert(categories.has(`context-item-${index}`), "mutation-coverage");
  for (const required of [
    "array-reordering",
    "different-master-secret",
    "non-canonical-cbor",
    "wrong-cbor-type",
    "wrong-fixed-length",
    "wrong-label",
    "wrong-output-length",
  ]) {
    assert(categories.has(required), "mutation-coverage");
  }
  return { valid: manifest.valid_vectors.length, invalid: manifest.invalid_cases.length };
}


try {
  const packageRoot = process.argv[2];
  assert(packageRoot !== undefined, "usage: verify_wp4_exporter_vectors.mjs <package-directory>");
  const counts = verify(packageRoot);
  console.log(`verified ${counts.valid} valid vectors and ${counts.invalid} invalid/mutation cases`);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
