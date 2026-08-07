import { createHash } from "node:crypto";
import { decodeCanonical, encodeCanonical, Tagged } from "./cbor.js";
import { publicKeyFromRaw, verifySign1 } from "./cose.js";
const sha=(b)=>createHash("sha256").update(b).digest();
const hex=(b)=>Buffer.isBuffer(b)?b.toString("hex"):null;
const uint=(v)=>typeof v==="number"&&Number.isSafeInteger(v)&&v>=0;
const exact=(m,required,optional=[])=>m instanceof Map&&[...m.keys()].every(k=>required.includes(k)||optional.includes(k))&&required.every(k=>m.has(k));
const bstr=(v,min,max=min)=>Buffer.isBuffer(v)&&v.length>=min&&v.length<=max;
const sortedUnique=(items,key=x=>typeof x==="number"?String(x).padStart(20,"0"):Buffer.isBuffer(x)?x.toString("hex"):String(x))=>Array.isArray(items)&&items.every((x,i)=>i===0||key(items[i-1])<key(x));
function outcome(reason,decision="REJECT"){return{outcome:decision,reason,mutation:false,enforcement:decision==="ACCEPT"?"NONE":"DENY_NEW_USE"};}
function extensionsOkay(value){if(!Array.isArray(value)||value.length>16)return false;let prev=-1;for(const item of value){if(!exact(item,[1,2,3])||!uint(item.get(1))||item.get(1)<1||item.get(1)>65535||typeof item.get(2)!=="boolean"||!bstr(item.get(3),0,4096)||item.get(1)<=prev)return false;prev=item.get(1);}return true;}
function unsupportedCritical(value){return Array.isArray(value)&&value.some(item=>item instanceof Map&&item.get(2)===true);}
function lineageOkay(m){return exact(m,[1,2,3])&&(m.get(1)===null||uint(m.get(1)))&&(m.get(2)===null||uint(m.get(2)))&&(m.get(3)===null||bstr(m.get(3),32));}
function authOkay(m){return exact(m,[1,2,3,4,5,6,7])&&uint(m.get(1))&&bstr(m.get(2),16,64)&&uint(m.get(3))&&uint(m.get(4))&&bstr(m.get(5),32)&&uint(m.get(6))&&typeof m.get(7)==="string";}
function digestWithout(map,key){const copy=new Map(map);copy.delete(key);return sha(encodeCanonical(copy));}
function bindingDigest(context){return sha(encodeCanonical(new Map([[1,"NBSR-FEDERATION-CAPABILITY-SESSION-BINDING-v1"],[2,context.selected_core_version],[3,context.agreed_federation_version],[4,context.agreed_profile_id],[5,[6]],[6,Buffer.from(context.authenticated_session_transcript_digest,"hex")]])));}
function expectedSignatureContext(container,groupId,context){return new Map([[1,"NBSR-FEDERATION-THRESHOLD-SIGNATURE-v1"],[2,1],[3,"nbsr-federation-dev-v1"],[4,container.get(3)],[5,container.get(4)],[6,container.get(5).get(2)],[7,groupId],[8,container.get(6)],[9,container.get(7)],[10,container.get(8)],[11,6],[12,bindingDigest(context)]]);}
function schema(container,authorities){
  if(!exact(container,[1,2,3,4,5,6,7,8,9],[10]))return"ERR_SCHEMA";
  if(typeof container.get(1)==="boolean"||!uint(container.get(1)))return"ERR_VERSION";
  if(container.get(1)!==1||container.get(2)!=="nbsr-federation-dev-v1")return"ERR_VERSION";
  if(!authorities.registries.object_types.values.has(container.get(3))||!bstr(container.get(4),32)||!bstr(container.get(6),32)||!lineageOkay(container.get(7))||!authOkay(container.get(8))||!Array.isArray(container.get(9)))return"ERR_SCHEMA";
  if(container.has(10)&&!extensionsOkay(container.get(10)))return"ERR_SCHEMA";if(container.has(10)&&unsupportedCritical(container.get(10)))return"ERR_UNSUPPORTED_CRITICAL";
  const p=container.get(5);if(!exact(p,[1,2,3,4,5,6,7,9],[8])||!uint(p.get(1))||p.get(1)!==1||!bstr(p.get(2),32)||typeof p.get(3)!=="string"||p.get(3).length<1||p.get(3).length>64||typeof p.get(4)!=="boolean"||!Array.isArray(p.get(5))||!sortedUnique(p.get(6))||!sortedUnique(p.get(7))||!sortedUnique(p.get(9))||p.get(9).some(x=>typeof x!=="string"))return"ERR_SCHEMA";
  if(p.has(8)&&!extensionsOkay(p.get(8)))return"ERR_SCHEMA";if(p.has(8)&&unsupportedCritical(p.get(8)))return"ERR_UNSUPPORTED_CRITICAL";
  const policyCopy=new Map(p);policyCopy.set(2,null);if(!sha(encodeCanonical(policyCopy)).equals(p.get(2)))return"ERR_AUTHORITY";
  for(const g of p.get(5)){if(!exact(g,[1,2,3,4,5,6,7,8,9,10],[11])||typeof g.get(1)!=="string"||g.get(1).length<1||g.get(1).length>32||typeof g.get(2)==="boolean"||!uint(g.get(2))||g.get(2)<1||g.get(2)>5||typeof g.get(3)==="boolean"||!uint(g.get(3))||g.get(3)<g.get(2)||g.get(3)>5||!sortedUnique(g.get(4))||!sortedUnique(g.get(5),x=>`${String(x[0]).padStart(4,"0")}:${String(x[1]).padStart(4,"0")}`)||!sortedUnique(g.get(6))||typeof g.get(7)==="boolean"||!uint(g.get(7))||g.get(7)<1||g.get(7)>g.get(2)||!sortedUnique(g.get(8))||typeof g.get(9)!=="boolean"||!bstr(g.get(10),32))return"ERR_SCHEMA";if(g.has(11)&&!extensionsOkay(g.get(11)))return"ERR_SCHEMA";if(g.has(11)&&unsupportedCritical(g.get(11)))return"ERR_UNSUPPORTED_CRITICAL";}
  return null;
}
export function evaluateThresholdVector(vector,authorities){
  if(typeof vector.canonical_cbor_hex!=="string"||vector.canonical_cbor_hex.length%2||!/^[0-9a-f]*$/.test(vector.canonical_cbor_hex))return outcome("ERR_SCHEMA");
  const bytes=Buffer.from(vector.canonical_cbor_hex,"hex"),limits=authorities.threshold.resource_limits;
  if(bytes.length>limits.max_encoded_container_bytes)return outcome("ERR_RESOURCE_LIMIT");
  let c;try{c=decodeCanonical(bytes,{allowTag18:false,maxBytes:limits.max_encoded_container_bytes,maxDepth:limits.max_nested_depth,maxArrayItems:256,maxMapPairs:128,maxStringBytes:4096});}catch(error){return outcome(/limit/.test(error.message)?"ERR_RESOURCE_LIMIT":"ERR_NON_CANONICAL");}
  const schemaReason=schema(c,authorities);if(schemaReason)return outcome(schemaReason);
  const p=c.get(5),auth=c.get(8),ctx=vector.validation_context;
  if(!ctx||ctx.selected_core_version!==2||ctx.agreed_federation_version!==1||ctx.agreed_profile_id!=="nbsr-federation-dev-v1")return outcome("ERR_VERSION");
  if(ctx.single_sign1_fallback)return outcome("ERR_DOWNGRADE");
  if(!ctx.capability_agreement_authenticated)return outcome("ERR_DOWNGRADE");
  const negotiated=ctx.negotiated_capabilities??[],authenticated=ctx.authenticated_capabilities??[];
  if(!Array.isArray(negotiated)||!Array.isArray(authenticated)||new Set(negotiated).size!==negotiated.length||new Set(authenticated).size!==authenticated.length)return outcome("ERR_SCHEMA");
  if(!authenticated.includes("THRESHOLD_EVIDENCE")||!negotiated.includes("THRESHOLD_EVIDENCE"))return outcome(authenticated.includes("THRESHOLD_EVIDENCE")?"ERR_DOWNGRADE":"ERR_UNSUPPORTED_CRITICAL");
  if(hex(auth.get(2))!==ctx.expected_request_event_transition_id)return outcome("ERR_REPLAY");
  if(auth.get(6)!==1)return outcome("ERR_SCHEMA");
  if(auth.get(4)<=auth.get(3))return outcome("ERR_SCHEMA");
  if(ctx.now<auth.get(3)||ctx.now>auth.get(4))return outcome("ERR_FRESHNESS");
  if(!digestWithout(auth,5).equals(auth.get(5)))return outcome("ERR_REPLAY");
  if(!p.get(6).includes(c.get(3)))return outcome("ERR_AUTHORITY");
  if(!p.get(7).includes(auth.get(1)))return outcome("ERR_REPLAY");
  if(!p.get(9).includes(auth.get(7)))return outcome(p.get(4)?"ERR_POLICY_EXPANSION":"ERR_AUTHORITY");
  if(p.get(4)&&auth.get(7)!=="deny")return outcome("ERR_POLICY_EXPANSION");
  const requirements=p.get(5),groups=c.get(9);
  const named=authorities.threshold.named_policies[p.get(3)];if(!named)return outcome("ERR_AUTHORITY");
  const objectValues=named.allowed_object_classes.map(x=>authorities.registries.object_types.byName.get(x)),messageValues=named.allowed_message_types.map(x=>authorities.registries.message_types.byName.get(x));
  if(JSON.stringify(p.get(6))!==JSON.stringify(objectValues))return outcome("ERR_AUTHORITY");
  if(JSON.stringify(p.get(7))!==JSON.stringify(messageValues))return outcome("ERR_REPLAY");
  if(p.get(4)!==named.deny_only||JSON.stringify(p.get(9))!==JSON.stringify(named.allowed_authority_effects))return outcome("ERR_AUTHORITY");
  if(requirements.length!==named.groups.length)return outcome("ERR_AUTHORITY");
  for(let i=0;i<requirements.length;i++){const req=requirements[i],want=named.groups[i],classValue=authorities.registries.authority_classes.byName.get(want.class),purposeValue=authorities.registries.key_purposes.byName.get(want.purpose);if(req.get(1)!==want.id||req.get(2)!==want.required||req.get(3)!==want.eligible||JSON.stringify(req.get(4))!==JSON.stringify([classValue])||JSON.stringify(req.get(5))!==JSON.stringify([[classValue,want.required]])||req.get(7)!==Math.min(named.minimum_organizations,want.required)||JSON.stringify(req.get(8))!==JSON.stringify([purposeValue])||req.get(9)!==named.deny_only)return outcome("ERR_AUTHORITY");}
  if(groups.length>limits.max_threshold_groups||groups.some(g=>g instanceof Map&&Array.isArray(g.get(2))&&g.get(2).length>limits.max_signatures_per_group)||groups.reduce((n,g)=>n+(Array.isArray(g?.get?.(2))?g.get(2).length:0),0)>limits.max_total_signer_entries)return outcome("ERR_RESOURCE_LIMIT");
  if(groups.length!==requirements.length)return outcome("ERR_AUTHORITY");
  const registry=ctx.accepted_authority_registry??[],used=new Set();
  for(let i=0;i<requirements.length;i++){
    const req=requirements[i],group=groups[i];if(!exact(group,[1,2])||group.get(1)!==req.get(1)||!Array.isArray(group.get(2)))return outcome("ERR_AUTHORITY");
    if(!req.get(10).equals(c.get(6)))return outcome("ERR_SCOPE");
    if(req.get(6).length){const trusted=[...new Set(registry.filter(x=>x.eligible_policy_groups.includes(`${p.get(3)}:${group.get(1)}`)&&req.get(4).includes(x.authority_class)&&req.get(8).includes(x.key_purpose)).map(x=>x.authority_id))].sort();if(JSON.stringify(req.get(6).map(hex))!==JSON.stringify(trusted))return outcome("ERR_AUTHORITY");}
    const signers=group.get(2),ids=new Set(),orgs=new Set(),classCounts=new Map();let previous=null;
    for(const signer of signers){
      if(signer instanceof Map&&(Buffer.isBuffer(signer.get(2))&&signer.get(2).length>limits.max_authority_identity_bytes||Buffer.isBuffer(signer.get(4))&&signer.get(4).length>limits.max_kid_bytes||Buffer.isBuffer(signer.get(5))&&signer.get(5).length>limits.max_organization_identity_bytes))return outcome("ERR_RESOURCE_LIMIT");
      if(!exact(signer,[1,2,3,4,5,6,7],[8])||!uint(signer.get(1))||!bstr(signer.get(2),1,64)||!uint(signer.get(3))||!bstr(signer.get(4),1,64)||(signer.get(5)!==null&&!bstr(signer.get(5),1,64))||!bstr(signer.get(6),32)||!Buffer.isBuffer(signer.get(7)))return outcome("ERR_SCHEMA");
      if(signer.has(8)&&!extensionsOkay(signer.get(8)))return outcome("ERR_SCHEMA");if(signer.has(8)&&unsupportedCritical(signer.get(8)))return outcome("ERR_UNSUPPORTED_CRITICAL");
      const id=hex(signer.get(2)),order=[signer.get(1),id,signer.get(3),hex(signer.get(4))].map(String).join(":");if(previous!==null&&previous>=order)return outcome("ERR_AUTHORITY");previous=order;
      if(ids.has(id)||used.has(id))return outcome("ERR_AUTHORITY");ids.add(id);used.add(id);
      const entry=registry.find(x=>x.kid===hex(signer.get(4)));if(!entry)return outcome("ERR_IDENTITY");
      if(entry.authority_id!==id||entry.authority_class!==signer.get(1)||hex(signer.get(5))!==entry.organization_id||!req.get(4).includes(signer.get(1))||(req.get(6).length&&!req.get(6).some(x=>hex(x)===id))||!entry.eligible_policy_groups.includes(`${p.get(3)}:${group.get(1)}`))return outcome("ERR_AUTHORITY");
      if(entry.key_purpose!==signer.get(3)||!req.get(8).includes(signer.get(3)))return outcome("ERR_KEY_PURPOSE");
      if(entry.revoked)return outcome("ERR_REVOKED");if(ctx.now<entry.not_before||ctx.now>entry.expires_at)return outcome("ERR_FRESHNESS");
      if(!signer.get(6).equals(c.get(4)))return outcome("ERR_SIGNATURE_INVALID");
      const expected=expectedSignatureContext(c,group.get(1),ctx);let signed,sign1;
      try{sign1=decodeCanonical(signer.get(7),{allowTag18:true});signed=decodeCanonical(sign1 instanceof Tagged&&Array.isArray(sign1.value)?sign1.value[2]:Buffer.alloc(0));}catch(error){return outcome(/non-|order|shortest|canonical|trailing/.test(error.message)?"ERR_NON_CANONICAL":"ERR_SCHEMA");}
      if(!(signed instanceof Map))return outcome("ERR_SCHEMA");
      if(signed.get(11)!==6)return outcome("ERR_DOWNGRADE");
      try{signed=decodeCanonical(verifySign1(signer.get(7),publicKeyFromRaw(Buffer.from(entry.public_key,"hex"))).payload);}catch{return outcome("ERR_SIGNATURE_INVALID");}
      if(!exact(signed,[1,2,3,4,5,6,7,8,9,10,11,12]))return outcome("ERR_SCHEMA");
      if(signed.get(1)!==expected.get(1)||signed.get(2)!==1||signed.get(3)!==expected.get(3))return outcome("ERR_SCHEMA");
      if(signed.get(4)!==expected.get(4)||!signed.get(6)?.equals?.(expected.get(6))||signed.get(7)!==expected.get(7))return outcome("ERR_AUTHORITY");
      if(!signed.get(5)?.equals?.(expected.get(5)))return outcome("ERR_SIGNATURE_INVALID");
      if(!signed.get(8)?.equals?.(expected.get(8)))return outcome("ERR_SCOPE");
      if(!encodeCanonical(signed.get(9)).equals(encodeCanonical(expected.get(9))))return outcome("ERR_REPLAY");
      if(!encodeCanonical(signed.get(10)).equals(encodeCanonical(expected.get(10))))return outcome("ERR_REPLAY");
      if(signed.get(11)!==6)return outcome("ERR_DOWNGRADE");
      if(!signed.get(12)?.equals?.(expected.get(12)))return outcome("ERR_REPLAY");
      orgs.add(entry.organization_id);classCounts.set(entry.authority_class,(classCounts.get(entry.authority_class)??0)+1);
    }
    if(signers.length===0)return outcome("ERR_EVIDENCE_MISSING","PENDING");
    if(signers.length<req.get(2))return outcome("ERR_WITNESS_THRESHOLD","PENDING");
    if(orgs.size<req.get(7))return outcome("ERR_WITNESS_THRESHOLD");
    if(signers.length>req.get(3))return outcome("ERR_AUTHORITY");
    for(const pair of req.get(5))if((classCounts.get(pair[0])??0)<pair[1])return outcome("ERR_AUTHORITY");
  }
  return outcome("NONE","ACCEPT");
}
export function verifyThresholdFixture(fixture,authorities){
  if(fixture.format_version!==1||fixture.oracle_count!==89||fixture.vectors.length!==89)throw new Error("threshold fixture structure/count mismatch");
  for(const vector of fixture.vectors){const actual=evaluateThresholdVector(vector,authorities);if(actual.outcome!==vector.expected_decision||actual.reason!==vector.expected_reason||actual.enforcement!==vector.enforcement||actual.mutation!==vector.expected_mutation)throw new Error(`${vector.id}: threshold mismatch: ${actual.outcome}/${actual.reason}`);}
  return fixture.vectors.length;
}
