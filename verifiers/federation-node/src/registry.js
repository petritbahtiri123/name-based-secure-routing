import { createHash } from "node:crypto";
import path from "node:path";
import { realpath } from "node:fs/promises";
import { parseStrictJson } from "./strict-json.js";
import { readStableRegular } from "./safe-file.js";
import { verifyManifest, selectedAuthority, VERSION1 } from "./manifest.js";
const sha=(b)=>createHash("sha256").update(b).digest("hex");
export async function loadAuthorities(packageDir,version=VERSION1){
  const selected=selectedAuthority(version);
  const manifest=await verifyManifest(packageDir,version),packageFiles=manifest.files;
  const root=path.resolve(packageDir,"../.."),lockBytes=packageFiles.get("authority-locks.json"),locks=parseStrictJson(lockBytes,{maxBytes:65_536,maxDepth:16});
  if(locks.accepted_baseline_commit!==selected.baseline||locks.format_version!==1||locks.federation_object_count!==18||locks.core_v02_artifact_count!==110||locks.schema_literal_count!==28||locks.threshold_literal_count!==89||locks.threshold_evidence_capability!==6)throw new Error("immutable authority lock mismatch");
  const bytesByPath=new Map();
  for(const authority of locks.authorities){if(!Number.isSafeInteger(authority.length)||authority.length<0||authority.length>1_000_000)throw new Error(`authority byte limit exceeded: ${authority.path}`);const target=path.join(root,authority.path==="docs/protocol/registries/federation-v0.1-development.json"?selected.development:authority.path);if(await realpath(target)!==path.resolve(target))throw new Error("unsafe authority alias");const bytes=await readStableRegular(target,{maxBytes:authority.length,label:`authority ${authority.path}`});if(bytes.length!==authority.length||sha(bytes)!==authority.sha256)throw new Error(`immutable authority drift: ${authority.path}`);bytesByPath.set(authority.path,bytes);}
  const development=parseStrictJson(bytesByPath.get("docs/protocol/registries/federation-v0.1-development.json"),{maxBytes:100_000,maxDepth:64});
  const schema=parseStrictJson(bytesByPath.get("docs/protocol/registries/federation-v0.1-schema-proposal.json"),{maxBytes:300_000,maxDepth:96});
  const threshold=parseStrictJson(bytesByPath.get("docs/protocol/registries/federation-v0.1-threshold-container-proposal.json"),{maxBytes:20_000,maxDepth:64});
  if(development.profile!=="nbsr-federation-dev-v1"||development.wire_freeze!==false)throw new Error("development profile mismatch");
  if(Object.keys(schema.objects).length!==18)throw new Error("Federation object registry must contain 18 objects");
  const objectTypes=new Map(development.registries.object_types.map(entry=>[entry.name,entry.value]));if(objectTypes.size!==18)throw new Error("ObjectType registry must contain 18 values");
  const registries=Object.fromEntries(Object.entries(development.registries).map(([name,entries])=>[name,{byName:new Map(entries.map(x=>[x.name,x.value])),values:new Set(entries.map(x=>x.value))}]));
  return{development,schema,threshold,objectTypes,registries,authorityLocks:locks.authorities.length,manifest};
}
