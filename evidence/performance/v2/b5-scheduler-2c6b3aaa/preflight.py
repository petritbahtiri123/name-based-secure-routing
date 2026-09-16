from pathlib import Path
import json, shutil, subprocess, sys, time
out=Path('/out')
bins=Path('/tmp/binaries');bins.mkdir()
shutil.copy2('/bin/sleep',bins/'perf_rust_source')
prefix=out/'preflight'
watcher=subprocess.Popen([sys.executable,str(out/'sched_observe.py'),str(prefix)])
until=time.monotonic()+5
while not prefix.with_suffix('.ready').exists():
 assert watcher.poll() is None and time.monotonic()<until
 time.sleep(.01)
child=subprocess.Popen([str(bins/'perf_rust_source'),'3'])
assert child.wait(timeout=5)==0
watcher.terminate();assert watcher.wait(timeout=5)==0
rows=[json.loads(x) for x in prefix.with_suffix('.ndjson').read_text().splitlines()]
samples=[r for r in rows if r.get('event')=='scheduler_sample']
assert len(samples)>=2 and all(r['pid']==child.pid for r in samples)
assert rows[-1]['event']=='observer_end' and rows[-1]['stopped']
print('PASS: non-root owned-process discovery, identity, counter capture, bounded shutdown')
