import json,os,signal,subprocess,sys,time
from pathlib import Path
os.chdir('/tmp/source');sys.path.insert(0,'/tmp/source')
from scripts.performance.authority import write_loopback_authority
from scripts.performance.authorities import write_authority_set
from scripts.performance.linux_loopback import parse_proc_stat
from scripts.performance.linux_socket_ownership import snapshot
from scripts.performance.linux_native_pair import verify_index
from scripts.performance.linux_b5_placement import seal_output
role,address,remote=sys.argv[1:];root=Path('/tmp/cancel-native-output');root.mkdir()
records=[]
for repeat in range(1,4):
 private=Path('/tmp/cancel-native-private')/str(repeat);private.mkdir(parents=True)
 authority=private/'authority';lifecycle=private/'lifecycle';write_loopback_authority(authority);write_authority_set(lifecycle,1)
 if role=='source':
  for i in range(16):(lifecycle/f'connection-{i}.start').write_text('start\n')
 output=root/('repeat-'+str(repeat))
 argv=[sys.executable,'-B','-m','scripts.performance.linux_native_lifecycle','--role',role,'--binaries','/tmp/binaries','--build-manifest','/build/build-manifest.json','--authority',str(authority),'--lifecycle',str(lifecycle),'--output',str(output),'--bind',address+':0','--count','16','--rate','100','--shards','2','--cores','1']
 if role=='source':
  ready=private/'ready.json';ready.write_text(json.dumps(dict(endpoint=remote+':44444',alpn='nbsr-quic-1')))
  argv+=['--ready-input',str(ready),'--destination-address',remote]
 (root/('command-'+str(repeat)+'.json')).write_text(json.dumps(argv))
 with (root/('wrapper-'+str(repeat)+'.stdout')).open('x') as out,(root/('wrapper-'+str(repeat)+'.stderr')).open('x') as err:
  wrapper=subprocess.Popen(argv,stdout=out,stderr=err,start_new_session=True)
  deadline=time.monotonic()+10;owned=None;binding=None
  while time.monotonic()<deadline:
   assert wrapper.poll() is None,'wrapper exited before cancellation point'
   try:
    owned=json.loads((output/'pid.json').read_text())
    row=json.loads((output/'resources.ndjson').read_text().splitlines()[0])
    binary='/tmp/binaries/'+('perf_rust_source' if role=='source' else 'wp8_interop_server')
    binding=snapshot(owned['pid'],row['start_ticks'],binary,address)
    if binding['status']=='MEASURED_LIVE_SOCKET_SNAPSHOT':break
   except (FileNotFoundError,IndexError,json.JSONDecodeError):pass
   time.sleep(.01)
  assert binding and binding['status']=='MEASURED_LIVE_SOCKET_SNAPSHOT','live cancellation point missing'
  (root/('pre-cancel-'+str(repeat)+'.json')).write_text(json.dumps(binding,indent=2))
  wrapper.send_signal(signal.SIGTERM);code=wrapper.wait(timeout=10);assert code!=0
 failure=json.loads((output/'failure.json').read_text());forced=json.loads((output/'forced-cleanup.json').read_text())
 assert failure['error_type']=='InterruptedError' and 'SIGTERM' in failure['error']
 assert forced['group_killed'] and forced['valid'] is False and not (output/'result.json').exists()
 proc=Path('/proc')/str(owned['pid'])/'stat'
 gone=not proc.exists() or parse_proc_stat(proc.read_text(),1,1)['start_ticks']!=row['start_ticks']
 assert gone,'owned child remains after wrapper exit'
 records.append(dict(role=role,repeat=repeat,status='PASS_CANCELLATION_REJECTS_AND_REAPS',wrapper_exit=code,child_pid=owned['pid'],child_start_ticks=row['start_ticks'],owned_child_absent=True,index=verify_index(output),scope='source probe cancels pending connection to unused fixture endpoint; destination cancels listening peer; no successful admission/security claim'))
 (root/'records.json').write_text(json.dumps(records,indent=2));print(role,repeat,'PASS_CANCELLATION',flush=True)
seal_output(root)
