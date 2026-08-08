import { createHash } from "node:crypto";
import { decodeCanonical } from "./cbor.js";
import { publicKeyFromRaw, verifySign1 } from "./cose.js";

const OBJECTS=new Map([[1,"OperatorRegistryRecord"],[2,"KeyAuthorizationRecord"],[6,"TransparencyCheckpoint"],[8,"ConsistencyProof"]]);
const FROZEN_REQUIREMENTS=new Map([
  ["operator-registrar",{authority_class:3,key_purpose:3,object_class:"OperatorRegistryRecord",requirement_id:"operator-registrar",subject_field:0}],
  ["key-identity-root",{authority_class:1,key_purpose:1,object_class:"KeyAuthorizationRecord",requirement_id:"key-identity-root",subject_field:32}],
  ["key-recovery",{authority_class:2,key_purpose:2,object_class:"KeyAuthorizationRecord",requirement_id:"key-recovery",subject_field:32}],
  ["checkpoint-log",{authority_class:5,key_purpose:8,object_class:"TransparencyCheckpoint",requirement_id:"checkpoint-log",subject_field:32}],
  ["consistency-log",{authority_class:5,key_purpose:8,object_class:"ConsistencyProof",requirement_id:"consistency-log",subject_field:32}],
]);
const sha=value=>createHash("sha256").update(value).digest();
const exactHex=(value,min,max=min)=>typeof value==="string"&&value.length%2===0&&value.length/2>=min&&value.length/2<=max&&/^[0-9a-f]+$/.test(value);
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const exactKeys=(value,expected)=>value&&typeof value==="object"&&!Array.isArray(value)&&same(Object.keys(value).sort(),[...expected].sort());
const safe=value=>Number.isSafeInteger(value);

function validateRecord(record,kid,now,state){
  if(!record||!exactHex(record.genesis_public_key,32)||!exactHex(record.signing_public_key,32)||!exactHex(record.operator_id,32)||!exactHex(record.kid,1,64)||!(record.subject_id===""||exactHex(record.subject_id,32)))return "ERR_IDENTITY";
  const genesis=Buffer.from(record.genesis_public_key,"hex"),operator=sha(Buffer.concat([Buffer.from("NBSR-FEDERATION-OPERATOR-ID-v1"),Buffer.from([0,1]),genesis]));
  if(!operator.equals(Buffer.from(record.operator_id,"hex"))||record.kid!==kid.toString("hex"))return "ERR_IDENTITY";
  if(!state||!safe(state.evaluation_time)||!safe(state.generation)||!safe(state.sequence)||state.generation<1||state.sequence<1||now!==state.evaluation_time||!safe(record.generation)||!safe(record.sequence)||record.generation!==state.generation||record.sequence!==state.sequence)return "ERR_REPLAY";
  if(typeof record.revoked!=="boolean")return "ERR_IDENTITY";if(record.revoked)return "ERR_REVOKED";if(!safe(record.key_lifecycle)||record.key_lifecycle!==2)return "ERR_KEY_LIFECYCLE";
  if(!safe(now)||!safe(record.not_before)||!safe(record.expires_at)||record.not_before<0||record.expires_at>253402300799||record.expires_at<=record.not_before||now<record.not_before||now>=record.expires_at)return "ERR_FRESHNESS";
  return "NONE";
}
function deriveRequirement(object,requirements){
  if(!(object instanceof Map)||!OBJECTS.has(object.get(1)))return null;const objectClass=OBJECTS.get(object.get(1));let id;
  if(objectClass==="OperatorRegistryRecord")id="operator-registrar";
  else if(objectClass==="KeyAuthorizationRecord"){const authority=object.get(37);if(!(authority instanceof Map))return null;id=authority.get(1)===1?"key-identity-root":authority.get(1)===2?"key-recovery":null;}
  else if(objectClass==="TransparencyCheckpoint")id="checkpoint-log";else if(objectClass==="ConsistencyProof")id="consistency-log";
  if(!id)return null;const actual=requirements.get(id),frozen=FROZEN_REQUIREMENTS.get(id);return actual&&same(actual,frozen)?actual:null;
}
function validateAuthority(record,requirement,object){
  if(record.key_purpose!==requirement.key_purpose)return "ERR_KEY_PURPOSE";if(record.authority_class!==requirement.authority_class)return "ERR_AUTHORITY";
  if(requirement.subject_field===0)return record.subject_id===""?"NONE":"ERR_IDENTITY";
  if(!exactHex(record.subject_id,32))return "ERR_IDENTITY";const expected=Buffer.from(record.subject_id,"hex"),subject=object.get(requirement.subject_field);if(!Buffer.isBuffer(subject)||!subject.equals(expected))return "ERR_IDENTITY";
  if(requirement.object_class==="KeyAuthorizationRecord"){const authority=object.get(37);if(!(authority instanceof Map)||authority.get(1)!==requirement.authority_class||!Buffer.isBuffer(authority.get(2))||!authority.get(2).equals(expected)||!Buffer.isBuffer(authority.get(3))||!authority.get(3).equals(Buffer.from(record.kid,"hex"))||!Buffer.isBuffer(authority.get(4))||!authority.get(4).equals(expected))return "ERR_IDENTITY";}
  return "NONE";
}
function evaluate(vector,signers,requirements,state){
  try{
    if(!exactHex(vector.cose_sign1_hex,1,1_048_576))throw new Error("canonical COSE hex required");const bytes=Buffer.from(vector.cose_sign1_hex,"hex"),parsed=decodeCanonical(bytes,{allowTag18:true});const protectedMap=decodeCanonical(parsed.value[0]),kid=protectedMap.get(4),record=signers.get(kid.toString("hex"));
    let reason=validateRecord(record,kid,vector.fixed_context?.evaluation_time,state);if(reason!=="NONE")return{outcome:"REJECT",reason};
    const result=verifySign1(bytes,publicKeyFromRaw(Buffer.from(record.signing_public_key,"hex")));
    let object;try{object=decodeCanonical(result.payload);}catch{return{outcome:"REJECT",reason:"ERR_SCHEMA"}};
    const requirement=deriveRequirement(object,requirements);if(!requirement)return{outcome:"REJECT",reason:"ERR_AUTHORITY"};reason=validateAuthority(record,requirement,object);if(reason!=="NONE")return{outcome:"REJECT",reason};
    return{outcome:"ACCEPT",reason:"NONE",payloadDigest:result.payloadDigest,kid:result.kid.toString("hex"),objectClass:requirement.object_class};
  }catch(error){return{outcome:"REJECT",reason:/signature invalid/.test(error.message)?"ERR_SIGNATURE_INVALID":"ERR_PARSE"};}
}
export function verifySignedFixture(fixture){
  const rootKeys=["authority","authority_state","format_version","object_coverage","signer_requirements","trusted_signers","vectors"],recordKeys=["authority_class","expires_at","generation","genesis_public_key","key_lifecycle","key_purpose","kid","not_before","operator_id","record_id","revoked","sequence","signing_public_key","subject_id"],requirementKeys=["authority_class","key_purpose","object_class","requirement_id","subject_field"],vectorKeys=["case","cose_sign1_hex","dependencies","expected","expected_reason","fixed_context","id","kid_hex","mutation","object_class","payload_sha256","threshold_envelope"];
  if(!exactKeys(fixture,rootKeys)||fixture.format_version!==1||fixture.vectors.length!==12||fixture.object_coverage.length!==18||!Array.isArray(fixture.trusted_signers)||!Array.isArray(fixture.signer_requirements)||!exactKeys(fixture.authority_state,["evaluation_time","generation","sequence"]))throw new Error("signed fixture structure/count mismatch");
  const signers=new Map(),requirements=new Map(),signingKeys=new Set();let prior="";for(const record of fixture.trusted_signers){if(!exactKeys(record,recordKeys)||!safe(record.authority_class)||!safe(record.key_purpose)||!safe(record.generation)||!safe(record.sequence)||!safe(record.not_before)||!safe(record.expires_at)||typeof record.revoked!=="boolean"||!record.record_id||record.record_id<=prior||signers.has(record.kid)||signingKeys.has(record.signing_public_key))throw new Error("trusted signer inventory invalid");const recordReason=validateRecord(record,Buffer.from(record.kid,"hex"),fixture.authority_state.evaluation_time,fixture.authority_state);if(recordReason!=="NONE")throw new Error(`trusted signer inventory invalid: ${recordReason}`);prior=record.record_id;signers.set(record.kid,record);signingKeys.add(record.signing_public_key);}prior="";for(const requirement of fixture.signer_requirements){if(!exactKeys(requirement,requirementKeys)||!safe(requirement.authority_class)||!safe(requirement.key_purpose)||!safe(requirement.subject_field)||!requirement.requirement_id||requirement.requirement_id<=prior||requirements.has(requirement.requirement_id))throw new Error("signer requirement inventory invalid");prior=requirement.requirement_id;requirements.set(requirement.requirement_id,requirement);}
  for(const vector of fixture.vectors){if(!exactKeys(vector,vectorKeys)||!exactHex(vector.cose_sign1_hex,1,1_048_576)||!exactHex(vector.kid_hex,1,64)||!exactHex(vector.payload_sha256,32))throw new Error("canonical COSE hex required");}
  for(const vector of fixture.vectors){const got=evaluate(vector,signers,requirements,fixture.authority_state);if(got.payloadDigest&&got.payloadDigest!==vector.payload_sha256)throw new Error(`${vector.id}: payload digest oracle mismatch`);if(got.kid&&got.kid!==vector.kid_hex)throw new Error(`${vector.id}: kid oracle mismatch`);if(got.objectClass&&got.objectClass!==vector.object_class)throw new Error(`${vector.id}: object class oracle mismatch`);if(got.outcome!==vector.expected||got.reason!==vector.expected_reason)throw new Error(`${vector.id}: signed result mismatch: ${got.outcome}/${got.reason}`);}return fixture.vectors.length;
}
