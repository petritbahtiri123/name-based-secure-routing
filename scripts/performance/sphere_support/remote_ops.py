"""Explicit approval-stage operations for the two fixed nodes. No import side effects."""

import hashlib, importlib.metadata, json, os, pathlib, subprocess, sys, time, urllib.request, zipfile

from plan import ROOT, UNIT, PIN, CONTROL

from sparse_source import stage, verify

import mountpoints

import tls_lifetime

from mountpoints import validate_mountpoint,may_remove_mountpoint



BASE=pathlib.Path(ROOT)

EVIDENCE=BASE/'evidence/system07'

PACKAGE_HASH='95a04ba20f572482eb8b5befb456347ab9742141a0e38d790f0dfcce65ec20e2'

PACK_HASH='3b3cd7a7b89c651fee7b63091db206f38220646d28121f3ff7b2460c6933c866'

def checked(path, digest):

    if path.is_symlink() or not path.is_file(): raise ValueError('input type')

    b=path.read_bytes()

    if hashlib.sha256(b).hexdigest()!=digest:raise ValueError('input hash')

    return b



def setup():

    import io

    archive=checked(BASE/'payload.zip',PACKAGE_HASH)

    pack=checked(BASE/'source-provenance.pack',PACK_HASH)

    with zipfile.ZipFile(io.BytesIO(archive)) as z:

        manifest=json.loads(z.read('CONTENTS.json'))

        selected=[n for n in manifest if n.startswith('bin/') or n.startswith('inputs/')]

        target=BASE/'payload';target.mkdir()

        for n in selected:

            p=pathlib.PurePosixPath(n)

            if '..' in p.parts or p.is_absolute() or '\\' in n:raise ValueError('path')

            row=manifest[n];b=z.read(n)

            if len(b)!=row['bytes'] or hashlib.sha256(b).hexdigest()!=row['sha256']:raise ValueError('member')

            dst=target/n;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b);dst.chmod(row['mode'])

        inv=json.loads(z.read('inputs/source-presentation-inventory.json'))['files']

        result=stage(BASE/'repo',z.read('inputs/source-presentation-440.tar'),inv,pack)

    (BASE/'evidence').mkdir();(BASE/'evidence/source-proof.json').write_text(json.dumps(result))



def install():

    if sys.version_info[:2]!=(3,12):raise RuntimeError('exact Python 3.12 required')

    rows=json.loads((BASE/'cp312-wheels.json').read_text());pip=json.loads((BASE/'pip-bootstrap.json').read_text())

    wheels=BASE/'wheels';wheels.mkdir()

    for r in [*rows,pip]:

        if not r['url'].startswith('https://files.pythonhosted.org/') or r['bytes']>5_000_000:raise ValueError('download policy')

        with urllib.request.urlopen(r['url'],timeout=20) as f:

            if not f.geturl().startswith('https://files.pythonhosted.org/'):raise ValueError('redirect')

            b=f.read(r['bytes']+1)

        if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('wheel integrity')

        (wheels/r['filename']).write_bytes(b)

    subprocess.run([sys.executable,'-B','-m','venv','--without-pip',str(BASE/'venv')],check=True,timeout=20)

    env={**os.environ,'PYTHONPATH':str(wheels/pip['filename']),'PIP_CONFIG_FILE':'/dev/null','PYTHONDONTWRITEBYTECODE':'1'}

    subprocess.run([str(BASE/'venv/bin/python'),'-B','-m','pip','--isolated','install','--no-index','--no-cache-dir','--no-compile',

        '--only-binary=:all:','--require-hashes','--find-links',str(wheels),'-r',str(BASE/'cp312.lock')],env=env,check=True,timeout=45)



def smoke(role):

    security=security_snapshot(role,smoke=True)

    sys.path.insert(0,str(BASE/'repo'))

    from scripts.performance.linux_native_finite_run import validate_config

    from plan import config

    validate_config(config())

    inv=json.loads((BASE/'payload/inputs/source-presentation-inventory.json').read_text())['files']

    verify(BASE/'repo',inv)

    fixtures=['vectors/wp8-f75-route-open/route-open-body.cbor','vectors/wp8-local-admission/source.cose','vectors/wp8-local-admission/destination.cose']

    assert pathlib.Path('/input').is_dir()

    for n in fixtures: checked(pathlib.Path('/'+n),inv[n]['sha256'])

    mounts=[line.split() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()]

    for p in ['/input','/vectors',ROOT+'/repo']:

        assert any(x[4]==p and 'ro' in x[5].split(',') for x in mounts),'read-only projection absent'

    relative=pathlib.Path('/proc/self/cgroup').read_text().strip().split('::',1)[1].lstrip('/')

    cg=pathlib.Path('/sys/fs/cgroup')/relative

    limits={k:(cg/k).read_text().strip() for k in ['memory.max','memory.swap.max','pids.max','cpu.max']}

    assert limits['memory.max']=='536870912' and limits['memory.swap.max']=='0' and limits['pids.max']=='128'

    quota,period=limits['cpu.max'].split();assert quota!='max' and int(quota)<=int(period)

    versions={r['name']:importlib.metadata.version(r['name']) for r in json.loads((BASE/'cp312-wheels.json').read_text())}

    assert versions=={'cryptography':'45.0.7','cffi':'2.1.0','pycparser':'3.0','cbor2':'5.9.0'}

    result=dict(status='PASS_CAPABILITY_ONLY',role=role,cgroup=relative,limits=limits,versions=versions,uid=os.getuid(),security=security)

    assert os.getuid()!=0

    with (EVIDENCE/('smoke-'+role+'.json')).open('x') as f:json.dump(result,f)

    print(json.dumps(result))



def expected_cgroup(role,smoke=False):

    if role not in UNIT:raise ValueError('role')

    return '/system.slice/'+UNIT[role]+('-smoke' if smoke else '')+'.service'



def validate_security_snapshot(row,role,smoke=False):

    if row['uid']!=1001 or row['gid']!=1001 or row['cgroup']!=expected_cgroup(role,smoke):raise ValueError('identity/cgroup')

    status=row['status']

    if status['NoNewPrivs']!='1' or any(int(status[k],16)!=0 for k in ['CapInh','CapPrm','CapEff','CapBnd','CapAmb']):raise ValueError('privilege boundary')

    for n in ['mnt','user']:

        if row['namespaces'][n]==row['host_namespaces'][n]:raise ValueError('private namespace absent')

    return row



def security_snapshot(role,smoke=False):

    fields=dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)

    row=dict(uid=os.getuid(),gid=os.getgid(),cgroup=pathlib.Path('/proc/self/cgroup').read_text().strip().split('::',1)[1],

             status={k:fields[k].strip() for k in ['NoNewPrivs','CapInh','CapPrm','CapEff','CapBnd','CapAmb']},

             namespaces={n:os.readlink('/proc/self/ns/'+n) for n in ['mnt','user']},

             host_namespaces=json.loads((EVIDENCE/('host-'+role+'.json')).read_text())['namespaces'])

    return validate_security_snapshot(row,role,smoke)



def prepare_output_parent():
    # Endpoint deliberately uses parents=False; reserve its fresh parent first.
    (BASE/'evidence/run07').mkdir(mode=0o700,parents=False,exist_ok=False)

def preflight(role):

    if role not in UNIT or os.getuid()!=1001 or os.getgid()!=1001:raise ValueError('identity')

    for p in [BASE,pathlib.Path(CONTROL),BASE/'repo',BASE/'evidence']:

        if str(p.resolve(strict=True))!=str(p) or p.stat().st_uid!=1001:raise ValueError('canonical owned path')

    if os.path.lexists(tls_lifetime.authority(role)):raise ValueError('unexpected TLS')

    mount_state={n:mountpoints.snapshot(n) for n in mountpoints.PATHS}

    for scope,names in [('--system',[UNIT[role]+'.service',UNIT[role]+'-smoke.service',tls_lifetime.unit(role)])]:

        for name in names:

            p=subprocess.run(['/usr/bin/systemctl',scope,'show',name,'--property=LoadState,ActiveState'],capture_output=True,text=True,timeout=3,check=True)

            fields=dict(x.split('=',1) for x in p.stdout.splitlines())

            if fields!={'LoadState':'not-found','ActiveState':'inactive'}:raise ValueError('unit exists')

    if os.path.lexists(BASE/'evidence/run07'/role):raise ValueError('endpoint output already exists')

    EVIDENCE.mkdir(exist_ok=False)
    prepare_output_parent()

    row={'role':role,'namespaces':{n:os.readlink('/proc/self/ns/'+n) for n in ['mnt','user']},'mountpoints':mount_state}

    with (EVIDENCE/('host-'+role+'.json')).open('x') as f:json.dump(row,f)

    print(json.dumps(row))



def remaining(deadline,cap):

    if deadline is None:return cap

    value=min(cap,deadline-time.monotonic())

    if value<=0:raise TimeoutError('original finalization deadline')

    return value



def system_stop(role,smoke=False,deadline=None):

    if role not in UNIT:raise ValueError('role')

    name=UNIT[role]+('-smoke' if smoke else '')+'.service'

    subprocess.run(['sudo','-i','--','/usr/bin/systemctl','--system','stop',name],capture_output=True,timeout=remaining(deadline,6),check=True)



def verify_system_absence(role,smoke=False,deadline=None):

    name=UNIT[role]+('-smoke' if smoke else '')+'.service'

    p=subprocess.run(['/usr/bin/systemctl','--system','show',name,'--property=Id,LoadState,ActiveState,ControlGroup'],capture_output=True,text=True,timeout=remaining(deadline,2),check=True)

    fields=dict(x.split('=',1) for x in p.stdout.splitlines())

    if fields.get('Id')!=name or fields.get('ActiveState') not in ['inactive','failed'] or fields.get('ControlGroup','')!='':raise ValueError('system unit remains')

    if (pathlib.Path('/sys/fs/cgroup')/expected_cgroup(role,smoke).lstrip('/')).exists():raise ValueError('cgroup remains')

    return fields



def cleanup_mountpoints(role,deadline=None):

    deadline=deadline if deadline is not None else time.monotonic()+10

    verify_system_absence(role,smoke=True,deadline=deadline)

    verify_system_absence(role,deadline=deadline)

    return mountpoints.cleanup(role,EVIDENCE,deadline)



def remove_tls(role):

    p=tls_lifetime.authority(role)

    if not os.path.lexists(p):return

    allowed={role+'-key.der',role+'.csr',role+'.der','ca.der','public-hashes.json'}

    if p.is_symlink() or p.stat().st_uid!=os.getuid():raise ValueError('TLS ownership')

    items=list(p.iterdir())

    if any(q.name not in allowed or q.is_symlink() or not q.is_file() for q in items):raise ValueError('TLS inventory')

    for q in items:q.unlink()

    # Only the system manager removes its runtime directory.



def receipt(role):

    cg=pathlib.Path('/proc/self/cgroup').read_text().strip().split('::',1)[1]

    if cg!=expected_cgroup(role) or os.getuid()!=1001 or os.getgid()!=1001:raise ValueError('receipt identity')

    row={'role':role,'unit':UNIT[role]+'.service','cgroup':cg,'manager':'system','uid':os.getuid(),'gid':os.getgid(),

         **{k:os.environ.get(k) for k in ['SERVICE_RESULT','EXIT_CODE','EXIT_STATUS']}}

    error=None

    try:remove_tls(role);row['tls_cleanup']='REMOVED'

    except BaseException as e:error=e;row['tls_cleanup']='UNCONFIRMED';row['tls_cleanup_error']=type(e).__name__

    with (EVIDENCE/('unit-'+role+'.json')).open('x') as f:json.dump(row,f)

    if error:raise error



def absence(role,deadline=None,emit=True):

    row=json.loads((EVIDENCE/('unit-'+role+'.json')).read_text())

    if row['role']!=role or row['unit']!=UNIT[role]+'.service' or row['cgroup']!=expected_cgroup(role):raise ValueError('unit identity')

    verify_system_absence(role,deadline=deadline)

    cg=pathlib.Path('/sys/fs/cgroup')/row['cgroup'].lstrip('/')

    absent=not cg.exists()

    if not absent:raise RuntimeError('owned cgroup still present; cleanup unconfirmed')

    # Exited cgroup membership is independent of SSH-relay and endpoint counters.

    private=tls_lifetime.authority(role)

    row.update(cgroup_absent=True,**tls_lifetime.absence(role,deadline))

    if emit:print(json.dumps(row))

    return row



def finalize(role):

    # Names are fixed in the sealed plan; no broad process killing or user-service cleanup.

    errors=[];private_removed=False;deadline=time.monotonic()+10

    try:

        try:verify_system_absence(role,deadline=deadline)

        except ValueError:system_stop(role,deadline=deadline);verify_system_absence(role,deadline=deadline)

    except BaseException as e:errors.append('endpoint_stop_'+type(e).__name__)

    try:remove_tls(role);private_removed=True

    except BaseException as e:errors.append('tls_cleanup_'+type(e).__name__)

    if private_removed:

        try:

            tls_lifetime.stop(role,deadline=deadline)

        except BaseException as e:errors.append('expiry_stop_'+type(e).__name__)

    # Preserve the fallback expiry service when private removal is unconfirmed.

    try:

        result=absence(role,deadline=deadline,emit=False)

        cleanup_mountpoints(role,deadline=deadline)

        result['mountpoint_cleanup']='CONFIRMED'

        if not errors:print(json.dumps(result))

    except BaseException as e:errors.append('absence_'+type(e).__name__)

    if errors:

        print(json.dumps({'cleanup_errors':errors}),file=sys.stderr)

        raise RuntimeError('owned cleanup unconfirmed')



if __name__=='__main__':

    action=sys.argv[1]

    if action=='setup':setup()

    elif action=='preflight' and sys.argv[2] in UNIT:preflight(sys.argv[2])

    elif action=='prepare-mountpoints' and sys.argv[2] in UNIT:mountpoints.prepare(sys.argv[2],EVIDENCE)

    elif action=='verify-mountpoints' and sys.argv[2] in UNIT:print(json.dumps(mountpoints.verify(sys.argv[2],EVIDENCE)))

    elif action=='cleanup-mountpoints' and sys.argv[2] in UNIT:print(json.dumps(cleanup_mountpoints(sys.argv[2])))

    elif action=='smoke-absence' and sys.argv[2] in UNIT:print(json.dumps(verify_system_absence(sys.argv[2],smoke=True)))

    elif action=='install':install()

    elif action=='smoke' and sys.argv[2] in UNIT:smoke(sys.argv[2])

    elif action=='start-tls' and sys.argv[2] in UNIT:tls_lifetime.start(sys.argv[2])

    elif action=='verify-tls' and sys.argv[2] in UNIT:print(json.dumps(tls_lifetime.gate(sys.argv[2],150,public=True)))

    elif action=='stop-tls' and sys.argv[2] in UNIT:print(json.dumps(tls_lifetime.stop(sys.argv[2])))

    elif action=='remove-tls' and sys.argv[2] in UNIT:remove_tls(sys.argv[2])

    elif action=='receipt' and sys.argv[2] in UNIT:receipt(sys.argv[2])

    elif action=='absence' and sys.argv[2] in UNIT:absence(sys.argv[2])

    elif action=='finalize' and sys.argv[2] in UNIT:finalize(sys.argv[2])

    else:raise SystemExit('unsupported operation')
