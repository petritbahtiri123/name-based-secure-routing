import { createHash } from "node:crypto";
import { readdir } from "node:fs/promises";
import path from "node:path";
import { parseStrictJson } from "./strict-json.js";
import { readStableRegular } from "./safe-file.js";
const MANIFEST_LIMIT=262_144,ARTIFACT_LIMIT=1_000_000;

const TOP_FIELDS = ["artifacts", "authority", "format_version", "package", "package_version"];
const ARTIFACT_FIELDS = ["class", "dependencies", "enforcement", "expected_outcome", "expected_reason", "expected_state_digest", "federation_version", "fixed_time", "id", "length", "mutation", "path", "profile", "sha256"];

function exactFields(value, fields, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} must be an object`);
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((key, i) => key !== expected[i])) throw new Error(`${label} has unexpected fields`);
}

function safeRelativePath(value) {
  return typeof value === "string" && value.length > 0 && !path.isAbsolute(value) && !value.includes("\\") && value.split("/").every((part) => part !== "" && part !== "." && part !== "..");
}

function assertAcyclic(artifacts) {
  const graph = new Map(artifacts.map((item) => [item.id, item.dependencies]));
  const active = new Set();
  const done = new Set();
  function visit(id) {
    if (active.has(id)) throw new Error("manifest dependency cycle");
    if (done.has(id)) return;
    active.add(id);
    for (const dependency of graph.get(id)) visit(dependency);
    active.delete(id);
    done.add(id);
  }
  for (const id of graph.keys()) visit(id);
}

export async function verifyManifest(packageDir) {
  const raw = await readStableRegular(path.join(packageDir,"manifest.json"),{maxBytes:MANIFEST_LIMIT,label:"manifest"});
  let manifest;
  try { manifest = parseStrictJson(raw,{maxBytes:262_144,maxDepth:16}); } catch(error) { throw new Error(`malformed manifest JSON: ${error.message}`); }
  exactFields(manifest, TOP_FIELDS, "manifest");
  if (manifest.format_version !== 1) throw new Error("unsupported manifest format version");
  if (manifest.package !== "federation-v0.1" || manifest.package_version !== "federation-v0.1-development-v1") throw new Error("unexpected package/profile version");
  if (!Array.isArray(manifest.artifacts) || manifest.artifacts.length === 0) throw new Error("manifest artifacts must be non-empty");

  const ids = new Set();
  const paths = new Set();
  for (const artifact of manifest.artifacts) {
    exactFields(artifact, ARTIFACT_FIELDS, "manifest artifact");
    if (typeof artifact.id !== "string" || ids.has(artifact.id)) throw new Error("duplicate or invalid artifact ID");
    if (!safeRelativePath(artifact.path)) throw new Error("unsafe artifact path");
    if (paths.has(artifact.path)) throw new Error("duplicate artifact path");
    if (!Array.isArray(artifact.dependencies) || artifact.dependencies.some((id) => typeof id !== "string")) throw new Error("invalid artifact dependencies");
    ids.add(artifact.id); paths.add(artifact.path);
  }
  for (const artifact of manifest.artifacts) for (const dependency of artifact.dependencies) if (!ids.has(dependency)) throw new Error("unknown manifest dependency");
  assertAcyclic(manifest.artifacts);

  const entries=await readdir(packageDir,{withFileTypes:true});if(entries.some(entry=>entry.isSymbolicLink()||(!entry.isFile()&&entry.name!=="."&&entry.name!=="..")))throw new Error("package entries must be regular files");
  const actualFiles = entries.filter((entry) => entry.isFile()).map((entry) => entry.name).filter((name) => name !== "manifest.json").sort();
  const listedFiles = [...paths].sort();
  const extra = actualFiles.find((name) => !paths.has(name));
  if (extra) throw new Error(`unlisted package file: ${extra}`);
  if (actualFiles.length !== listedFiles.length || listedFiles.some((name, i) => name !== actualFiles[i])) throw new Error("manifest inventory incomplete");

  const files=new Map();
  for (const artifact of manifest.artifacts) {
    if(!Number.isSafeInteger(artifact.length)||artifact.length<0||artifact.length>ARTIFACT_LIMIT)throw new Error(`manifest artifact byte limit exceeded: ${artifact.path}`);
    const target=path.join(packageDir,artifact.path),bytes=await readStableRegular(target,{maxBytes:artifact.length,label:`artifact ${artifact.path}`});
    if (artifact.length !== bytes.length) throw new Error(`manifest length mismatch: ${artifact.path}`);
    const digest = createHash("sha256").update(bytes).digest("hex");
    if (!/^[0-9a-f]{64}$/.test(artifact.sha256) || digest !== artifact.sha256) throw new Error(`manifest digest mismatch: ${artifact.path}`);
    files.set(artifact.path,bytes);
  }
  const result={artifacts:manifest.artifacts.length,package:manifest.package,packageVersion:manifest.package_version};Object.defineProperty(result,"files",{value:files});return result;
}
