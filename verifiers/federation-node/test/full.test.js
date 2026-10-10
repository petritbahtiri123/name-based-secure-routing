import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { cp, mkdtemp, readFile, rm, writeFile, mkdir, realpath, rename, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";

import { verifyPackage } from "../src/verifier.js";
import { verifySignedFixture } from "../src/signed.js";
import { loadAuthorities } from "../src/registry.js";

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

test("v2 requires explicit selection and preserves all vector outcomes", async () => {
  const v2 = "federation-v0.1-development-v2";
  const dir = path.resolve(packageDir, "../" + v2);
  await assert.rejects(verifyPackage(dir));
  assert.deepEqual(await verifyPackage(dir, v2), await verifyPackage(packageDir));
  await assert.rejects(verifyPackage(dir, "unknown"));
  for (const version of ["federation-v0.1-development-v1", v2]) {
    const a = await loadAuthorities(version === v2 ? dir : packageDir, version);
    for (const purpose of [15, 16, 17, 255]) {
      assert.equal(a.registries.key_purposes.values.has(purpose), version === v2 && purpose < 17);
    }
  }
});


test("authority snapshots reject missing, changed and cross-version bytes",async(t)=>{
 const repo=path.resolve(packageDir,"../..");
 const development="docs/protocol/registries/federation-v0.1-development.json",archive="docs/protocol/registries/archive/federation-v0.1-development-v1.json";
 for(const version of ["federation-v0.1-development-v1","federation-v0.1-development-v2"]){
  const source=version.endsWith("v1")?packageDir:path.resolve(packageDir,"../"+version);
  const root=await realpath(await mkdtemp(path.join(tmpdir(),"nbsr-fed-authority-")));
  t.after(()=>rm(root,{recursive:true,force:true}));
  const pkg=path.join(root,"vectors","package");await cp(source,pkg,{recursive:true});
  const locks=JSON.parse(await readFile(path.join(pkg,"authority-locks.json")));
  for(const item of locks.authorities){const rel=version.endsWith("v1")&&item.path===development?archive:item.path;const dst=path.join(root,rel);await mkdir(path.dirname(dst),{recursive:true});await cp(path.join(repo,rel),dst);}
  await verifyPackage(pkg,version);
  const rel=version.endsWith("v1")?archive:development,target=path.join(root,rel),original=await readFile(target);
  await rm(target);await assert.rejects(verifyPackage(pkg,version));
  await writeFile(target,Buffer.concat([original,Buffer.from(" ")]));await assert.rejects(verifyPackage(pkg,version));
  await writeFile(target,await readFile(path.join(repo,version.endsWith("v1")?development:archive)));await assert.rejects(verifyPackage(pkg,version));
  await writeFile(target,original);
  const parent=path.dirname(target),moved=parent+"-real";
  await rename(parent,moved);await symlink(moved,parent,process.platform==="win32"?"junction":"dir");
  await assert.rejects(verifyPackage(pkg,version),/unsafe authority alias/);
 }
});


test("authority API cannot be supplied an unauthenticated lock map", async()=>{
 await assert.rejects(loadAuthorities(packageDir,new Map()),/unsupported package version/);
});


test("result signing purposes cannot replace federation signers",async()=>{
 const original=JSON.parse(await readFile(path.join(packageDir,"signed-vectors.json")));
 for(const purpose of [15,16]){const changed=structuredClone(original);changed.trusted_signers[0].key_purpose=purpose;assert.throws(()=>verifySignedFixture(changed),/ERR_KEY_PURPOSE/);}
});
