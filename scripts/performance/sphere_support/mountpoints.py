"""Exact two host mountpoints; no recursive deletion or ownership adoption."""
import os,stat,pathlib,json,subprocess,time
PATHS=('/input','/vectors')
def validate_mountpoint(row):
    if not row['exists']:return row
    if not row['directory'] or row['uid']!=0 or row['gid']!=0 or row['mode']&0o022 or not row['empty'] or row['mounted']:
        raise ValueError('unsafe host mountpoint')
    return row
def snapshot(name):
    if name not in PATHS:raise ValueError('mountpoint name')
    p=pathlib.Path(name)
    try:s=p.lstat()
    except FileNotFoundError:return {'exists':False}
    directory=stat.S_ISDIR(s.st_mode)
    mounts=[line.split()[4] for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()]
    row=dict(exists=True,directory=directory,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode),
             device=s.st_dev,inode=s.st_ino,empty=directory and next(p.iterdir(),None) is None,mounted=name in mounts)
    return validate_mountpoint(row)
def may_remove_mountpoint(record,current):
    validate_mountpoint(current)
    if record.get('state')!='created' or record.get('created_by_task') is not True:raise ValueError('not confirmed task-created')
    if not current['exists'] or current!=record['identity']:raise ValueError('mountpoint changed')
    return True
def write(path,row,exclusive=False):
    with path.open('x' if exclusive else 'w') as f:
        json.dump(row,f);f.flush();os.fsync(f.fileno())
def prepare(role,evidence):
    baseline=json.loads((evidence/('host-'+role+'.json')).read_text())['mountpoints']
    path=evidence/('mountpoints-'+role+'.json');state={'role':role,'records':{}}
    write(path,state,True)
    for name in PATHS:
        current=snapshot(name)
        if current!=baseline[name]:raise ValueError('mountpoint changed since preflight')
        if current['exists']:
            state['records'][name]={'state':'preexisting','created_by_task':False,'identity':current};write(path,state);continue
        state['records'][name]={'state':'creation_intent','created_by_task':False};write(path,state)
        # If this fails or completion is uncertain, never adopt the observed directory for deletion.
        subprocess.run(['sudo','-i','--','/usr/bin/mkdir','--mode=0755','--',name],capture_output=True,timeout=4,check=True)
        identity=snapshot(name)
        if not identity['exists']:raise ValueError('created mountpoint absent')
        state['records'][name]={'state':'created','created_by_task':True,'identity':identity};write(path,state)
    print(json.dumps(state))
def verify(role,evidence):
    state=json.loads((evidence/('mountpoints-'+role+'.json')).read_text())
    if state['role']!=role or set(state['records'])!=set(PATHS):raise ValueError('mountpoint records incomplete')
    for name,row in state['records'].items():
        if row['state'] not in ['created','preexisting'] or snapshot(name)!=row['identity']:raise ValueError('mountpoint identity drift')
    return state
def cleanup(role,evidence,deadline):
    path=evidence/('mountpoints-'+role+'.json');state=json.loads(path.read_text())
    if state['role']!=role:raise ValueError('mountpoint record role')
    for name in PATHS:
        row=state['records'].get(name)
        if row is None:
            if snapshot(name)['exists']:raise ValueError('unrecorded mountpoint exists')
            continue
        current=snapshot(name)
        if row['state']=='preexisting':
            if current!=row['identity']:raise ValueError('preexisting mountpoint changed')
            continue
        if row['state']=='removed':
            if current['exists']:raise ValueError('removed path recreated')
            continue
        may_remove_mountpoint(row,current)
        remaining=min(2,deadline-time.monotonic())
        if remaining<=0:raise TimeoutError('mountpoint cleanup deadline')
        subprocess.run(['sudo','-i','--','/usr/bin/rmdir','--',name],capture_output=True,timeout=remaining,check=True)
        if os.path.lexists(name):raise ValueError('mountpoint removal unconfirmed')
        row['state']='removed';write(path,state)
    return state
