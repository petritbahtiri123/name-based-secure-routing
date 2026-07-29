import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  cp,
  mkdtemp,
  readFile,
  readdir,
  rm,
  unlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  ManifestError,
  loadManifest,
  parseJsonStrict,
  validateManifest,
  verifyPackageInventory,
} from "../lib/manifest.mjs";
import {
  CborError,
  CborTag,
  decodeDeterministic,
  encodeDeterministic,
} from "../lib/cbor.mjs";
import {
  CryptoVerificationError,
  importRawEd25519PublicKey,
  loadPublicKeyHex,
  verifyCoseSign1,
  verifyProof,
} from "../lib/crypto.mjs";
import {
  ERROR,
  createVerifierContext,
  evaluateVector,
} from "../lib/semantics.mjs";
import { verifyVectorPackage } from "../verify.mjs";

const REPO_ROOT = path.resolve(import.meta.dirname, "../../..");
const VECTOR_ROOT = path.join(REPO_ROOT, "vectors", "core-v0.2");

async function withPackageCopy(run) {
  const parent = await mkdtemp(path.join(REPO_ROOT, ".node-verifier-test-"));
  const root = path.join(parent, "core-v0.2");
  await cp(VECTOR_ROOT, root, { recursive: true });
  try {
    return await run(root);
  } finally {
    await rm(parent, { recursive: true, force: true });
  }
}

async function mutateManifest(root, mutate) {
  const manifestPath = path.join(root, "manifest.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  mutate(manifest);
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}

async function packageSnapshot(root) {
  const result = new Map();
  async function visit(directory) {
    const entries = await readdir(directory, {withFileTypes: true});
    for (const entry of entries) {
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(absolute);
      } else if (entry.isFile()) {
        result.set(
          path.relative(root, absolute).split(path.sep).join("/"),
          createHash("sha256").update(await readFile(absolute)).digest("hex"),
        );
      }
    }
  }
  await visit(root);
  return result;
}

test("strict JSON rejects duplicate object keys", () => {
  assert.throws(
    () => parseJsonStrict('{"protocol":"NBSR","protocol":"other"}'),
    ManifestError,
  );
});

test("strict JSON accepts escaped keys in separate objects", () => {
  assert.deepEqual(parseJsonStrict('{"a\\"b":1,"nested":{"a\\"b":2}}'), {
    'a"b': 1,
    nested: {'a"b': 2},
  });
});

test("checked-in package has 14 valid and 18 invalid vectors", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  assert.equal(manifest.vectors.filter((vector) => vector.class === "valid").length, 14);
  assert.equal(manifest.vectors.filter((vector) => vector.class === "invalid").length, 18);
  const artifacts = await verifyPackageInventory(VECTOR_ROOT, manifest);
  assert.equal(artifacts.size, 32);
});

test("manifest rejects missing and unknown top-level keys", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  const missing = structuredClone(manifest);
  delete missing.protocol;
  assert.throws(() => validateManifest(missing), ManifestError);
  assert.throws(() => validateManifest({...manifest, unexpected: true}), ManifestError);
});

test("manifest rejects duplicate and unsorted IDs", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  const duplicate = structuredClone(manifest);
  duplicate.vectors[1].id = duplicate.vectors[0].id;
  assert.throws(() => validateManifest(duplicate), ManifestError);

  const unsorted = structuredClone(manifest);
  [unsorted.vectors[0], unsorted.vectors[1]] = [unsorted.vectors[1], unsorted.vectors[0]];
  assert.throws(() => validateManifest(unsorted), ManifestError);
});

test("manifest rejects unknown closed enum values", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  for (const [field, value] of [
    ["class", "maybe"],
    ["artifact_type", "packet-capture"],
    ["expected_outcome", "maybe"],
    ["validation_stage", "transport"],
    ["message_type", "NOT_A_MESSAGE"],
  ]) {
    const changed = structuredClone(manifest);
    changed.vectors[0][field] = value;
    assert.throws(() => validateManifest(changed), ManifestError, field);
  }
});

test("manifest rejects unsafe artifact paths", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  for (const artifactPath of [
    "../escape.cbor",
    "artifacts\\valid\\escape.cbor",
    "C:/escape.cbor",
    "file:///escape.cbor",
    "/absolute.cbor",
    "artifacts/./escape.cbor",
  ]) {
    const changed = structuredClone(manifest);
    changed.vectors[0].artifact_path = artifactPath;
    assert.throws(() => validateManifest(changed), ManifestError, artifactPath);
  }
});

test("package rejects a missing artifact", async () => {
  await withPackageCopy(async (root) => {
    const manifest = await loadManifest(root);
    await unlink(path.join(root, manifest.vectors[0].artifact_path));
    await assert.rejects(() => verifyPackageInventory(root, manifest), ManifestError);
  });
});

test("package rejects an unlisted artifact", async () => {
  await withPackageCopy(async (root) => {
    const manifest = await loadManifest(root);
    await writeFile(path.join(root, "artifacts", "extra.bin"), Buffer.from([0]));
    await assert.rejects(() => verifyPackageInventory(root, manifest), ManifestError);
  });
});

test("package rejects wrong length and SHA-256", async () => {
  for (const field of ["length", "sha256"]) {
    await withPackageCopy(async (root) => {
      await mutateManifest(root, (manifest) => {
        if (field === "length") {
          manifest.vectors[0].length += 1;
        } else {
          manifest.vectors[0].sha256 = "0".repeat(64);
        }
      });
      const manifest = await loadManifest(root);
      await assert.rejects(() => verifyPackageInventory(root, manifest), ManifestError);
    });
  }
});

test("package root must be a real core-v0.2 directory", async () => {
  await assert.rejects(
    () => loadManifest(path.join(os.tmpdir(), "not-a-vector-package")),
    ManifestError,
  );
});

test("RFC 8949 map ordering is bytewise, not length-first", () => {
  const decoded = decodeDeterministic(Buffer.from("a21818002001", "hex"));
  assert.deepEqual([...decoded.keys()], [24, -1]);
  assert.equal(encodeDeterministic(decoded).toString("hex"), "a21818002001");
});

test("all valid CBOR artifacts decode and re-encode identically", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  const artifacts = await verifyPackageInventory(VECTOR_ROOT, manifest);
  for (const entry of manifest.vectors.filter(
    (vector) => vector.class === "valid" && vector.artifact_type !== "ed25519-signature",
  )) {
    const options = { allowTag18: entry.artifact_type === "cose-sign1" };
    const decoded = decodeDeterministic(artifacts.get(entry.id), options);
    assert.deepEqual(encodeDeterministic(decoded, options), artifacts.get(entry.id), entry.id);
  }
});

test("all structural invalid vectors fail with the exact CBOR error kind", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  const artifacts = await verifyPackageInventory(VECTOR_ROOT, manifest);
  const entries = manifest.vectors.filter((vector) => vector.validation_stage === "structural");
  assert.deepEqual(
    entries.map((entry) => entry.id),
    [
      "cbor-duplicate-map-key",
      "cbor-float",
      "cbor-indefinite-map",
      "cbor-nonpreferred-integer",
      "cbor-over-total-bytes",
      "cbor-trailing-bytes",
      "cbor-truncated",
      "cbor-unsupported-tag",
      "cbor-wrong-map-order",
    ],
  );
  for (const entry of entries) {
    assert.throws(
      () => decodeDeterministic(artifacts.get(entry.id)),
      (error) => error instanceof CborError
        && error.kind === (entry.id === "cbor-over-total-bytes" ? "capacity" : "profile"),
      entry.id,
    );
  }
});

test("CBOR rejects unsupported values and invalid UTF-8", () => {
  for (const hex of ["f7", "f8ff", "f93c00", "c100", "61ff"]) {
    assert.throws(
      () => decodeDeterministic(Buffer.from(hex, "hex")),
      (error) => error instanceof CborError && error.kind === "profile",
      hex,
    );
  }
});

test("CBOR enforces each configured resource limit", () => {
  const cases = [
    [Buffer.from("8100", "hex"), {maxArrayItems: 0}],
    [Buffer.from("a10000", "hex"), {maxMapPairs: 0}],
    [Buffer.from("6161", "hex"), {maxTextBytes: 0}],
    [Buffer.from("4100", "hex"), {maxByteStringBytes: 0}],
    [Buffer.from("8100", "hex"), {maxDepth: 1}],
    [Buffer.from("1818", "hex"), {maxTotalBytes: 1}],
  ];
  for (const [wire, limits] of cases) {
    assert.throws(
      () => decodeDeterministic(wire, {limits}),
      (error) => error instanceof CborError && error.kind === "capacity",
    );
  }
});

test("CBOR supports tag 18 only when explicitly enabled", () => {
  const tagged = Buffer.from("d28100", "hex");
  assert.throws(() => decodeDeterministic(tagged), CborError);
  const decoded = decodeDeterministic(tagged, {allowTag18: true});
  assert.ok(decoded instanceof CborTag);
  assert.equal(decoded.tag, 18);
  assert.deepEqual(decoded.value, [0]);
  assert.deepEqual(encodeDeterministic(decoded, {allowTag18: true}), tagged);
});

test("CBOR encoder rejects cycles and duplicate deterministic map keys", () => {
  const cyclic = [];
  cyclic.push(cyclic);
  assert.throws(() => encodeDeterministic(cyclic), CborError);

  const duplicate = new Map();
  duplicate.set(1, "first");
  duplicate.set(1n, "second");
  assert.throws(() => encodeDeterministic(duplicate), CborError);
});

function routeOpenBody(wire) {
  const envelope = decodeDeterministic(wire);
  assert.ok(envelope instanceof Map);
  const body = envelope.get(5);
  assert.ok(body instanceof Map);
  return body;
}

test("public Ed25519 key files have the exact test-only format", async () => {
  for (const name of [
    "test-only-route-grant-ed25519-public.hex",
    "test-only-session-ed25519-public.hex",
  ]) {
    const publicKey = await loadPublicKeyHex(path.join(VECTOR_ROOT, "keys", name));
    assert.equal(publicKey.length, 32);
    assert.doesNotThrow(() => importRawEd25519PublicKey(publicKey));
  }
  for (const length of [0, 31, 33]) {
    assert.throws(
      () => importRawEd25519PublicKey(Buffer.alloc(length)),
      CryptoVerificationError,
    );
  }
});

test("valid RouteGrant COSE Sign1 verifies independently", async () => {
  const publicKey = await loadPublicKeyHex(
    path.join(VECTOR_ROOT, "keys", "test-only-route-grant-ed25519-public.hex"),
  );
  const manifest = await loadManifest(VECTOR_ROOT);
  const artifacts = await verifyPackageInventory(VECTOR_ROOT, manifest);
  const result = verifyCoseSign1(artifacts.get("route-grant-sign1"), publicKey);
  assert.deepEqual(result.payload, artifacts.get("route-grant-payload"));
  assert.ok(result.kid.length >= 1 && result.kid.length <= 64);
});

test("valid Route Open proof verifies independently", async () => {
  const publicKey = await loadPublicKeyHex(
    path.join(VECTOR_ROOT, "keys", "test-only-session-ed25519-public.hex"),
  );
  const artifacts = await verifyPackageInventory(
    VECTOR_ROOT,
    await loadManifest(VECTOR_ROOT),
  );
  assert.doesNotThrow(() => verifyProof(
    artifacts.get("route-open-proof-transcript"),
    artifacts.get("route-open-proof-signature"),
    publicKey,
  ));
});

test("all three invalid COSE vectors fail independently", async () => {
  const publicKey = await loadPublicKeyHex(
    path.join(VECTOR_ROOT, "keys", "test-only-route-grant-ed25519-public.hex"),
  );
  const artifacts = await verifyPackageInventory(
    VECTOR_ROOT,
    await loadManifest(VECTOR_ROOT),
  );
  for (const id of ["cose-bad-signature", "cose-missing-tag", "cose-wrong-algorithm"]) {
    const grant = routeOpenBody(artifacts.get(id)).get(2);
    assert.throws(() => verifyCoseSign1(grant, publicKey), CryptoVerificationError, id);
  }
});

test("invalid Route Open proof vector fails independently", async () => {
  const publicKey = await loadPublicKeyHex(
    path.join(VECTOR_ROOT, "keys", "test-only-session-ed25519-public.hex"),
  );
  const artifacts = await verifyPackageInventory(
    VECTOR_ROOT,
    await loadManifest(VECTOR_ROOT),
  );
  const badSignature = routeOpenBody(artifacts.get("proof-bad-signature")).get(7);
  assert.throws(
    () => verifyProof(
      artifacts.get("route-open-proof-transcript"),
      badSignature,
      publicKey,
    ),
    CryptoVerificationError,
  );
});

test("COSE rejects malformed profile fields before signature verification", async () => {
  const publicKey = await loadPublicKeyHex(
    path.join(VECTOR_ROOT, "keys", "test-only-route-grant-ed25519-public.hex"),
  );
  const artifacts = await verifyPackageInventory(
    VECTOR_ROOT,
    await loadManifest(VECTOR_ROOT),
  );
  const tagged = decodeDeterministic(artifacts.get("route-grant-sign1"), {allowTag18: true});
  const [protectedBytes, unprotected, payload, signature] = tagged.value;
  const protectedHeaders = decodeDeterministic(protectedBytes);

  const mutations = [
    new CborTag(18, [encodeDeterministic(new Map([[1, -8]])), unprotected, payload, signature]),
    new CborTag(18, [encodeDeterministic(new Map([[1, -8], [4, "text-kid"]])), unprotected, payload, signature]),
    new CborTag(18, [encodeDeterministic(new Map([[1, -8], [4, Buffer.alloc(0)]])), unprotected, payload, signature]),
    new CborTag(18, [protectedBytes, new Map([[1, 1]]), payload, signature]),
    new CborTag(18, [protectedBytes, unprotected, null, signature]),
    new CborTag(18, [protectedBytes, unprotected, payload, Buffer.alloc(63)]),
  ];
  for (const mutation of mutations) {
    const wire = encodeDeterministic(mutation, {allowTag18: true});
    assert.throws(() => verifyCoseSign1(wire, publicKey), CryptoVerificationError);
  }

  const kid65 = new Map(protectedHeaders);
  kid65.set(4, Buffer.alloc(65));
  assert.throws(
    () => verifyCoseSign1(
      encodeDeterministic(
        new CborTag(18, [encodeDeterministic(kid65), unprotected, payload, signature]),
        {allowTag18: true},
      ),
      publicKey,
    ),
    CryptoVerificationError,
  );
});

test("proof verification rejects a one-bit transcript mutation", async () => {
  const publicKey = await loadPublicKeyHex(
    path.join(VECTOR_ROOT, "keys", "test-only-session-ed25519-public.hex"),
  );
  const artifacts = await verifyPackageInventory(
    VECTOR_ROOT,
    await loadManifest(VECTOR_ROOT),
  );
  const transcript = Buffer.from(artifacts.get("route-open-proof-transcript"));
  transcript[transcript.length - 1] ^= 1;
  assert.throws(
    () => verifyProof(
      transcript,
      artifacts.get("route-open-proof-signature"),
      publicKey,
    ),
    CryptoVerificationError,
  );
});

const VALID_IDS = [
  "client-hello",
  "client-hello-body",
  "edge-hello",
  "edge-hello-body",
  "route-accept",
  "route-grant-payload",
  "route-grant-sign1",
  "route-open",
  "route-open-proof-signature",
  "route-open-proof-transcript",
  "route-reject",
  "stream-accept",
  "stream-open",
  "stream-reject",
];

const INVALID_IDS = [
  "boolean-protocol-version",
  "cbor-duplicate-map-key",
  "cbor-float",
  "cbor-indefinite-map",
  "cbor-nonpreferred-integer",
  "cbor-over-total-bytes",
  "cbor-trailing-bytes",
  "cbor-truncated",
  "cbor-unsupported-tag",
  "cbor-wrong-map-order",
  "cose-bad-signature",
  "cose-missing-tag",
  "cose-wrong-algorithm",
  "grant-expired",
  "proof-bad-signature",
  "route-port-not-authorized",
  "version-one-on-v2",
  "version-three-generic-close",
];

test("all 32 artifact outcomes match the manifest exactly", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  const artifacts = await verifyPackageInventory(VECTOR_ROOT, manifest);
  const context = await createVerifierContext(VECTOR_ROOT, artifacts);
  assert.equal(manifest.vectors.length, 32);
  assert.deepEqual(
    manifest.vectors.filter((entry) => entry.class === "valid").map((entry) => entry.id),
    VALID_IDS,
  );
  assert.deepEqual(
    manifest.vectors.filter((entry) => entry.class === "invalid").map((entry) => entry.id),
    INVALID_IDS,
  );
  for (const entry of manifest.vectors) {
    const actual = evaluateVector(entry, artifacts.get(entry.id), context);
    assert.deepEqual(actual, {
      outcome: entry.expected_outcome,
      error: entry.expected_error,
    }, entry.id);
  }
});

test("portable semantics reject unknown and missing body keys", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  const artifacts = await verifyPackageInventory(VECTOR_ROOT, manifest);
  const context = await createVerifierContext(VECTOR_ROOT, artifacts);
  const entry = manifest.vectors.find((vector) => vector.id === "client-hello");
  const valid = decodeDeterministic(artifacts.get("client-hello"));

  for (const mutate of [
    (body) => body.delete(7),
    (body) => body.set(99, 1),
  ]) {
    const changed = new Map(valid);
    const body = new Map(changed.get(5));
    mutate(body);
    changed.set(5, body);
    assert.deepEqual(
      evaluateVector(entry, encodeDeterministic(changed), context),
      {outcome: "reject", error: ERROR.PROFILE},
    );
  }
});

test("portable semantics distinguish downgrade from unknown-version close", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  const artifacts = await verifyPackageInventory(VECTOR_ROOT, manifest);
  const context = await createVerifierContext(VECTOR_ROOT, artifacts);
  const entry = manifest.vectors.find((vector) => vector.id === "client-hello");
  const valid = decodeDeterministic(artifacts.get("client-hello"));

  const versionOne = new Map(valid);
  versionOne.set(0, 1);
  assert.deepEqual(
    evaluateVector(entry, encodeDeterministic(versionOne), context),
    {outcome: "reject", error: ERROR.DOWNGRADE},
  );

  const versionThree = new Map(valid);
  versionThree.set(0, 3);
  assert.deepEqual(
    evaluateVector(entry, encodeDeterministic(versionThree), context),
    {outcome: "close", error: null},
  );
});

test("portable semantics reject boolean protocol versions as profile errors", async () => {
  const manifest = await loadManifest(VECTOR_ROOT);
  const artifacts = await verifyPackageInventory(VECTOR_ROOT, manifest);
  const context = await createVerifierContext(VECTOR_ROOT, artifacts);
  const entry = manifest.vectors.find((vector) => vector.id === "client-hello");
  const changed = decodeDeterministic(artifacts.get("client-hello"));
  changed.set(0, true);
  assert.deepEqual(
    evaluateVector(entry, encodeDeterministic(changed), context),
    {outcome: "reject", error: ERROR.PROFILE},
  );
});

test("complete checked-in package verifies read-only", async () => {
  const before = await packageSnapshot(VECTOR_ROOT);
  assert.deepEqual(await verifyVectorPackage(VECTOR_ROOT), {
    valid: 14,
    invalid: 18,
    scenarios: 8,
  });
  assert.deepEqual(await packageSnapshot(VECTOR_ROOT), before);
});

test("scenario catalog requires exact referenced vector outcomes", async () => {
  await withPackageCopy(async (root) => {
    await mutateManifest(root, (manifest) => {
      manifest.scenarios[0].steps[0].expected_outcome = "close";
      manifest.scenarios[0].steps[0].expected_error = null;
    });
    await assert.rejects(() => verifyVectorPackage(root), ManifestError);
  });
});

test("package verification fails read-only after one artifact byte changes", async () => {
  await withPackageCopy(async (root) => {
    const manifest = await loadManifest(root);
    const artifactPath = path.join(root, manifest.vectors[0].artifact_path);
    const changed = Buffer.from(await readFile(artifactPath));
    changed[0] ^= 1;
    await writeFile(artifactPath, changed);
    const before = await packageSnapshot(root);
    await assert.rejects(() => verifyVectorPackage(root), ManifestError);
    assert.deepEqual(await packageSnapshot(root), before);
  });
});

test("CLI prints one bounded success line", () => {
  const cli = path.join(REPO_ROOT, "tools", "core-v02-node-verifier", "verify.mjs");
  const result = spawnSync(process.execPath, [cli, VECTOR_ROOT], {
    encoding: "utf8",
    windowsHide: true,
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(
    result.stdout,
    "NBSR Core v0.2 vectors verified: 14 valid, 18 invalid, 8 scenarios.\n",
  );
  assert.equal(result.stderr, "");
});

test("CLI rejects missing and extra arguments", () => {
  const cli = path.join(REPO_ROOT, "tools", "core-v02-node-verifier", "verify.mjs");
  for (const args of [[], [VECTOR_ROOT, VECTOR_ROOT]]) {
    const result = spawnSync(process.execPath, [cli, ...args], {
      encoding: "utf8",
      windowsHide: true,
    });
    assert.equal(result.status, 1);
    assert.equal(result.stdout, "");
    assert.match(result.stderr, /^Core v0\.2 verification failed: .{1,200}\n$/u);
  }
});
