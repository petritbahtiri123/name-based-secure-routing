import concurrent.futures,json,subprocess,sys,time,traceback,shutil
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from scripts.performance.authority import write_loopback_authority
from scripts.performance.authorities import write_authority_set
from scripts.run_b3_session_lifecycle import ownership_cleanup
from scripts.performance.linux_native_pair import verify_index
ROOT=Path(__file__).resolve().parent;PRIVATE=Path('C:/NBSR-build/private-native-lifecycle-b6cf5e56')
BUILD=Path('C:/NBSR-build/linux-current-b6cf5e56');NETWORK='nbsr-native-lifecycle-b6cf5e56'
NAMES={r:'nbsr-native-lifecycle-'+r+'-b6cf5e56' for r in ('source','destination')}
commands=[];created=[];records=[]
def write(n,v):(ROOT/n).write_text(json.dumps(v,indent=2)+'\n')
def call(argv,timeout=60):
 commands.append(argv);write('commands.json',commands)
 return subprocess.check_output(argv,stderr=subprocess.STDOUT,text=True,timeout=timeout)
def wait_files(paths,procs,timeout=60):
 deadline=time.monotonic()+timeout
 while not all(p.exists() for p in paths):
  if any(p.poll() is not None for p in procs):raise RuntimeError('peer wrapper exited before marker')
  if time.monotonic()>deadline:raise TimeoutError('native lifecycle marker deadline')
  time.sleep(.01)
def json_ready(path,procs):
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  if any(p.poll() is not None for p in procs):raise RuntimeError('peer wrapper exited before JSON readiness')
  try:return json.loads(path.read_text())
  except (FileNotFoundError,json.JSONDecodeError):time.sleep(.01)
 raise TimeoutError('native readiness JSON deadline')
try:
 assert shutil.disk_usage(ROOT).free>5*1024**3
 call(['docker','network','create','--internal',NETWORK])
 for role,name in NAMES.items():
  (ROOT/role).mkdir()
  call(['docker','run','-d','--name',name,'--network',NETWORK,'--user','0','--entrypoint','sleep','-v',str(ROOT/role)+':/out','-v',str(ROOT)+':/control:ro','-v',str(PRIVATE)+':/fixture','-v',str(BUILD)+':/build:ro','-v','C:/NBSR-build/linux-current-edc0f96d:/old:ro','nbsr-linux-smoke-3644c324:prepared','1800']);created.append(name)
 def prepare(role):
  value=call(['docker','exec',NAMES[role],'python','-B','/control/setup.py'],180)
  (ROOT/role/'setup.log').write_text(value)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(prepare,NAMES))
 info={role:json.loads(call(['docker','inspect',name]))[0] for role,name in NAMES.items()};write('containers-before.json',info)
 ips={r:v['NetworkSettings']['Networks'][NETWORK]['IPAddress'] for r,v in info.items()};assert ips['source']!=ips['destination']
 write('placement.json',dict(addresses=ips,scope='shared WSL host; two internal Docker network namespaces; not independent physical servers'))
 for count in (16,32,64,128):
  for repeat in range(1,6):
   label=f'bundles-{count}-r{repeat}';print('NATIVE_LIFECYCLE',label,flush=True)
   fixture=PRIVATE/label;fixture.mkdir();lifecycle=fixture/'lifecycle'
   write_loopback_authority(fixture/'authority');write_authority_set(lifecycle,1)
   for i in range(count):(lifecycle/f'connection-{i}.start').write_text('start\n')
   processes={};handles=[]
   def launch(role):
    argv=['docker','exec','--user','65532',NAMES[role],'python','-B','/control/role.py',role,label,str(count),ips[role],ips['destination' if role=='source' else 'source']]
    commands.append(argv);write('commands.json',commands)
    o=(ROOT/role/(label+'.stdout')).open('x');e=(ROOT/role/(label+'.stderr')).open('x');handles.extend((o,e))
    processes[role]=subprocess.Popen(argv,stdout=o,stderr=e)
   try:
    launch('destination');ready=json_ready(fixture/'ready.json',list(processes.values()));assert ready['endpoint'].split(':')[0]==ips['destination']
    launch('source')
    wait_files([lifecycle/f'connection-{i}.active' for i in range(count)]+[lifecycle/f'destination-{i}.active' for i in range(count)],list(processes.values()),120)
    # Preserve the existing two-second active interval before release.
    active_started=time.monotonic_ns();time.sleep(2)
    joins={role:json.loads(call(['docker','exec','--user','65532',NAMES[role],'python','-B','/control/binding.py',label,ips[role]])) for role in NAMES}
    assert len(joins['source']['sockets'])==count and len(joins['destination']['sockets'])==1
    snapshots=[json.loads((lifecycle/f'destination-{i}.active').read_text()) for i in range(count)]
    write(label+'-active.json',dict(active_started_ns=active_started,destination_snapshots=snapshots,bindings=joins))
    for i in range(count):(lifecycle/f'connection-{i}.release').write_text('release\n')
    wait_files([lifecycle/f'connection-{i}.ack' for i in range(count)],[],60)
    wait_files([lifecycle/'destination.report-ready'],[processes['destination']],120)
    time.sleep(2)
    (lifecycle/'destination.report-release').write_text('release\n')
    assert processes['source'].wait(timeout=30)==0
    assert processes['destination'].wait(timeout=30)==0
    src,dst=ROOT/'source'/label,ROOT/'destination'/label
    verify_index(src);verify_index(dst)
    outputs=[json.loads(line) for line in (src/'stdout').read_text().splitlines() if line.strip()]
    success=[r for r in outputs if r.get('success') is True]
    assert len(success)==count and all(r.get('bytes_received')==r.get('bytes_transmitted')==1024 for r in success)
    final=json.loads((dst/'diagnostics.ndjson').read_text().splitlines()[-1])
    cleanup=ownership_cleanup('rust-rust',final,outputs,source_count=1);assert cleanup['all_zero']
    server=json.loads((dst/'server-result.json').read_text());assert server['status']=='PASS' and server['connections']==count and len(server['samples'])==count
    assert not list(lifecycle.glob('*.failed'))
    record=dict(count=count,repeat=repeat,status='PASS_NATIVE_MATERIALIZED_BUNDLES',successful=count,cleanup=cleanup,source_index=verify_index(src),destination_index=verify_index(dst),source_socket_count=len(joins['source']['sockets']),destination_socket_count=len(joins['destination']['sockets']),handshake_ns=[r['transport_handshake_ns'] for r in success],timing='DIAGNOSTIC_ONLY',capacity='NOT_PROVEN')
    records.append(record);write('records.json',records)
   finally:
    for h in handles:h.close()
except BaseException as error:
 write('failure.json',dict(error=str(error),traceback=traceback.format_exc(),replacement=False));raise
finally:
 for name in created:subprocess.run(['docker','stop','--timeout','5',name],check=False)
 write('containers-after.json',{name:json.loads(subprocess.check_output(['docker','inspect','--size',name],text=True))[0] for name in created})
