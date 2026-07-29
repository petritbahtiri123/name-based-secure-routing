import { createHash } from "node:crypto";
import { lstat, readFile, readdir } from "node:fs/promises";
import path from "node:path";

export class ManifestError extends Error {
  constructor(message) {
    super(message);
    this.name = "ManifestError";
  }
}

const TOP_LEVEL_KEYS = new Set([
  "alpn",
  "format_version",
  "hash",
  "protocol",
  "protocol_version",
  "scenarios",
  "vectors",
]);
const VECTOR_KEYS = new Set([
  "artifact_path",
  "artifact_type",
  "class",
  "expected_error",
  "expected_outcome",
  "id",
  "length",
  "message_type",
  "scenario_only",
  "sha256",
  "validation_stage",
]);
const SCENARIO_KEYS = new Set(["final_assertions", "id", "initial_core_version", "steps"]);
const STEP_KEYS = new Set(["expected_error", "expected_outcome", "sequence", "vector_id"]);
const CLASSES = new Set(["valid", "invalid"]);
const OUTCOMES = new Set(["accept", "reject", "close"]);
const ARTIFACT_TYPES = new Set([
  "core-object-cbor",
  "cose-sign1",
  "control-envelope-cbor",
  "proof-transcript-cbor",
  "ed25519-signature",
  "malformed-bytes",
]);
const STAGES = new Set([
  "structural",
  "deterministic-cbor",
  "object-schema",
  "cose",
  "envelope-schema",
  "message-schema",
  "version-dispatch",
  "proof",
  "binding",
  "replay",
  "policy",
]);
const MESSAGE_TYPES = new Set([
  "CLIENT_HELLO",
  "EDGE_HELLO",
  "ROUTE_OPEN",
  "ROUTE_ACCEPT",
  "ROUTE_REJECT",
  "STREAM_OPEN",
  "STREAM_ACCEPT",
  "STREAM_REJECT",
  "LEASE_RENEW",
  "LEASE_RESULT",
  "KEY_UPDATE_NOTICE",
  "ROUTE_DRAIN",
  "ROUTE_REVOKE",
  "ROUTE_CLOSE",
  "PING",
  "PONG",
  "ERROR",
]);
const ERROR_NAMES = new Set([
  "NBSR_E_NAME_INVALID",
  "NBSR_E_NAME_NOT_FOUND",
  "NBSR_E_RECORD_UNTRUSTED",
  "NBSR_E_RECORD_STALE",
  "NBSR_E_RECORD_REVOKED",
  "NBSR_E_CONTEXT_REQUIRED",
  "NBSR_E_HANDLE_EXHAUSTED",
  "NBSR_E_ROUTE_DENIED",
  "NBSR_E_GRANT_INVALID",
  "NBSR_E_GRANT_EXPIRED",
  "NBSR_E_PROOF_INVALID",
  "NBSR_E_REPLAY",
  "NBSR_E_PROFILE_UNSUPPORTED",
  "NBSR_E_DOWNGRADE",
  "NBSR_E_EDGE_UNAVAILABLE",
  "NBSR_E_ORIGIN_UNAVAILABLE",
  "NBSR_E_REVOKED",
  "NBSR_E_OVER_CAPACITY",
  "NBSR_E_INTERNAL",
]);
const FINAL_ASSERTIONS = new Set([
  "transport-session-active",
  "transport-session-closed",
  "route-context-active",
  "no-route-state",
  "stream-active",
  "no-stream-state",
  "replay-state-unchanged",
  "replay-tombstone-retained",
  "no-version-fallback",
  "no-origin-disclosure",
]);
const SUPPORT_FILES = new Set([
  "README.md",
  "manifest.json",
  "keys/test-only-route-grant-ed25519-seed.hex",
  "keys/test-only-route-grant-ed25519-public.hex",
  "keys/test-only-session-ed25519-seed.hex",
  "keys/test-only-session-ed25519-public.hex",
]);
const ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

function fail(message) {
  throw new ManifestError(message);
}

function scanJson(text) {
  let offset = 0;

  function whitespace() {
    while (offset < text.length && /\s/u.test(text[offset])) {
      offset += 1;
    }
  }

  function string() {
    const start = offset;
    if (text[offset] !== '"') {
      fail("invalid manifest JSON");
    }
    offset += 1;
    while (offset < text.length) {
      const character = text[offset];
      if (character === '"') {
        offset += 1;
        try {
          return JSON.parse(text.slice(start, offset));
        } catch {
          fail("invalid manifest JSON");
        }
      }
      if (character === "\\") {
        offset += 1;
        if (offset >= text.length) {
          fail("invalid manifest JSON");
        }
        if (text[offset] === "u") {
          if (!/^[0-9a-fA-F]{4}$/u.test(text.slice(offset + 1, offset + 5))) {
            fail("invalid manifest JSON");
          }
          offset += 5;
          continue;
        }
        if (!'"\\/bfnrt'.includes(text[offset])) {
          fail("invalid manifest JSON");
        }
      } else if (character.charCodeAt(0) < 0x20) {
        fail("invalid manifest JSON");
      }
      offset += 1;
    }
    fail("invalid manifest JSON");
  }

  function value() {
    whitespace();
    const character = text[offset];
    if (character === "{") {
      object();
      return;
    }
    if (character === "[") {
      array();
      return;
    }
    if (character === '"') {
      string();
      return;
    }
    const remainder = text.slice(offset);
    const token = remainder.match(/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/u);
    if (!token) {
      fail("invalid manifest JSON");
    }
    offset += token[0].length;
  }

  function object() {
    offset += 1;
    whitespace();
    const keys = new Set();
    if (text[offset] === "}") {
      offset += 1;
      return;
    }
    while (offset < text.length) {
      whitespace();
      const key = string();
      if (keys.has(key)) {
        fail(`duplicate JSON key: ${key}`);
      }
      keys.add(key);
      whitespace();
      if (text[offset] !== ":") {
        fail("invalid manifest JSON");
      }
      offset += 1;
      value();
      whitespace();
      if (text[offset] === "}") {
        offset += 1;
        return;
      }
      if (text[offset] !== ",") {
        fail("invalid manifest JSON");
      }
      offset += 1;
    }
    fail("invalid manifest JSON");
  }

  function array() {
    offset += 1;
    whitespace();
    if (text[offset] === "]") {
      offset += 1;
      return;
    }
    while (offset < text.length) {
      value();
      whitespace();
      if (text[offset] === "]") {
        offset += 1;
        return;
      }
      if (text[offset] !== ",") {
        fail("invalid manifest JSON");
      }
      offset += 1;
    }
    fail("invalid manifest JSON");
  }

  value();
  whitespace();
  if (offset !== text.length) {
    fail("invalid manifest JSON");
  }
}

export function parseJsonStrict(text) {
  if (typeof text !== "string" || text.startsWith("\uFEFF")) {
    fail("invalid manifest JSON");
  }
  scanJson(text);
  try {
    return JSON.parse(text);
  } catch {
    fail("invalid manifest JSON");
  }
}

function requireExactKeys(value, expected, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(`${label} must be an object`);
  }
  const actual = Object.keys(value);
  if (actual.length !== expected.size || actual.some((key) => !expected.has(key))) {
    fail(`${label} has unknown or missing keys`);
  }
}

function requireInteger(value, label, minimum = 0) {
  if (!Number.isSafeInteger(value) || value < minimum) {
    fail(`invalid ${label}`);
  }
}

function requireId(value, label) {
  if (typeof value !== "string" || !ID_PATTERN.test(value)) {
    fail(`invalid ${label}`);
  }
}

function validateOutcome(outcome, error) {
  if (!OUTCOMES.has(outcome)) {
    fail("invalid expected_outcome");
  }
  if (outcome === "reject") {
    if (!ERROR_NAMES.has(error)) {
      fail("reject must name a frozen error");
    }
  } else if (error !== null) {
    fail(`${outcome} expected_error must be null`);
  }
}

function validateArtifactPath(artifactPath) {
  if (
    typeof artifactPath !== "string"
    || artifactPath.includes("\\")
    || artifactPath.includes("://")
    || /^[A-Za-z]:/u.test(artifactPath)
    || artifactPath.startsWith("/")
  ) {
    fail("invalid artifact path");
  }
  const parts = artifactPath.split("/");
  if (parts[0] !== "artifacts" || parts.some((part) => !part || part === "." || part === "..")) {
    fail("invalid artifact path");
  }
}

function validateVector(vector) {
  requireExactKeys(vector, VECTOR_KEYS, "vector");
  requireId(vector.id, "vector id");
  if (!CLASSES.has(vector.class)) {
    fail("invalid class");
  }
  if (!ARTIFACT_TYPES.has(vector.artifact_type)) {
    fail("invalid artifact_type");
  }
  validateArtifactPath(vector.artifact_path);
  requireInteger(vector.length, "length");
  if (typeof vector.sha256 !== "string" || !SHA256_PATTERN.test(vector.sha256)) {
    fail("invalid sha256");
  }
  validateOutcome(vector.expected_outcome, vector.expected_error);
  if (!STAGES.has(vector.validation_stage)) {
    fail("invalid validation_stage");
  }
  if (vector.expected_outcome === "close" && !["structural", "version-dispatch"].includes(vector.validation_stage)) {
    fail("close requires structural or version-dispatch stage");
  }
  if (vector.message_type !== null && !MESSAGE_TYPES.has(vector.message_type)) {
    fail("invalid message_type");
  }
  if (typeof vector.scenario_only !== "boolean") {
    fail("invalid scenario_only");
  }
}

function validateScenario(scenario, vectorIds) {
  requireExactKeys(scenario, SCENARIO_KEYS, "scenario");
  requireId(scenario.id, "scenario id");
  requireInteger(scenario.initial_core_version, "initial_core_version", 1);
  if (!Array.isArray(scenario.steps) || scenario.steps.length === 0) {
    fail("scenario steps must be nonempty");
  }
  for (const [index, step] of scenario.steps.entries()) {
    requireExactKeys(step, STEP_KEYS, "scenario step");
    requireInteger(step.sequence, "scenario sequence", 1);
    if (step.sequence !== index + 1) {
      fail("scenario sequence must be contiguous");
    }
    requireId(step.vector_id, "scenario vector id");
    if (!vectorIds.has(step.vector_id)) {
      fail("unknown scenario vector id");
    }
    validateOutcome(step.expected_outcome, step.expected_error);
  }
  if (
    !Array.isArray(scenario.final_assertions)
    || new Set(scenario.final_assertions).size !== scenario.final_assertions.length
    || scenario.final_assertions.some((assertion) => !FINAL_ASSERTIONS.has(assertion))
  ) {
    fail("invalid final_assertions");
  }
}

export function validateManifest(manifest) {
  requireExactKeys(manifest, TOP_LEVEL_KEYS, "manifest");
  if (manifest.format_version !== 1 || !Number.isInteger(manifest.format_version)) {
    fail("invalid format_version");
  }
  if (manifest.protocol !== "NBSR") {
    fail("invalid protocol");
  }
  if (manifest.protocol_version !== 2 || !Number.isInteger(manifest.protocol_version)) {
    fail("invalid protocol_version");
  }
  if (manifest.alpn !== "nbsr-quic-1" || manifest.hash !== "sha256") {
    fail("invalid protocol profile");
  }
  if (!Array.isArray(manifest.vectors) || !Array.isArray(manifest.scenarios)) {
    fail("vectors and scenarios must be arrays");
  }

  for (const vector of manifest.vectors) {
    validateVector(vector);
  }
  const vectorIds = manifest.vectors.map((vector) => vector.id);
  const artifactPaths = manifest.vectors.map((vector) => vector.artifact_path);
  if (new Set(vectorIds).size !== vectorIds.length || new Set(artifactPaths).size !== artifactPaths.length) {
    fail("duplicate vector id or artifact path");
  }
  if (vectorIds.some((id, index) => index > 0 && id <= vectorIds[index - 1])) {
    fail("vectors must be sorted by id");
  }

  const knownVectorIds = new Set(vectorIds);
  for (const scenario of manifest.scenarios) {
    validateScenario(scenario, knownVectorIds);
  }
  const scenarioIds = manifest.scenarios.map((scenario) => scenario.id);
  if (
    new Set(scenarioIds).size !== scenarioIds.length
    || scenarioIds.some((id, index) => index > 0 && id <= scenarioIds[index - 1])
  ) {
    fail("scenarios must have unique sorted ids");
  }
  return manifest;
}

export async function loadManifest(vectorRoot) {
  try {
    const manifestPath = path.join(path.resolve(vectorRoot), "manifest.json");
    const text = await readFile(manifestPath, "utf8");
    return validateManifest(parseJsonStrict(text));
  } catch (error) {
    if (error instanceof ManifestError) {
      throw error;
    }
    throw new ManifestError("invalid manifest JSON");
  }
}

async function listRegularFiles(root, current = root) {
  const relativeFiles = [];
  let entries;
  try {
    entries = await readdir(current, { withFileTypes: true });
  } catch {
    fail("invalid vector package");
  }
  for (const entry of entries) {
    const absolute = path.join(current, entry.name);
    const relative = path.relative(root, absolute).split(path.sep).join("/");
    if (entry.isSymbolicLink()) {
      fail(`symbolic link prohibited: ${relative}`);
    }
    if (entry.isDirectory()) {
      relativeFiles.push(...await listRegularFiles(root, absolute));
    } else if (entry.isFile()) {
      relativeFiles.push(relative);
    } else {
      fail(`unsupported package entry: ${relative}`);
    }
  }
  return relativeFiles;
}

export async function verifyPackageInventory(vectorRoot, manifest) {
  validateManifest(manifest);
  const root = path.resolve(vectorRoot);
  let rootStat;
  try {
    rootStat = await lstat(root);
  } catch {
    fail("invalid vector package");
  }
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    fail("invalid vector package");
  }

  const expectedArtifacts = new Set(manifest.vectors.map((vector) => vector.artifact_path));
  const expectedFiles = new Set([...SUPPORT_FILES, ...expectedArtifacts]);
  const actualFiles = new Set(await listRegularFiles(root));
  if (
    expectedFiles.size !== actualFiles.size
    || [...expectedFiles].some((file) => !actualFiles.has(file))
  ) {
    fail("package file inventory mismatch");
  }

  const artifacts = new Map();
  for (const vector of manifest.vectors) {
    const absolute = path.resolve(root, ...vector.artifact_path.split("/"));
    if (!absolute.startsWith(`${root}${path.sep}`)) {
      fail("artifact path escapes package");
    }
    const stat = await lstat(absolute);
    if (!stat.isFile() || stat.isSymbolicLink()) {
      fail(`invalid artifact: ${vector.id}`);
    }
    const data = await readFile(absolute);
    if (data.length !== vector.length) {
      fail(`artifact length mismatch: ${vector.id}`);
    }
    if (createHash("sha256").update(data).digest("hex") !== vector.sha256) {
      fail(`artifact SHA-256 mismatch: ${vector.id}`);
    }
    artifacts.set(vector.id, data);
  }
  return artifacts;
}
