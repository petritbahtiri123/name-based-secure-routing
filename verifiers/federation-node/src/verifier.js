import path from "node:path";
import { fileURLToPath } from "node:url";
import { verifyCapabilityFixture } from "./capability.js";
import { verifyManifest } from "./manifest.js";
import { runMutationChecks } from "./mutations.js";
import { verifyPrecedenceFixture } from "./precedence.js";
import { loadAuthorities } from "./registry.js";
import { verifyStaticFixture } from "./schema.js";
import { verifySignedFixture } from "./signed.js";
import { verifyStateFixture } from "./state.js";
import { verifyThresholdFixture } from "./threshold.js";
import { parseStrictJson } from "./strict-json.js";
function json(manifest,name){const bytes=manifest.files.get(name);if(!bytes)throw new Error(`verified artifact unavailable: ${name}`);return parseStrictJson(bytes,{maxBytes:1_000_000,maxDepth:96});}
export async function verifyPackage(packageDir){
  const manifest=await verifyManifest(packageDir),authorities=await loadAuthorities(packageDir,manifest.files);
  const staticFixture=json(manifest,"static-vectors.json"),signed=json(manifest,"signed-vectors.json"),threshold=json(manifest,"threshold-vectors.json"),capability=json(manifest,"capability-vectors.json"),state=json(manifest,"stateful-scenarios.json");
  return {
    manifestArtifacts:manifest.artifacts,
    staticVectors:verifyStaticFixture(staticFixture,authorities),
    signedVectors:verifySignedFixture(signed),
    thresholdVectors:verifyThresholdFixture(threshold,authorities),
    capabilityVectors:verifyCapabilityFixture(capability),
    precedenceCases:verifyPrecedenceFixture(json(manifest,"error-precedence.json")),
    stateScenarios:verifyStateFixture(state),
    mutationTests:await runMutationChecks({signed,capability,threshold,state},authorities),
  };
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  try{const result=await verifyPackage(path.resolve(process.argv[2]??"../../vectors/federation-v0.1"));for(const [key,value] of Object.entries(result))console.log(`${key}: ${value}`);}catch(error){console.error(`Federation verification failed: ${error.message}`);process.exitCode=1;}
}
