import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  ManifestError,
  loadManifest,
  verifyPackageInventory,
} from "./lib/manifest.mjs";
import {
  createVerifierContext,
  evaluateVector,
} from "./lib/semantics.mjs";

const SCENARIO_CATALOG_SHA256 = "6de6ddf8415a6ea22672ab177146abefe029ee8726503b2a9eb9f2b8baa87177";

function verifyScenarioCatalog(manifest) {
  if (manifest.scenarios.length !== 8) {
    throw new ManifestError("scenario catalog count mismatch");
  }
  const digest = createHash("sha256")
    .update(JSON.stringify(manifest.scenarios), "utf8")
    .digest("hex");
  if (digest !== SCENARIO_CATALOG_SHA256) {
    throw new ManifestError("scenario catalog mismatch");
  }
}

export async function verifyVectorPackage(vectorRoot) {
  if (typeof vectorRoot !== "string" || vectorRoot.length === 0) {
    throw new ManifestError("exactly one vector-root path is required");
  }
  const manifest = await loadManifest(vectorRoot);
  const artifacts = await verifyPackageInventory(vectorRoot, manifest);
  const context = await createVerifierContext(vectorRoot, artifacts);

  for (const entry of manifest.vectors) {
    const actual = evaluateVector(entry, artifacts.get(entry.id), context);
    if (
      actual.outcome !== entry.expected_outcome
      || actual.error !== entry.expected_error
    ) {
      throw new ManifestError(`vector outcome mismatch: ${entry.id}`);
    }
  }
  verifyScenarioCatalog(manifest);
  return {
    valid: manifest.vectors.filter((entry) => entry.class === "valid").length,
    invalid: manifest.vectors.filter((entry) => entry.class === "invalid").length,
    scenarios: manifest.scenarios.length,
  };
}

function boundedMessage(error) {
  const raw = error instanceof Error ? error.message : "unknown verifier failure";
  const normalized = raw.replace(/[\r\n\t]+/gu, " ").replace(/\s{2,}/gu, " ").trim();
  return (normalized || "unknown verifier failure").slice(0, 200);
}

export async function main(args) {
  if (!Array.isArray(args) || args.length !== 1) {
    throw new ManifestError("exactly one vector-root path is required");
  }
  const counts = await verifyVectorPackage(args[0]);
  process.stdout.write(
    `NBSR Core v0.2 vectors verified: ${counts.valid} valid, `
    + `${counts.invalid} invalid, ${counts.scenarios} scenarios.\n`,
  );
}

const isDirectExecution = process.argv[1]
  && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (isDirectExecution) {
  main(process.argv.slice(2)).catch((error) => {
    process.stderr.write(`Core v0.2 verification failed: ${boundedMessage(error)}\n`);
    process.exitCode = 1;
  });
}
