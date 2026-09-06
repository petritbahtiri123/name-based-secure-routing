import json,os,subprocess,sys,time
from pathlib import Path
from scripts.performance.linux_resources import LinuxResourceSampler
from scripts.performance.linux_exit import observe_owned_exit
cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
a=subprocess.Popen([sys.executable,"-c","import sys; sys.stdin.readline()"],stdin=subprocess.PIPE)
b=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])
s=LinuxResourceSampler({'source':a.pid,'destination':b.pid},[cpu],interval_seconds=.01,max_records=1000,terminal_roles=('source',))
started=False
try:
 s.start();started=True
 deadline=time.monotonic()+5
 while len(s.records_snapshot())<2:
  s.check_health(require_running=True)
  if time.monotonic()>deadline:raise RuntimeError('initial samples deadline')
  time.sleep(.01)
 a.stdin.write(b'close\n');a.stdin.flush();a.stdin.close()
 while True:
  s.check_health(require_running=True);rows=s.records_snapshot()
  terminal=[r for r in rows if r['role']=='source' and r['state']=='Z']
  if terminal and len([r for r in rows if r['role']=='destination' and r['timestamp_ns']>terminal[0]['timestamp_ns']])>=2:break
  if time.monotonic()>deadline:raise RuntimeError('terminal sample deadline')
  time.sleep(.01)
 assert observe_owned_exit(a.pid)==0 and a.returncode is None
 rows=s.stop();started=False
 assert len(terminal)==1 and terminal[0]['private_resident_bytes'] is None
 assert a.wait(timeout=5)==0
 b.terminate();b.wait(timeout=5)
 print(json.dumps(dict(classification='LINUX_SAMPLER_LIFECYCLE_COMPATIBILITY_ONLY',selected_cpu=cpu,source_terminal_samples=len(terminal),destination_continues=True,source_explicit_join=0,records=rows)))
finally:
 if started:
  try:s.stop()
  except Exception:pass
 for child in [a,b]:
  if child.returncode is None:
   try:child.kill()
   except ProcessLookupError:pass
   child.wait(timeout=5)
