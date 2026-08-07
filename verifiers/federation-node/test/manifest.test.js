import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { verifyManifest } from "../src/manifest.js";

const packageDir = path.resolve(import.meta.dirname, "../../../vectors/federation-v0.1");

async function mutatedPackage(mutate) {
  const root = await mkdtemp(path.join(tmpdir(), "nbsr-fed-node-"));
  await cp(packageDir, root, { recursive: true });
  await mutate(root);
  return root;
}

test("verifies the checked-in closed package inventory and bytes", async () => {
  const result = await verifyManifest(packageDir);
  assert.deepEqual(result, { artifacts: 8, package: "federation-v0.1", packageVersion: "federation-v0.1-development-v1" });
});

test("rejects a digest mutation before semantic verification", async (t) => {
  const root = await mutatedPackage(async (dir) => {
    const file = path.join(dir, "manifest.json");
    const manifest = JSON.parse(await readFile(file, "utf8"));
    manifest.artifacts[0].sha256 = "00".repeat(32);
    await writeFile(file, JSON.stringify(manifest));
  });
  t.after(() => rm(root, { recursive: true, force: true }));
  await assert.rejects(verifyManifest(root), /manifest digest mismatch/);
});

test("rejects unlisted files and unsafe relative paths", async (t) => {
  const extra = await mutatedPackage((dir) => writeFile(path.join(dir, "extra.json"), "{}"));
  t.after(() => rm(extra, { recursive: true, force: true }));
  await assert.rejects(verifyManifest(extra), /unlisted package file/);

  const unsafe = await mutatedPackage(async (dir) => {
    const file = path.join(dir, "manifest.json");
    const manifest = JSON.parse(await readFile(file, "utf8"));
    manifest.artifacts[0].path = "../README.md";
    await writeFile(file, JSON.stringify(manifest));
  });
  t.after(() => rm(unsafe, { recursive: true, force: true }));
  await assert.rejects(verifyManifest(unsafe), /unsafe artifact path/);
});
