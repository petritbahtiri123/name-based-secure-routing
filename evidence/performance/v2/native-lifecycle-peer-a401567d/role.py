import os,sys
os.chdir('/tmp/source');sys.path.insert(0,'/tmp/source')
from scripts.performance.linux_native_lifecycle import main
role,label,count,address,remote=sys.argv[1:]
args=['--role',role,'--binaries','/tmp/binaries','--build-manifest','/build/build-manifest.json','--authority','/fixture/'+label+'/authority','--lifecycle','/fixture/'+label+'/'+role,'--output','/out/'+label,'--bind',address+':0','--count',count,'--shards','2','--rate','100','--cores','1']
if role=='source':args+=['--ready-input','/control/destination/'+label+'/ready.json','--destination-address',remote]
sys.argv=['linux_native_lifecycle',*args];main()
