import concurrent.futures,json,subprocess,sys,time,traceback,shutil
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from scripts.performance.authority import write_loopback_authority
from scripts.performance.authorities import write_authority_set
from scripts.performance.linux_native_pair import verify_index
ROOT=Path(__file__).resolve().parent;PRIVATE=Path('C:/NBSR-build/private-native-control-scale512-a401567d')
BUILD=Path('C:/NBSR-build/linux-current-a401567d');NETWORK='nbsr-native-control-scale512-a401567d'
NAMES={r:'nbsr-native-control-scale512-'+r+'-a401567d' for r in ('source','destination')}
commands=[];created=[];records=[]
def write(n,v):(ROOT/n).write_text(json.dumps(v,indent=2)+'\n')
def call(argv,timeout=60):
 commands.append(argv);write('commands.json',commands)
 return subprocess.check_output(argv,stderr=subprocess.STDOUT,text=True,timeout=timeout)
def wait(paths,processes,label,timeout=120):
 deadline=time.monotonic()+timeout
 while not all(p.exists() for p in paths):
  if any((ROOT/r/(label+'-failed.json')).exists() or (ROOT/r/(label+'-watcher-error.json')).exists() for r in NAMES):raise RuntimeError('observed failure marker')
  if any(p.poll() is not None for p in processes):raise RuntimeError('peer wrapper exited before marker')
  if time.monotonic()>deadline:raise TimeoutError('control deadline')
  time.sleep(.01)
def ready(path,process,label):
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  if process.poll() is not None:raise RuntimeError('destination exited before readiness')
  try:return json.loads(path.read_text())
  except (FileNotFoundError,json.JSONDecodeError):time.sleep(.01)
 raise TimeoutError('readiness deadline')
try:
 assert shutil.disk_usage(ROOT).free>5*1024**3
 (ROOT/'signals').mkdir();call(['docker','network','create','--internal',NETWORK])
 for role,name in NAMES.items():
  (ROOT/role).mkdir()
  call(['docker','run','-d','--name',name,'--network',NETWORK,'--user','0','--entrypoint','sleep','-v',str(ROOT/role)+':/out','-v',str(ROOT)+':/control:ro','-v',str(PRIVATE)+':/fixture','-v',str(BUILD)+':/build:ro','-v','C:/NBSR-build/linux-current-edc0f96d:/old:ro','nbsr-linux-smoke-3644c324:prepared','3600']);created.append(name)
 def prepare(role):
  value=call(['docker','exec',NAMES[role],'python','-B','/control/setup.py'],180)
  (ROOT/role/'setup.log').write_text(value)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(prepare,NAMES))
 info={r:json.loads(call(['docker','inspect',name]))[0] for r,name in NAMES.items()};write('containers-before.json',info)
 ips={r:v['NetworkSettings']['Networks'][NETWORK]['IPAddress'] for r,v in info.items()};assert ips['source']!=ips['destination']
 write('placement.json',dict(addresses=ips,scope='shared WSL host, separate internal namespaces'))
 for repeat in range(1,6):
  for mode in ('local',):
   assert shutil.disk_usage(ROOT).free>5*1024**3
   count=512;label=f'{mode}-512-r{repeat}';print('CONTROL_STORAGE',label,flush=True)
   fixture=PRIVATE/label;fixture.mkdir();write_loopback_authority(fixture/'authority');write_authority_set(fixture/'source',1);shutil.copytree(fixture/'source',fixture/'destination')
   for i in range(count):(fixture/'source'/f'connection-{i}.start').write_text('start\n')
   processes={};handles=[];record=dict(mode=mode,count=count,repeat=repeat,label=label)
   def launch(role):
    argv=['docker','exec','--user','65532',NAMES[role],'python','-B','/control/role.py',role,label,str(count),ips[role],ips['destination' if role=='source' else 'source'],mode]
    commands.append(argv);write('commands.json',commands)
    o=(ROOT/role/(label+'.stdout')).open('x');e=(ROOT/role/(label+'.stderr')).open('x');handles.extend((o,e));processes[role]=subprocess.Popen(argv,stdout=o,stderr=e)
   try:
    launch('destination');r=ready(ROOT/'destination'/label/'ready.json',processes['destination'],label);assert r['endpoint'].split(':')[0]==ips['destination'];launch('source')
    wait([ROOT/r/(label+'-active.json') for r in NAMES],list(processes.values()),label)
    time.sleep(2)
    joins={r:json.loads(call(['docker','exec','--user','65532',NAMES[r],'python','-B','/control/binding.py',label,ips[r]])) for r in NAMES}
    assert len(joins['source']['sockets'])==count and len(joins['destination']['sockets'])==1
    write(label+'-bindings.json',joins)
    for role in ('destination','source'):
     (ROOT/'signals'/(label+'.'+role+'.release')).write_text('release\n')
     wait([ROOT/role/(label+'-released.json')],[processes[role]],label)
    wait([ROOT/'source'/(label+'-acked.json'),ROOT/'destination'/(label+'-report-ready.json')],[processes['destination']],label)
    time.sleep(2);(ROOT/'signals'/(label+'.report-release')).write_text('release\n')
    assert all(p.wait(timeout=30)==0 for p in processes.values())
    results={r:json.loads((ROOT/r/label/'result.json').read_text()) for r in NAMES}
    assert all(v['successful']==count and v['ownership_all_zero'] for v in results.values())
    record.update(status='PASS_FUNCTIONAL',successful=count,results=results)
   except Exception as error:
    record.update(status='FAIL_RETAINED',error=str(error),traceback=traceback.format_exc())
    (ROOT/'signals'/(label+'.cancel')).write_text('cancel\n')
    for p in processes.values():p.wait(timeout=15)
   finally:
    for h in handles:h.close()
   record['exit_codes']={r:p.returncode for r,p in processes.items()}
   record['indexes']={r:verify_index(ROOT/r/label) for r in processes if (ROOT/r/label/'checksums.sha256').exists()}
   record['markers']={r:{ext:len(list((ROOT/r/(label+'-markers')).glob('*.'+ext))) for ext in ('active','failed','release','ack')} for r in processes}
   records.append(record);write('records.json',records);print(label,record['status'],record['markers'],flush=True)
except BaseException as error:
 write('campaign-failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise
finally:
 for name in created:subprocess.run(['docker','stop','--timeout','5',name],check=False)
 write('containers-after.json',{name:json.loads(subprocess.check_output(['docker','inspect','--size',name],text=True))[0] for name in created})
