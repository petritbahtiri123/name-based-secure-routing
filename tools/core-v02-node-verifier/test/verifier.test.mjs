import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, unlink, writeFile } from "node:fs/promises";
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
