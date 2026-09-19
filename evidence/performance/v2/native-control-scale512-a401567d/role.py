import os,sys,json,shutil,threading,time,signal,subprocess
from pathlib import Path
os.chdir('/tmp/source');sys.path.insert(0,'/tmp/source')
from scripts.performance.linux_native_lifecycle import main
from scripts.performance.linux_loopback import write_json
role,label,count,address,remote,mode=sys.argv[1:];count=int(count)
fixture=Path('/fixture')/label;original=fixture/role
lifecycle=original if mode=='windows' else Path('/tmp')/('control-'+label+'-'+role)
if mode=='local':shutil.copytree(original,lifecycle)
out=Path('/out');stop=threading.Event();errors=[]
write_json(out/(label+'-storage.json'),dict(root=str(lifecycle),mode=mode,
    filesystem=subprocess.check_output(['stat','-f','-c','%T',str(lifecycle)],text=True).strip(),
    observer='separate control-watcher thread; outside child affinity; diagnostic only'))
def watch():
 try:
  published=set()
  while not stop.wait(.01):
   if not (out/label/'pid.json').exists():continue
   if (Path('/control/signals')/(label+'.cancel')).exists():
    os.kill(os.getpid(),signal.SIGTERM);return
   names={p.name for p in lifecycle.iterdir()}
   active={('connection-' if role=='source' else 'destination-')+str(i)+'.active' for i in range(count)}
   if active<=names and 'active' not in published:
    write_json(out/(label+'-active.json'),dict(names=sorted(active),timestamp_ns=time.monotonic_ns()));published.add('active')
   failures=sorted(n for n in names if n.endswith('.failed'))
   if failures and 'failed' not in published:
    write_json(out/(label+'-failed.json'),dict(names=failures,timestamp_ns=time.monotonic_ns()));published.add('failed')
   if (Path('/control/signals')/(label+'.'+role+'.release')).exists() and 'release' not in published:
    for i in range(count):(lifecycle/f'connection-{i}.release').write_text('release\n')
    write_json(out/(label+'-released.json'),dict(count=count));published.add('release')
   if role=='source' and {f'connection-{i}.ack' for i in range(count)}<=names and 'acked' not in published:
    write_json(out/(label+'-acked.json'),dict(count=count));published.add('acked')
   if role=='destination' and 'destination.report-ready' in names and 'report-ready' not in published:
    write_json(out/(label+'-report-ready.json'),dict(ready=True));published.add('report-ready')
   if role=='destination' and (Path('/control/signals')/(label+'.report-release')).exists() and 'report-release' not in published:
    (lifecycle/'destination.report-release').write_text('release\n');published.add('report-release')
 except BaseException as error:
  errors.append(str(error));write_json(out/(label+'-watcher-error.json'),dict(error=str(error)))
  if (out/label/'pid.json').exists():os.kill(os.getpid(),signal.SIGTERM)
worker=threading.Thread(target=watch);worker.start()
args=['--role',role,'--binaries','/tmp/binaries','--build-manifest','/build/build-manifest.json',
 '--authority',str(fixture/'authority'),'--lifecycle',str(lifecycle),'--output',str(out/label),
 '--bind',address+':0','--count',str(count),'--shards','2','--rate','100','--cores','1']
if role=='source':args+=['--ready-input','/control/destination/'+label+'/ready.json','--destination-address',remote]
try:
 sys.argv=['linux_native_lifecycle',*args];main()
finally:
 stop.set();worker.join(timeout=5);assert not worker.is_alive()
 markers=out/(label+'-markers');markers.mkdir()
 for p in lifecycle.iterdir():
  if p.is_file():shutil.copyfile(p,markers/p.name)
 assert not errors,errors
