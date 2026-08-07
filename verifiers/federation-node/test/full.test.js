import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { verifyPackage } from "../src/verifier.js";

const packageDir = path.resolve(import.meta.dirname, "../../../vectors/federation-v0.1");

test("independently reproduces every Federation package result", async () => {
  const result = await verifyPackage(packageDir);
  assert.deepEqual(result, {
    manifestArtifacts: 8,
    staticVectors: 35,
    signedVectors: 12,
    thresholdVectors: 89,
    capabilityVectors: 12,
    precedenceCases: 11,
    stateScenarios: 43,
    mutationTests: 9,
  });
});
