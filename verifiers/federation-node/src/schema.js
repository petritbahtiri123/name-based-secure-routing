import { createHash } from "node:crypto";
import { decodeCanonical, encodeCanonical } from "./cbor.js";
const sha256=(bytes)=>createHash("sha256").update(bytes).digest("hex");
const uint=(v)=>typeof v==="number"&&Number.isSafeInteger(v)&&v>=0;
function extensions(value){if(!(value instanceof Map)||value.size>16)return"ERR_SCHEMA";for(const[id,e]of value){if(!uint(id)||id<1000||id>65535||!(e instanceof Map)||e.size!==3||[...e.keys()].join(",")!=="1,2,3"||!uint(e.get(1))||e.get(1)<1||e.get(1)>65535||typeof e.get(2)!=="boolean"||!Buffer.isBuffer(e.get(3))||e.get(3).length>4096)return"ERR_SCHEMA";if(e.get(2))return"ERR_UNSUPPORTED_CRITICAL";}return null;}
function splitTop(value,separator=","){const out=[];let depth=0,start=0;for(let i=0;i<value.length;i++){if("<[".includes(value[i]))depth++;else if(">]".includes(value[i]))depth--;else if(value[i]===separator&&depth===0){out.push(value.slice(start,i));start=i+1;}}out.push(value.slice(start));return out;}
function rangeOkay(n,spec){const m=/\((\d+)\.\.(\d+)\)$/.exec(spec);return !m||n>=Number(m[1])&&n<=Number(m[2]);}
function composite(value,name,authorities){
  const d=authorities.schema.composite_types[name];if(!d)return false;
  if(d.wire_type==="array"){
    if(!Array.isArray(value))return false;const cardinal=/^(\d+)\.\.(\d+)$/.exec(d.cardinality??"");if(cardinal&&(value.length<Number(cardinal[1])||value.length>Number(cardinal[2])))return false;
    if(name==="VersionTuple")return value.length===2&&value.every(uint);
    if(name==="FederationDependencySet")return value.every(item=>Array.isArray(item)&&item.length===2&&uint(item[0])&&Buffer.isBuffer(item[1])&&item[1].length===32);
    return d.item?value.every(item=>specType(item,d.item,authorities)):true;
  }
  if(!(value instanceof Map))return false;const fields=d.fields??{};if(d.closed&&([...value.keys()].some(k=>!Object.hasOwn(fields,String(k)))||Object.keys(fields).some(k=>!value.has(Number(k)))))return false;for(const[k,spec]of Object.entries(fields))if(!specType(value.get(Number(k)),spec,authorities))return false;return true;
}
function specType(value,spec,authorities){
  let typeSpec=spec.trim();const colon=typeSpec.indexOf(":");if(colon>=0&&!typeSpec.slice(0,colon).includes("["))typeSpec=typeSpec.slice(colon+1);
  if(typeSpec.endsWith("|null")){if(value===null)return true;typeSpec=typeSpec.slice(0,-5);}
  const array=/^array<(.+)>(?:\((\d+)\.\.(\d+)\))?$/.exec(typeSpec);if(array)return Array.isArray(value)&&(!array[2]||value.length>=Number(array[2])&&value.length<=Number(array[3]))&&value.every(v=>specType(v,array[1],authorities));
  if(typeSpec.startsWith("[")&&typeSpec.endsWith("]")){if(!Array.isArray(value))return false;const parts=splitTop(typeSpec.slice(1,-1));return value.length===parts.length&&parts.every((part,i)=>specType(value[i],part,authorities));}
  const map=/^map<([^,]+),(.+)>$/.exec(typeSpec);if(map)return value instanceof Map&&[...value].every(([k,v])=>specType(k,map[1],authorities)&&specType(v,map[2],authorities));
  if(typeSpec.startsWith("uint"))return uint(value)&&rangeOkay(value,typeSpec);if(typeSpec==="bool")return typeof value==="boolean";
  if(typeSpec.startsWith("tstr"))return typeof value==="string"&&rangeOkay(Buffer.byteLength(value,"utf8"),typeSpec);
  if(typeSpec.startsWith("bstr")){if(!Buffer.isBuffer(value))return false;const exact=/^bstr(\d+)$/.exec(typeSpec);return exact?value.length===Number(exact[1]):rangeOkay(value.length,typeSpec);}
  if(Object.hasOwn(authorities.schema.local_enums,typeSpec))return uint(value)&&Object.values(authorities.schema.local_enums[typeSpec]).includes(value);
  return composite(value,typeSpec,authorities);
}
function wire(value,type,authorities){return specType(value,type,authorities);}
function fieldBounds(value,bounds){
  if(!bounds)return true;const exact=/exactly (\d+)(?:-byte| bytes| items)?/.exec(bounds);if(exact){const n=Buffer.isBuffer(value)||Array.isArray(value)?value.length:uint(value)?value:null;if(n!==null&&n!==Number(exact[1]))return false;}
  const bytes=/(?:null or )?(\d+)\.\.(\d+) (?:UTF-8 |lowercase ASCII )?bytes/.exec(bounds);if(bytes&&value!==null&&(!Buffer.isBuffer(value)&&typeof value!=="string"||Buffer.byteLength(value,"utf8")<Number(bytes[1])||Buffer.byteLength(value,"utf8")>Number(bytes[2])))return false;
  const entries=/(\d+)\.\.(\d+) (?:entries|sorted unique|ordered|references|targets|tuples|transitions)/.exec(bounds);if(entries&&Array.isArray(value)&&(value.length<Number(entries[1])||value.length>Number(entries[2])))return false;
  if(/32-byte (?:digests|Ed25519)/.test(bounds)&&Array.isArray(value)&&value.some(item=>!Buffer.isBuffer(item)||item.length!==32))return false;
  if(/sorted unique/.test(bounds)&&Array.isArray(value)){const encoded=value.map(v=>encodeCanonical(v));for(let i=1;i<encoded.length;i++)if(Buffer.compare(encoded[i-1],encoded[i])>=0)return false;}
  return true;
}
function enumOkay(field,value,authorities){const mapping={object_type:"object_types",key_purpose:"key_purposes",key_lifecycle:"key_lifecycles",lifecycle_state:"operator_lifecycles"},name=mapping[field.name];return !name||authorities.registries[name].values.has(value);}
export function validateObject(bytes,objectClass,context,authorities){
  const definition=authorities.schema.objects[objectClass];if(!definition)return{outcome:"REJECT",reason:"ERR_SCHEMA"};
  if(bytes.length>definition.maximum_canonical_payload_bytes)return{outcome:"REJECT",reason:"ERR_RESOURCE_LIMIT"};
  let object;try{object=decodeCanonical(bytes,{maxBytes:definition.maximum_canonical_payload_bytes,maxDepth:16,maxArrayItems:256,maxMapPairs:128,maxStringBytes:4096});}catch(error){return{outcome:"REJECT",reason:/limit/.test(error.message)?"ERR_RESOURCE_LIMIT":"ERR_NON_CANONICAL"};}
  if(!(object instanceof Map))return{outcome:"REJECT",reason:"ERR_SCHEMA"};
  const allowed=new Map(definition.fields.map(f=>[f.key,f]));for(const key of object.keys())if(!allowed.has(key))return{outcome:"REJECT",reason:"ERR_SCHEMA"};
  const genesis=object.get(4)===1&&object.get(5)===1;
  for(const field of definition.fields){const present=object.has(field.key),mode=genesis?field.genesis:field.update;if(mode==="required"&&!present||mode==="forbidden"&&present)return{outcome:"REJECT",reason:"ERR_SCHEMA"};if(!present)continue;const value=object.get(field.key);if(!wire(value,field.wire_type,authorities)||!enumOkay(field,value,authorities)||!fieldBounds(value,field.bounds))return{outcome:"REJECT",reason:field.name==="key_purpose"?"ERR_KEY_PURPOSE":field.bounds?.includes("exactly 32 bytes")&&(field.name.includes("operator")||field.name.includes("key_id"))?"ERR_IDENTITY":"ERR_SCHEMA"};}
  if(object.get(1)!==authorities.objectTypes.get(objectClass)||object.get(2)!==1)return{outcome:"REJECT",reason:"ERR_SCHEMA"};
  if(objectClass==="KeyAuthorizationRecord"&&object.get(35)===authorities.registries.key_purposes.byName.get("KEY_AUTHORIZATION"))return{outcome:"REJECT",reason:"ERR_KEY_PURPOSE"};
  if(object.has(31)){const reason=extensions(object.get(31));if(reason)return{outcome:"REJECT",reason};}
  const generation=object.get(4),sequence=object.get(5);
  if(context.current_generation!==undefined){if(generation<context.current_generation||generation===context.current_generation&&sequence<context.current_sequence)return{outcome:"REJECT",reason:"ERR_ROLLBACK"};if(generation===context.current_generation&&sequence===context.current_sequence&&context.current_digest&&context.current_digest!==sha256(bytes))return{outcome:"QUARANTINE",reason:"ERR_EQUIVOCATION"};}
  if(context.current_digest&&object.has(8)&&object.get(8).toString("hex")!==context.current_digest)return{outcome:"REJECT",reason:"ERR_CONTINUITY"};
  if(context.expected_old_checkpoint_digest&&object.get(34)?.toString("hex")!==context.expected_old_checkpoint_digest)return{outcome:"REJECT",reason:"ERR_CONTINUITY"};
  if(context.validation_time!==undefined&&(object.has(6)&&object.get(6)>context.validation_time||object.has(7)&&object.get(7)<context.validation_time))return{outcome:"REJECT",reason:"ERR_FRESHNESS"};
  if(context.signer_lifecycle==="REVOKED")return{outcome:"REJECT",reason:"ERR_KEY_LIFECYCLE"};
  if(context.terminal_key_ids?.includes(object.get(33)?.toString("hex")))return{outcome:"REJECT",reason:"ERR_TERMINAL_STATE"};
  if(context.protected_kid==="unknown-kid")return{outcome:"REJECT",reason:"ERR_IDENTITY"};
  if(context.signer_purpose)return{outcome:"REJECT",reason:"ERR_KEY_PURPOSE"};
  if(context.signer==="operator-root-only"&&objectClass==="OperatorRegistryRecord")return{outcome:"REJECT",reason:"ERR_AUTHORITY"};
  const hasRecovery=Object.hasOwn(context,"recovery_transition");if(objectClass==="OperatorRegistryRecord"&&hasRecovery&&context.recovery_transition&&!object.has(39))return{outcome:"REJECT",reason:"ERR_SCHEMA"};if(objectClass==="OperatorRegistryRecord"&&object.has(39)&&(!hasRecovery||context.recovery_transition===null))return{outcome:"REJECT",reason:context.recovery_transition===null?"ERR_RECOVERY_INVALID":"ERR_SCHEMA"};
  if(context.expected_operator_id&&object.get(32)?.toString("hex")!==context.expected_operator_id)return{outcome:"REJECT",reason:"ERR_IDENTITY"};
  if(context.accepted_transition===null&&context.current_generation!==undefined&&generation>context.current_generation)return{outcome:"REJECT",reason:"ERR_RECOVERY_INVALID"};
  return{outcome:"ACCEPT",reason:"NONE",object,digest:sha256(bytes)};
}
export function evaluateStaticVector(vector,authorities){
  if(typeof vector.canonical_cbor_hex!=="string"||vector.canonical_cbor_hex.length%2||!/^[0-9a-f]*$/.test(vector.canonical_cbor_hex))return{outcome:"REJECT",reason:"ERR_SCHEMA"};
  return validateObject(Buffer.from(vector.canonical_cbor_hex,"hex"),vector.object_class,vector.fixed_context,authorities);
}
export function verifyStaticFixture(fixture,authorities){
  if(fixture.format_version!==1||fixture.schema_oracle_count!==28||fixture.vectors.length!==35||fixture.object_coverage.length!==18)throw new Error("static fixture structure/count mismatch");
  const covered=new Set(fixture.object_coverage.map(x=>x.object_class));if(covered.size!==18||[...authorities.objectTypes.keys()].some(x=>!covered.has(x)))throw new Error("static object coverage mismatch");
  for(const vector of fixture.vectors){const bytes=Buffer.from(vector.canonical_cbor_hex,"hex");if(sha256(bytes)!==vector.payload_sha256)throw new Error(`${vector.id}: payload digest mismatch`);const actual=evaluateStaticVector(vector,authorities);if(actual.outcome!==vector.expected||actual.reason!==vector.expected_reason)throw new Error(`${vector.id}: static result mismatch: ${actual.outcome}/${actual.reason}`);}
  return fixture.vectors.length;
}
