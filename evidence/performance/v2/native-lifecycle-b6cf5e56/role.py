import json,os,sys,time,subprocess,signal
from pathlib import Path
os.chdir('/tmp/source');sys.path.insert(0,'/tmp/source')
from scripts.performance.b3_linux import environment
from scripts.performance.linux_native_peer import wait_target_exec,observe_child
from scripts.performance.linux_loopback import digest,write_json
from scripts.performance.linux_b5_reference import git_state
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.process_cancellation import Cancellation
role,label,count,address,remote=sys.argv[1:];count=int(count)
assert role in ('source','destination') and count in (16,32,64,128)
fixture=Path('/fixture')/label;lifecycle=fixture/'lifecycle';authority=fixture/'authority'
out=Path('/out')/label;out.mkdir()
host=environment(1);sha,dirty=git_state();assert not dirty
build=json.loads(Path('/build/build-manifest.json').read_text());assert build['source_sha']==sha
binary=Path('/tmp/binaries')/('perf_rust_source' if role=='source' else 'wp8_interop_server')
assert digest(binary)==build['binary_sha256'][binary.name]
common=['--authority-dir',str(authority)]
if role=='source':
 ready=json.loads((fixture/'ready.json').read_text());assert ready['endpoint'].split(':')[0]==remote
 argv=[str(binary),*common,'--endpoint',ready['endpoint'],'--samples','1','--payload-bytes','1024','--lifecycle-authority-dir',str(lifecycle),'--connections','1','--services','1','--streams-per-service','1','--concurrent-streams','--hold-for-release','--connection-offset','0','--diagnostics','1','--lifecycle-clients',str(count),'--lifecycle-source-shards','2','--lifecycle-offered-rate','100','--b3-materialized-streams','1','--benchmark-client-bind',address+':0']
 overrides={}
else:
 argv=[str(binary),*common,'--ready',str(fixture/'ready.json'),'--result',str(out/'server-result.json'),'--completion-ack',str(fixture/'completion.ack'),'--destination-diagnostics-file',str(out/'diagnostics.ndjson'),'--diagnostic-drain-seconds','2','--b3-report-gate',str(lifecycle),'--b3-materialized-streams','1','--benchmark-listen',address+':0']
 overrides=dict(NBSR_PERF_LIFECYCLE_ROOT=str(lifecycle),NBSR_PERF_LIFECYCLE_CONNECTIONS=str(count),NBSR_PERF_LIFECYCLE_SERVICES='1',NBSR_PERF_STREAMS_PER_SERVICE='1',NBSR_PERF_CONCURRENT_STREAMS='1',NBSR_PERF_CONCURRENT_SESSIONS='1',NBSR_PERF_LIFECYCLE_SERIAL_ACCEPT='1',NBSR_PERF_LIFECYCLE_OFFERED_RATE='100')
command=[host['taskset'],'--cpu-list',','.join(map(str,host['selected_cpus'])),*argv]
write_json(out/'environment.json',dict(role=role,source_sha=sha,count=count,linux_environment=host,binary_sha256=digest(binary),uid=os.getuid(),scope='diagnostic native namespace lifecycle; shared host'))
write_json(out/'command.json',dict(argv=command,environment_overrides=overrides))
child=None;success=False
try:
 with Cancellation() as cancellation,(out/'stdout').open('x') as stdout,(out/'stderr').open('x') as stderr:
  clean={k:v for k,v in os.environ.items() if not k.startswith('NBSR_')}
  child=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=clean|overrides,start_new_session=True)
  write_json(out/'pid.json',dict(pid=child.pid,owns_process_group=True))
  wait_target_exec(child,binary,check_cancelled=cancellation.check)
  result=observe_child(child,host['selected_cpus'],out,deadline=time.monotonic()+120,check_cancelled=cancellation.check)
  assert result['exit_code']==0
  write_json(out/'result.json',dict(status='PASS_OWNED_EXIT',**result));success=True
except BaseException as error:
 write_json(out/'failure.json',dict(error=str(error),kind=type(error).__name__));raise
finally:
 if child is not None and not success:
  try:os.killpg(child.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  child.wait(timeout=5)
  write_json(out/'forced-cleanup.json',dict(pid=child.pid))
 seal_output(out)
