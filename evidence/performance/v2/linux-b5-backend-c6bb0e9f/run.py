import json,os,subprocess,sys,time
from scripts.performance.linux_b5_backend import LinuxB5Backend
cpu=min(os.sched_getaffinity(0)); backend=LinuxB5Backend(dict(platform="linux",selected_cpus=[cpu],taskset="/usr/bin/taskset"))
mask=1<<cpu;backend.validate(dict(endpoint_groups=1),dict(source_mask=mask,endpoint_masks=[mask],logical_processors_available=1))
argv=backend.command([sys.executable,"-c","import sys; sys.stdin.readline()"])
children=[];sampler=None;running=False;rows=[]
try:
 for role in ['source','destination_0']:
  p=subprocess.Popen(argv,stdin=subprocess.PIPE);children.append(p)
  assert backend.verify_affinity(p,mask,sys.executable)['verified']
 a,b=children
 sampler=backend.sampler({'source':a.pid,'destination_0':b.pid},interval=.01,bound=1000,sink=rows.append)
 sampler.start();running=True;deadline=time.monotonic_ns()+5_000_000_000
 while len(sampler.records_snapshot())<2:
  sampler.check_health(require_running=True)
  if time.monotonic_ns()>deadline:raise RuntimeError('live sampling deadline')
  time.sleep(.01)
 a.stdin.write(b'close\n');a.stdin.flush();a.stdin.close()
 while backend.observe_source(a) is None:
  sampler.check_health(require_running=True)
  if time.monotonic_ns()>deadline:raise RuntimeError('source deadline')
  time.sleep(.01)
 backend.complete_source(a,sampler,deadline);running=False
 assert a.returncode==0 and b.returncode is None
 b.stdin.write(b'ack\n');b.stdin.flush();b.stdin.close()
 backend.complete_destination(b,'destination_0',sampler,rows.append,deadline)
 assert b.returncode==0
 assert len([r for r in rows if r['role']=='source' and r['state']=='Z'])==1
 assert rows[-1]['role']=='destination_0' and rows[-1]['state']=='Z'
 print(json.dumps(dict(classification='LINUX_BACKEND_LIFECYCLE_ONLY',argv=argv,source_join=0,destination_join=0,terminal_samples_before_reaping=True,records=rows)))
finally:
 if running:
  try:sampler.stop()
  except Exception:pass
 for p in children:
  if p.returncode is None:
   try:p.kill()
   except ProcessLookupError:pass
   p.wait(timeout=5)
