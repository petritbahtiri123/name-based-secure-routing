import { decodeCanonical, encodeCanonical } from "./cbor.js";
import { evaluateCapabilityVector } from "./capability.js";
import { publicKeyFromRaw, verifySign1 } from "./cose.js";
import { verifyStateFixture } from "./state.js";
import { evaluateThresholdVector } from "./threshold.js";
const PUBLIC_KEY=publicKeyFromRaw(Buffer.from("43046bfe4092b3e94994eada15dcc20d8aaa07b658fd3954eb8e0efb8bdca5de","hex"));
function mustFail(fn,label,pattern=null){try{fn();}catch(error){if(pattern&&!pattern.test(error.message))throw new Error(`${label}: wrong failure ${error.message}`);return 1;}throw new Error(`mutation was accepted: ${label}`);}
function mustDecision(actual,outcome,reason,label){if(actual.outcome!==outcome||actual.reason!==reason)throw new Error(`${label}: got ${actual.outcome}/${actual.reason}`);return 1;}
const opts={maxBytes:65_536,maxDepth:8,maxArrayItems:256,maxMapPairs:128,maxStringBytes:4096};
function mutatedThreshold(vector,mutate){const root=decodeCanonical(Buffer.from(vector.canonical_cbor_hex,"hex"),opts);mutate(root);return{...vector,canonical_cbor_hex:encodeCanonical(root).toString("hex"),name:"renamed",expected_decision:"ACCEPT",expected_reason:"NONE"};}
export async function runMutationChecks(fixtures,authorities){let count=0;
  const signed=Buffer.from(fixtures.signed.vectors[0].cose_sign1_hex,"hex");let changed=Buffer.from(signed);changed[Math.floor(changed.length/2)]^=1;count+=mustFail(()=>verifySign1(changed,PUBLIC_KEY),"signed payload byte");changed=Buffer.from(signed);changed[changed.length-1]^=1;count+=mustFail(()=>verifySign1(changed,PUBLIC_KEY),"COSE signature byte",/signature invalid/);
  const cap=fixtures.capability.vectors[0],wrongSet={...cap,capability_set_digest:"00".repeat(32),case:"renamed",expected_outcome:"ACCEPT"};count+=mustDecision(evaluateCapabilityVector(wrongSet),"REJECT","ERR_DOWNGRADE","capability 6 binding");
  const wrongSession={...cap,authenticated_transcript_digest:"11".repeat(32),case:"renamed",expected_outcome:"ACCEPT"};count+=mustDecision(evaluateCapabilityVector(wrongSession),"REJECT","ERR_REPLAY","session transcript");
  const base=fixtures.threshold.vectors.find(v=>v.id==="threshold-002-valid-witness-2-of-3");
  const reordered=mutatedThreshold(base,root=>root.get(9)[0].get(2).reverse());count+=mustDecision(evaluateThresholdVector(reordered,authorities),"REJECT","ERR_AUTHORITY","signer reorder");
  const duplicate=mutatedThreshold(base,root=>{const s=root.get(9)[0].get(2);s[1]=s[0];});count+=mustDecision(evaluateThresholdVector(duplicate,authorities),"REJECT","ERR_AUTHORITY","duplicate signer");
  const digest=mutatedThreshold(base,root=>{const d=Buffer.from(root.get(4));d[0]^=1;root.set(4,d);});count+=mustDecision(evaluateThresholdVector(digest,authorities),"REJECT","ERR_SIGNATURE_INVALID","threshold payload digest");
  const state=structuredClone(fixtures.state);state.event_vectors[0].federation_event.generation=2;count+=mustFail(()=>verifyStateFixture(state),"generation change",/ERR_ROLLBACK/);
  count+=mustFail(()=>decodeCanonical(Buffer.from("a202000100","hex")),"noncanonical CBOR map",/map key order/);
  return count;
}
