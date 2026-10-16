"""Exact system-owned ephemeral runtime directory; never reads a private key."""

import pathlib,os,stat,subprocess,time,json,re,hashlib

from plan import UNIT,ROOT

EXPECTED={'User':'1001','Group':'1001','Type':'exec','Restart':'no','RuntimeDirectoryMode':'0700','RuntimeDirectoryPreserve':'no','RuntimeMaxUSec':'5min','TimeoutStopUSec':'5s','KillMode':'control-group','SendSIGKILL':'yes','NoNewPrivileges':'yes','PrivateUsers':'yes','PrivateMounts':'yes','CapabilityBoundingSet':'','AmbientCapabilities':'','MemoryMax':'67108864','MemorySwapMax':'0','TasksMax':'16','CPUQuotaPerSecUSec':'100ms'}

def dirname(role):return UNIT[role]+'-tls'

def unit(role):return UNIT[role]+'-tls-expiry.service'

def authority(role):return pathlib.Path('/run')/dirname(role)

def start_command(role):

 props=['Type=exec','Restart=no','RuntimeDirectory='+dirname(role),'RuntimeDirectoryMode=0700','RuntimeDirectoryPreserve=no','RuntimeMaxSec=300','TimeoutStopSec=5','KillMode=control-group','SendSIGKILL=yes','User=1001','Group=1001','UMask=0077','NoNewPrivileges=yes','PrivateUsers=yes','PrivateMounts=yes','CapabilityBoundingSet=','AmbientCapabilities=','MemoryMax=67108864','MemorySwapMax=0','TasksMax=16','CPUQuota=10%','LimitCORE=0','LimitFSIZE=16384','StandardOutput=null','StandardError=journal']

 return ['sudo','-i','--','/usr/bin/systemd-run','--system','--uid=1001','--gid=1001','--quiet','--unit='+unit(role),*['--property='+p for p in props],'--','/usr/bin/sleep','300']

def budget(deadline,cap):

 remaining=cap if deadline is None else min(cap,deadline-time.monotonic())

 if remaining<=0:raise TimeoutError('original TLS cleanup deadline')

 return remaining

def show(role,deadline=None):

 keys=[*EXPECTED,'LoadState','Id','ActiveState','SubState','MainPID','ActiveEnterTimestampMonotonic','ControlGroup','RuntimeDirectory','ExecStart']

 p=subprocess.run(['/usr/bin/systemctl','--system','show',unit(role),'--property='+','.join(keys)],capture_output=True,text=True,timeout=budget(deadline,3),check=True)

 return dict(line.split('=',1) for line in p.stdout.splitlines())

def validate(role,row,now,min_remaining):

 expected={**EXPECTED,'Id':unit(role),'ActiveState':'active','SubState':'running','RuntimeDirectory':dirname(role),'ControlGroup':'/system.slice/'+unit(role)}

 if any(row.get(k)!=v for k,v in expected.items()) or int(row.get('MainPID','0'))<=0:raise ValueError('TLS holder identity/configuration')

 match=re.findall(r'path=([^;]+);\s*argv\[\]=([^;]+);',row.get('ExecStart',''))

 if len(match)!=1 or tuple(x.strip() for x in match[0])!=('/usr/bin/sleep','/usr/bin/sleep 300'):raise ValueError('TLS holder executable')

 age=now-int(row['ActiveEnterTimestampMonotonic'])/1_000_000

 if not 0<=age<300 or 300-age<min_remaining:raise ValueError('insufficient original TLS lifetime')

 return 300-age

def directory_state(role):

 p=authority(role);s=p.lstat()

 if not stat.S_ISDIR(s.st_mode) or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=(1001,1001,0o700) or p.resolve(strict=True)!=p:raise ValueError('TLS runtime directory ownership/mode')

 mounts=[line.split() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()]

 if not any(x[4]=='/run' and x[x.index('-')+1]=='tmpfs' for x in mounts):raise ValueError('memory-backed /run required')

 return {'device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode)}

def gate(role,min_remaining=120,*,initial=False,public=False):

 remaining=validate(role,show(role),time.monotonic(),min_remaining);state=directory_state(role)

 receipt=pathlib.Path(ROOT)/'evidence/system07'/('tls-directory-'+role+'.json')

 if initial:

  if list(authority(role).iterdir()):raise ValueError('new TLS directory not empty')

  with receipt.open('x') as f:json.dump(state,f)

 elif json.loads(receipt.read_text())!=state:raise ValueError('TLS runtime directory replaced')

 result={'role':role,'remaining_seconds':remaining,'directory':state}

 if public:

  p=authority(role);allowed={role+'-key.der',role+'.csr',role+'.der','ca.der','public-hashes.json'}

  if {q.name for q in p.iterdir()}!=allowed:raise ValueError('TLS inventory')

  for q in p.iterdir():

   s=q.lstat()

   if not stat.S_ISREG(s.st_mode) or s.st_uid!=1001 or s.st_size>16384:raise ValueError('TLS file metadata')

  if stat.S_IMODE((p/(role+'-key.der')).stat().st_mode)!=0o600:raise ValueError('private key mode')

  hashes={n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in ['ca.der',role+'.der']}

  expected=json.loads((p/'public-hashes.json').read_text())

  if any(expected.get(n)!=v for n,v in hashes.items()):raise ValueError('public certificate digest')

  result['public_hashes']=hashes

 return result

def start(role):

 if os.path.lexists(authority(role)):raise ValueError('runtime directory already exists')

 row=show(role)

 if row.get('LoadState')!='not-found' or row.get('ActiveState')!='inactive' or row.get('MainPID')!='0':raise ValueError('TLS holder already exists')

 subprocess.run(start_command(role),capture_output=True,check=True,timeout=6)

 print(json.dumps(gate(role,270,initial=True)))

def absence(role,deadline=None):

 row=show(role,deadline)

 if row.get('ActiveState') not in ['inactive','failed'] or row.get('ControlGroup','') or int(row.get('MainPID','0')):raise ValueError('TLS holder still active')

 if (pathlib.Path('/sys/fs/cgroup/system.slice')/unit(role)).exists() or os.path.lexists(authority(role)):raise ValueError('TLS holder directory/cgroup remains')

 return {'tls_holder_absent':True,'tls_path_absent':True}

def stop(role,deadline=None):

 deadline=deadline if deadline is not None else time.monotonic()+10

 row=show(role,deadline)

 if row.get('ActiveState') not in ['inactive','failed'] or row.get('MainPID')!='0':

  subprocess.run(['sudo','-i','--','/usr/bin/systemctl','--system','stop',unit(role)],capture_output=True,check=True,timeout=budget(deadline,6))

 return absence(role,deadline)
