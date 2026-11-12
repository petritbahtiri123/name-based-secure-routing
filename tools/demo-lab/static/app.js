'use strict';
let token = null, busy = false, connectionState = 'connecting', timer = null, lastState = null;
const connection = document.querySelector('#connection');
const result = document.querySelector('#result');
const command = document.querySelector('#command');
const descriptions = {
 allowed_service_a: {kind:'LIVE RESULT', steps:['Named Service A request (schematic)', 'Authority / Go–Rust route (not individually traced)', 'Application response'], proof:'Exact application body received; destination status PASS and backend_requests=1.', source:'nbsr_demo_lab/worker.py; evidence.py: application.json + destination.json', limit:'Intermediate hops and authorization timings are not independently measured by this receipt.'},
 unknown_service: {kind:'FIXTURE ASSERTION', steps:['Unknown presentation name', 'Service lookup boundary', 'Secure route not opened'], proof:'Unknown service fails closed: zero recorded routes and no payload, even though CONNECT returns HTTP 200.',source:'demo/internal/client/task6_matrix_test.go: TestTask6UnknownServiceDeniedBeforeSecureRoute',limit:'Fixture regression; no live Rust destination or network attack.'},
 stale_authority: {kind:'FIXTURE ASSERTION', steps:['Fixture with stale generation', 'Authority validation: REJECT', 'Transport / application blocked'],proof:'ErrStaleGeneration; transport calls=0, application opens=0, payload writes=0.',source:'demo/internal/client/task6_matrix_test.go: TestTask6AuthorityDeniedBeforeTransportOrApplication',limit:'Counters are assertions inside the named test, not browser telemetry.'},
 digest_mismatch: {kind:'FIXTURE ASSERTION', steps:['Fixture with mismatched service digest', 'Service binding validation: REJECT', 'Transport / application blocked'],proof:'ErrBindingMismatch; transport calls=0, application opens=0, payload writes=0.',source:'demo/internal/client/task6_matrix_test.go: TestTask6ServiceDigestMismatchBeforeTransportOrApplication',limit:'Counters are assertions inside the named test, not browser telemetry.'},
 expired_mapping: {kind:'FIXTURE ASSERTION', steps:['Fake clock at exact expiry', 'Mapping lookup / acquire: REJECT', 'Expired Mapping unavailable'],proof:'LookupMapping and AcquireMapping return ErrExpiredMapping. Entry remains stored: this test does not prove implicit cleanup.',source:'internal/corestate/mapping_test.go: TestMappingExactExpiryCannotBeReturnedOrAcquired',limit:'Store-level test; transport and application traffic are not measured.'},
 shared_ip_isolation: {kind:'FIXTURE ASSERTION', steps:['Two services on shared synthetic IP / port', 'Flow-to-service correlation', 'Distinct recorded routes'],proof:'Recorded routes retain storage.service / payments.service identities and different service digests.',source:'internal/resolution/integration_test.go: TestSharedSyntheticIPCorrelatesSamePortServicesEndToEnd',limit:'Fixture route opener; no live transport isolation or throughput claim.'}
};
function journeyFor(item) {
 const spec = item && Object.hasOwn(descriptions,item.scenario) && descriptions[item.scenario];
 return {spec, verified:!!spec && item.status==='PASS' && item.scenario_outcome==='PASS' && item.cleanup==='CLEAN' && Array.isArray(item.errors) && item.errors.length===0};
}
function renderJourney(item) {
 const target=document.querySelector('#journey');target.replaceChildren();
 const {spec,verified}=journeyFor(item);
 if(!spec){target.textContent='Choose and run a scenario to see its evidence boundary.';return;}
 const label=document.createElement('p'); label.textContent=spec.kind+' — '+(verified?'verified completed run':'expected path only; not proven for this attempt');
 const steps=document.createElement('ol');steps.className='journey-steps';
 spec.steps.forEach((text,index)=>{const step=document.createElement('li');step.textContent=text;step.className=verified&&index>0?'asserted':'';if(item.scenario==='allowed_service_a'&&index===1)step.className='';steps.append(step)});
 const proof=document.createElement('p');proof.textContent=(verified?'Verified assertion: ':'Expected assertion (unverified): ')+spec.proof;
 const source=document.createElement('p');source.className='journey-source';source.textContent='Source: '+spec.source;
 const limit=document.createElement('p');limit.textContent=spec.limit+' This is an explanation of evidence, not an animated event trace.';
 target.append(label,steps,proof,source,limit);
}
function disableActions(){document.querySelectorAll('#scenarios button').forEach(b=>b.disabled=true);document.querySelector('#cancel').disabled=true;document.querySelector('#stop').disabled=true;}
function disconnect(){
 if(connectionState==='stopped')return;
 connectionState='disconnected';busy=false;clearInterval(timer);disableActions();
 connection.textContent='Disconnected — current run status is unknown. No request will be retried. Last received evidence is retained below. Reconcile the server/owned run in the terminal, then launch a new private session; do not just refresh this tab.';
 document.querySelector('#freshness').textContent='Historical snapshot only — no current server confirmation.';
 if(!lastState||!lastState.current)result.textContent='No verified result received. Whether the submitted request ran is unknown.';
}
async function api(path,body){
 const headers=token?{Authorization:`Bearer ${token}`}:{},controller=new AbortController();
 const options={headers,cache:'no-store',signal:controller.signal};
 if(body!==undefined){options.method='POST';headers['Content-Type']='application/json';headers['X-NBSR-Action']='demo';options.body=JSON.stringify(body)}
 const deadline=setTimeout(()=>controller.abort(),15000);
 try{const response=await fetch(path,options);const data=await response.json();if(!response.ok){const error=new Error(data.error||`Request failed (${response.status})`);error.status=response.status;throw error;}return data;}
 catch(error){if(!error.status||error.status===401)disconnect();throw error;}
 finally{clearTimeout(deadline)}
}
function render(state){
 lastState=state;document.querySelector('#platform').textContent=state.platform_validation||'';
 const list=document.querySelector('#scenarios');list.replaceChildren();
 for(const scenario of state.scenarios){
  const row=document.createElement('div');row.className='scenario';
  const title=document.createElement('span');title.textContent=scenario.label;
  const kind=document.createElement('small');kind.textContent=scenario.kind;
  const button=document.createElement('button');button.textContent=scenario.disabled?'Platform support pending':'Run scenario';
  button.disabled=scenario.disabled||state.running||state.blocked||busy||connectionState!=='connected';
  button.onclick=async()=>{
   if(busy||connectionState!=='connected')return;busy=true;render(lastState);
   connection.textContent='Submitting '+scenario.label+' — awaiting server admission. This is not yet a running or successful test.';
   try{await api('/api/start',{scenario:scenario.id,request_id:crypto.randomUUID()});}
   catch(error){if(connectionState==='connected')connection.textContent=error.message;}
   finally{busy=false;if(connectionState==='connected'){try{await refresh()}catch(_){/* api records disconnection */}}}
  };
  row.append(title,kind,button);list.append(row);
 }
 document.querySelector('#cancel').disabled=!state.running||connectionState!=='connected';document.querySelector('#stop').disabled=connectionState!=='connected';
 if(state.current){const item=state.current;result.textContent=`${item.run_id}\nScenario: ${item.scenario}\nOverall: ${item.status}\nObserved scenario: ${item.scenario_outcome||'pending'}\nCleanup: ${item.cleanup}\n${(item.errors||[]).join('\n')}`;result.className=journeyFor(item).verified?'verified':'';command.textContent=item.verify_command||'';document.querySelector('#copy').hidden=!item.verify_command;renderJourney(item);}
 document.querySelector('#freshness').textContent='Last server response received '+new Date().toLocaleTimeString()+'. Steps below are schematic; no per-hop progress is measured.';
 if(state.blocked&&!state.running)connection.textContent='New runs blocked: cleanup needs operator reconciliation. No automatic retry.';
 else if(!busy)connection.textContent=state.running?'Run admitted. Waiting for verified evidence and cleanup.':'Private local session connected.';
}
async function refresh(){if(connectionState!=='connected')return;const state=await api('/api/status');if(connectionState==='connected')render(state);}
document.querySelector('#copy').onclick=async()=>{try{await navigator.clipboard.writeText(command.textContent);document.querySelector('#copy-status').textContent='Command copied.';}catch(_){document.querySelector('#copy-status').textContent='Clipboard unavailable. Select and copy the displayed command manually.';}};
document.querySelector('#cancel').onclick=async()=>{if(connectionState!=='connected')return;try{await api('/api/cancel',{});connection.textContent='Cancellation requested; waiting for confirmed cleanup.';}catch(error){if(connectionState==='connected')connection.textContent=error.message;}};
document.querySelector('#stop').onclick=async()=>{if(connectionState!=='connected')return;try{await api('/api/shutdown',{});connectionState='stopped';clearInterval(timer);disableActions();connection.textContent='Shutdown requested. Session closed; confirm owned cleanup in terminal. Last evidence remains below.';document.querySelector('#freshness').textContent='Session closed — retained evidence only.';}catch(error){if(connectionState==='connected')connection.textContent=error.message;}};
(async()=>{const secret=location.hash.slice(1);history.replaceState(null,'','/');try{if(!secret)throw Error('Open the private one-use link from the launcher. Refresh cannot restore a session.');const value=await api('/api/bootstrap',{secret});token=value.token;connectionState='connected';await refresh();timer=setInterval(()=>refresh().catch(()=>{}),1500);}catch(error){if(connectionState!=='disconnected'){connection.textContent=error.message;disableActions();}}})();
