const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();
function element(){return {textContent:'',className:'',hidden:false,disabled:false,children:[],append(...x){this.children.push(...x)},replaceChildren(){this.children=[]}}}
const context={document:{querySelector(s){if(!elements.has(s))elements.set(s,element());return elements.get(s)},querySelectorAll(){return [...elements.values()].flatMap(e=>e.children).filter(e=>e.tag==='button')},createElement(tag){return Object.assign(element(),{tag})}},location:{hash:''},history:{replaceState(){}},navigator:{clipboard:{writeText:async()=>{}}},crypto:{randomUUID:()=> 'test-id'},setInterval:()=>1,clearInterval(){},setTimeout,clearTimeout,AbortController,console,fetch:async()=>{throw Error('network lost')}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
(async()=>{
 assert.equal(vm.runInContext('typeof journeyFor',context),'function');
 for(const scenario of ['allowed_service_a','unknown_service','stale_authority','digest_mismatch','expired_mapping','shared_ip_isolation']){
  context.item={scenario,status:'PASS',scenario_outcome:'PASS',cleanup:'CLEAN',errors:[]};
  assert.equal(vm.runInContext('journeyFor(item).verified',context),true);
  for(const state of ['RUNNING','FAIL','INCOMPLETE']){context.item.status=state;assert.equal(vm.runInContext('journeyFor(item).verified',context),false)}
  context.item.status='PASS';context.item.cleanup='UNCONFIRMED';assert.equal(vm.runInContext('journeyFor(item).verified',context),false);
 }
 context.item={scenario:'invented',status:'PASS',scenario_outcome:'PASS',cleanup:'CLEAN',errors:[]};assert.equal(vm.runInContext('journeyFor(item).verified',context),false);
 vm.runInContext("connectionState='connected';lastState={running:false,blocked:false,scenarios:[{id:'stale_authority',label:'Stale authority',kind:'REGRESSION'}],current:null};render(lastState)",context);
 const button=elements.get('#scenarios').children[0].children[2];await button.onclick();
 assert.match(elements.get('#connection').textContent,/Disconnected/);assert.equal(elements.get('#cancel').disabled,true);
 assert.ok(elements.get('#scenarios').children.every(row=>row.children[2].disabled));
 assert.match(elements.get('#result').textContent,/unknown|No verified/i);
 context.fetch=async()=>({ok:true,json:async()=>({scenarios:[],current:{status:'RUNNING'}})});
 await vm.runInContext('refresh()',context);assert.match(elements.get('#connection').textContent,/Disconnected/);

 // Real refresh/render functions with explicitly controlled response order.
 const deferred=[];context.fetch=()=>new Promise(resolve=>deferred.push(resolve));
 vm.runInContext("connectionState='connected'",context);
 const older=vm.runInContext('refresh()',context),newer=vm.runInContext('refresh()',context);
 const stateFor=label=>({platform_validation:label,running:false,blocked:false,scenarios:[],current:null});
 deferred[1]({ok:true,json:async()=>stateFor('newer')});await newer;
 assert.equal(elements.get('#platform').textContent,'newer');
 deferred[0]({ok:true,json:async()=>stateFor('older')});await older;
 assert.equal(elements.get('#platform').textContent,'newer','older response must not overwrite newer evidence');

 // An earlier completion may render while a later request is pending (no starvation).
 const first=vm.runInContext('refresh()',context),second=vm.runInContext('refresh()',context);
 deferred[2]({ok:true,json:async()=>stateFor('first completed')});await first;
 assert.equal(elements.get('#platform').textContent,'first completed');
 deferred[3]({ok:true,json:async()=>stateFor('second completed')});await second;
 assert.equal(elements.get('#platform').textContent,'second completed');
 // A response still cannot resurrect the stopped session.
 const late=vm.runInContext('refresh()',context);vm.runInContext("connectionState='stopped'",context);
 deferred[4]({ok:true,json:async()=>stateFor('must not render')});await late;
 assert.equal(elements.get('#platform').textContent,'second completed');
 console.log('PASS: six evidence gates, unknown scenario, failed POST, disabled actions, late-response guard, ordered overlapping responses, no starvation, stopped-session guard');
})().catch(e=>{console.error(e);process.exitCode=1});
