import { createHash } from "node:crypto";
function stable(v){if(Array.isArray(v))return`[${v.map(stable).join(",")}]`;if(v&&typeof v==="object")return`{${Object.keys(v).sort().map(k=>`${JSON.stringify(k)}:${stable(v[k])}`).join(",")}}`;return JSON.stringify(v);}
const hash=(v)=>createHash("sha256").update(stable(v),"ascii").digest("hex");
function initial(){return{accepted:[],pending:[],quarantine:[],replay:[],static:[{activated:1899999000,digest:"50".repeat(32),expires:1900001000,operators:["41".repeat(32),"42".repeat(32)],scope:"static:route",service:"53".repeat(32),triggers:["control-outage"]}],tombstones:[]};}
export function stateDigest(state){return hash(state);}
function acceptedValue(e){return{dependencies:e.dependencies,digest:e.object_digest,fresh:e.source_fresh_at,generation:e.generation,key:e.key,kind:e.object_kind,operator:e.operator_id,peer:e.peer_operator_id,sequence:e.sequence,service:e.service_id,terminal:e.terminal,valid_until:e.valid_until};}
function result(outcome,reason,enforcement="NONE",mutation=false,evidence=[]){return{outcome,reason,enforcement,mutation,evidence};}
const FAILURE_ORDER=["ERR_RESOURCE_LIMIT","ERR_NON_CANONICAL","ERR_SIGNATURE_INVALID","ERR_IDENTITY","ERR_SCHEMA","ERR_AUTHORITY","ERR_ROLLBACK","ERR_REVOKED","ERR_TRANSPARENCY","ERR_FRESHNESS","ERR_LOCAL_POLICY","ERR_CHECKPOINT","ERR_RECOVERY_INVALID","ERR_DOWNGRADE","ERR_REPLAY"];
function validateEvent(e,now){
  const fields=["authority_expansion","compromised","dependencies","generation","key","object_digest","object_kind","operation","operator_id","outage_trigger","peer_operator_id","previous_digest","recovery_of","replay_digest","requires_prior_authority","sequence","service_id","source_fresh_at","static_policy_digest","terminal","valid_until","validation_failures"];
  const actual=Object.keys(e).sort();if(actual.length!==fields.length||actual.some((key,i)=>key!==[...fields].sort()[i]))throw new Error("unexpected state event fields");
  const ints=[e.generation,e.sequence,now];for(const key of ["source_fresh_at","valid_until"])if(e[key]!==null)ints.push(e[key]);if(ints.some(v=>!Number.isSafeInteger(v)||v<0))throw new Error("unsafe state event integer");
  for(const key of ["key","object_digest","object_kind","operation","operator_id","peer_operator_id","service_id"])if(typeof e[key]!=="string")throw new Error(`invalid state event ${key}`);
  if(!Array.isArray(e.dependencies)||e.dependencies.some(v=>typeof v!=="string")||!Array.isArray(e.validation_failures)||e.validation_failures.some(v=>!FAILURE_ORDER.includes(v)))throw new Error("invalid state event arrays");
  for(const key of ["authority_expansion","compromised","requires_prior_authority","terminal"])if(typeof e[key]!=="boolean")throw new Error(`invalid state event ${key}`);
  for(const key of ["outage_trigger","previous_digest","recovery_of","replay_digest","static_policy_digest"])if(e[key]!==null&&typeof e[key]!=="string")throw new Error(`invalid state event ${key}`);
  const hex32=/^[0-9a-f]{64}$/;for(const key of ["object_digest","operator_id","peer_operator_id","service_id"])if(!hex32.test(e[key]))throw new Error(`invalid state event ${key} hex`);
  if(e.dependencies.some(v=>!hex32.test(v)))throw new Error("invalid state event dependency hex");for(const key of ["previous_digest","replay_digest","static_policy_digest"])if(e[key]!==null&&!hex32.test(e[key]))throw new Error(`invalid state event ${key} hex`);
}
function decide(state,e,now){
  validateEvent(e,now);
  if(e.validation_failures.length){const reason=[...e.validation_failures].sort((a,b)=>FAILURE_ORDER.indexOf(a)-FAILURE_ORDER.indexOf(b))[0];return result("REJECT",reason,"DENY_NEW_USE");}
  if(e.compromised)return result("REJECT","ERR_REVOKED","TERMINATE_ACTIVE_USE");
  const acceptedDigests=new Set(state.accepted.map(x=>x.digest));
  if(e.dependencies.some(d=>!acceptedDigests.has(d)))return result("REJECT","ERR_CONTINUITY","DENY_NEW_USE");
  if(e.requires_prior_authority&&state.accepted.length===0)return result("REJECT","ERR_AUTHORITY","DENY_NEW_USE");
  if(e.recovery_of&&!state.tombstones.includes(e.recovery_of)&&!state.quarantine.some(([key])=>key===e.recovery_of))return result("REJECT","ERR_RECOVERY_INVALID","DENY_NEW_USE");
  if(e.replay_digest&&state.replay.some(([d])=>d===e.replay_digest))return result("REJECT","ERR_REPLAY","DENY_NEW_USE");
  if(e.operation==="existing_context"){if(e.authority_expansion)return result("REJECT","ERR_LOCAL_POLICY","DENY_NEW_USE");return now-e.source_fresh_at<=900?result("RESTRICTED","ERR_FRESHNESS","REAUTHENTICATE"):result("REJECT","ERR_OUTAGE_POLICY","DRAIN");}
  if(e.operation==="static_recovery"){
    const p=state.static.find(x=>x.digest===e.static_policy_digest&&x.scope===e.key&&x.service===e.service_id&&x.operators.includes(e.operator_id)&&x.operators.includes(e.peer_operator_id)&&x.triggers.includes(e.outage_trigger));
    return p&&now>=p.activated&&now<=p.expires?result("RESTRICTED","ERR_OUTAGE_POLICY","DENY_NEW_USE"):result("REJECT","ERR_RECOVERY_INVALID","DENY_NEW_USE");
  }
  const old=state.accepted.find(x=>x.key===e.key);
  if(e.previous_digest!==null&&(!old||e.previous_digest!==old.digest))return result("REJECT","ERR_CONTINUITY","DENY_NEW_USE");
  if(!old&&(e.generation!==1||e.sequence!==1))return result("REJECT","ERR_ROLLBACK","DENY_NEW_USE");
  if(old){
    if(e.generation<old.generation||(e.generation===old.generation&&e.sequence<old.sequence))return result("REJECT","ERR_ROLLBACK","DENY_NEW_USE");
    if(e.generation===old.generation&&e.sequence===old.sequence){
      if(e.object_digest===old.digest)return result("ACCEPT","NONE");
      const q=state.quarantine.find(x=>x[0]===e.key);if(q)q[1]=[...new Set([...q[1],e.object_digest])].sort();else state.quarantine.push([e.key,[old.digest,e.object_digest].sort()]);state.quarantine.sort();
      return result("QUARANTINE","ERR_EQUIVOCATION","DENY_NEW_USE",true,[]);
    }
  }
  if(state.tombstones.includes(e.key))return result("REJECT","ERR_TERMINAL_STATE","DENY_NEW_USE");
  state.accepted=state.accepted.filter(x=>x.key!==e.key);state.accepted.push(acceptedValue(e));state.accepted.sort((a,b)=>a.key.localeCompare(b.key));
  if(e.terminal&&!state.tombstones.includes(e.key))state.tombstones.push(e.key);state.tombstones.sort();
  if(e.replay_digest)state.replay.push([e.replay_digest,now]);state.replay.sort();
  return result("ACCEPT","NONE","NONE",true,[e.object_digest]);
}
export function verifyStateFixture(fixture){
  if(fixture.format_version!==1||fixture.event_vectors.length!==43||fixture.scenarios.length!==43||fixture.task6_oracle.length!==4)throw new Error("state fixture structure/count mismatch");
  const state=initial();if(stateDigest(state)!==fixture.scenarios[0].input.pre_state)throw new Error("initial state digest mismatch");
  for(let i=0;i<43;i++){
    const wrapped=fixture.event_vectors[i],scenario=fixture.scenarios[i];
    if(wrapped.id!==scenario.input.vector_id||stateDigest(state)!==scenario.input.pre_state)throw new Error(`${scenario.id}: pre-state mismatch`);
    const actual=decide(state,wrapped.federation_event,wrapped.evaluation_time),digest=stateDigest(state);
    if(actual.outcome!==scenario.expected_result||actual.reason!==scenario.expected_reason||actual.enforcement!==scenario.enforcement||actual.mutation!==scenario.mutation||digest!==scenario.resulting_state_digest)throw new Error(`${scenario.id}: state result mismatch ${actual.outcome}/${actual.reason}/${actual.enforcement}/${actual.mutation}/${digest}`);
    if(stable(actual.evidence)!==stable(scenario.emitted_evidence))throw new Error(`${scenario.id}: evidence mismatch`);
  }return fixture.scenarios.length;
}
