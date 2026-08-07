import { createHash } from "node:crypto";
import { decodeCanonical, encodeCanonical } from "./cbor.js";
import { publicKeyFromRaw, verifySign1 } from "./cose.js";
const PUBLIC_KEY=publicKeyFromRaw(Buffer.from("43046bfe4092b3e94994eada15dcc20d8aaa07b658fd3954eb8e0efb8bdca5de","hex"));
const sha=(...parts)=>createHash("sha256").update(Buffer.concat(parts)).digest();
const result=(outcome,reason)=>({outcome,reason,enforcement:outcome==="ACCEPT"?"NONE":"DENY_NEW_USE",mutation:outcome==="ACCEPT"});
function strictHex(value,bytes){return typeof value==="string"&&value.length===bytes*2&&/^[0-9a-f]+$/.test(value);}
export function evaluateCapabilityVector(v){
  try{
    for(const field of ["offer_cbor_hex","offer_sign1_hex","selection_cbor_hex","selection_sign1_hex","signed_threshold_signature_context_hex","threshold_evidence_sign1_hex"])if(typeof v[field]!=="string"||v[field].length%2||!/^[0-9a-f]+$/.test(v[field]))return result("REJECT","ERR_SCHEMA");
    const offerBytes=Buffer.from(v.offer_cbor_hex,"hex"),selectionBytes=Buffer.from(v.selection_cbor_hex,"hex"),offer=decodeCanonical(offerBytes),selection=decodeCanonical(selectionBytes);
    if(!(offer instanceof Map)||[...offer.keys()].join(",")!=="1,2"||!(selection instanceof Map)||[...selection.keys()].join(",")!=="1,2,3,4,5")return result("REJECT","ERR_SCHEMA");
    verifySign1(Buffer.from(v.offer_sign1_hex,"hex"),PUBLIC_KEY,offerBytes);verifySign1(Buffer.from(v.selection_sign1_hex,"hex"),PUBLIC_KEY,selectionBytes);
    const offered=offer.get(1),agreed=selection.get(1);if(!Array.isArray(offered)||!Array.isArray(agreed)||offered.some(x=>typeof x!=="number"||!Number.isSafeInteger(x))||agreed.some(x=>typeof x!=="number"||!Number.isSafeInteger(x))||new Set(offered).size!==offered.length||new Set(agreed).size!==agreed.length)return result("REJECT","ERR_SCHEMA");
    if(selection.get(2)!=="core-v0.2"||selection.get(3)!=="federation-v0.1"||selection.get(4)!=="federation-v0.1-development")return result("REJECT","ERR_VERSION");
    if(!Buffer.isBuffer(offer.get(2))||offer.get(2).length!==64||typeof selection.get(5)!=="string"||selection.get(5)!==offer.get(2).toString("ascii")||!strictHex(selection.get(5),32))return result("REJECT","ERR_REPLAY");
    if(offered.includes(6)&&!agreed.includes(6))return result("REJECT","ERR_DOWNGRADE");
    if(!agreed.includes(6))return result("REJECT","ERR_UNSUPPORTED_CRITICAL");
    if(agreed.some(x=>![1,6].includes(x)))return result("REJECT","ERR_UNSUPPORTED_CRITICAL");
    const capDigest=sha(encodeCanonical(agreed)),transcript=sha(offerBytes,selectionBytes),session=Buffer.from(selection.get(5),"hex");
    if(!strictHex(v.capability_set_digest,32)||!capDigest.equals(Buffer.from(v.capability_set_digest,"hex")))return result("REJECT","ERR_DOWNGRADE");
    if(!strictHex(v.authenticated_transcript_digest,32)||!transcript.equals(Buffer.from(v.authenticated_transcript_digest,"hex")))return result("REJECT","ERR_REPLAY");
    if(v.authenticated_session_digest!==selection.get(5))return result("REJECT","ERR_REPLAY");
    const context=sha(capDigest,transcript,session,Buffer.from("threshold-evidence-v1"));
    const evidence=verifySign1(Buffer.from(v.threshold_evidence_sign1_hex,"hex"),PUBLIC_KEY);
    if(!evidence.payload.equals(context)||v.signed_threshold_signature_context_hex!==context.toString("hex")||v.threshold_signature_context_digest!==context.toString("hex"))return result("REJECT","ERR_REPLAY");
    return result("ACCEPT","NONE");
  }catch(error){return result("REJECT",/signature invalid/.test(error.message)?"ERR_SIGNATURE_INVALID":"ERR_SCHEMA");}
}
export function verifyCapabilityFixture(fixture){
  if(fixture.format_version!==1||fixture.required_capability?.id!==6||fixture.required_capability?.name!=="THRESHOLD_EVIDENCE"||fixture.vectors.length!==12)throw new Error("capability fixture structure/count mismatch");
  for(const vector of fixture.vectors){const actual=evaluateCapabilityVector(vector);if(actual.outcome!==vector.expected_outcome||actual.reason!==vector.expected_reason||actual.enforcement!==vector.enforcement||actual.mutation!==vector.mutation)throw new Error(`${vector.id}: capability mismatch: ${actual.outcome}/${actual.reason}`);}
  return fixture.vectors.length;
}
