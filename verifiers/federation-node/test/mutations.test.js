import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { runMutationChecks } from "../src/mutations.js";
import { loadAuthorities } from "../src/registry.js";

test("rejects nine independently-created adversarial mutations", async () => {
  const dir=path.resolve(import.meta.dirname,"../../../vectors/federation-v0.1");
  const load=async(name)=>JSON.parse(await readFile(path.join(dir,name),"utf8"));
  assert.equal(await runMutationChecks({signed:await load("signed-vectors.json"),capability:await load("capability-vectors.json"),threshold:await load("threshold-vectors.json"),state:await load("stateful-scenarios.json")},await loadAuthorities(dir)),9);
});
