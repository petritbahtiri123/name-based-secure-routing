"""Windows Job wrapper for one reviewed command or coordinator. Never runs at import."""
import ctypes, json, pathlib, shutil, subprocess, sys, time
V5=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(V5))
import resource_boundary
class MemoryStatus(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','page_total','page_available','virtual_total','virtual_available','extended']]

def run(argv, output, work=60):
    from draining_owner import DrainingOwner as WindowsOwner
    from diagnostic_backend import DiagnosticBackend as Win32Backend
    from scripts.performance.linux_native_watchdog import supervise
    resource_boundary.check(starting=True)
    output=pathlib.Path(output);output.mkdir(exist_ok=False)
    started=time.monotonic()
    request=output/'request.json';request.write_text(json.dumps({'argv':argv,'output':str(output.resolve()),'started':started}))
    owner=WindowsOwner([sys.executable,'-B',str(pathlib.Path(__file__).resolve()),'worker',str(request.resolve())],backend=Win32Backend(),deadline=started+min(work,100),cancel=lambda:(output/'cancel').touch())
    def guard():
        roots=[pathlib.Path(__file__).parent]+[pathlib.Path(__file__).parent.parent/n for n in ['approval-tls-retry06-2026-10-16','approval-tls-system-2026-10-16','approval-drain2-2026-10-16','approval-cadence-2026-10-16','approval-sudo-login-2026-10-16','approval-system-2026-10-16','approval-2026-10-16','approval-2026-10-16-r2','approval-2026-10-16-r3','disk-boundary-2026-10-16']]
        counts=resource_boundary.check(starting=False,groups={'artifacts':roots,'output':[output]})
        m=MemoryStatus();m.length=ctypes.sizeof(m)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) or min(m.available,m.page_available)<2*1024**3:raise RuntimeError('laptop memory reserve')
        if counts['artifacts']>128*1024**2:raise RuntimeError('whole approval workspace cap')
        if counts['output']>80*1024**2:raise RuntimeError('evidence byte cap')
    def cutoff():
        if time.monotonic()-started>=work:raise TimeoutError('work deadline')
    result=supervise(owner,started_at=started,guard=guard,check_cancelled=cutoff)
    (output/'job-exit-observations.json').write_text(json.dumps(owner.backend.exit_observations,indent=2))
    (output/'job-drain.json').write_text(json.dumps(owner.drain_events,indent=2))
    result['drain_failure']=owner.drain_failure
    result['owned_handles']=owner.owned
    (output/'supervision.json').write_text(json.dumps(result,indent=2))
    if result['status']!='LOCAL_WORKER_COMPLETED' or owner.owned or owner.drain_failure:raise RuntimeError('owned command failed; retain evidence')
    return result

def worker(path):
    r=json.loads(pathlib.Path(path).read_text());out=pathlib.Path(r['output'])
    if r['argv'][0]=='@COORDINATOR@':
        import coordinator,shlex
        from plan import HOSTS,ROOT,CONTROL,final_gate
        problem=None;result=None;receipts={};cleanup_errors={}
        try:result=coordinator.execute(out/'coordinator',r['argv'][1],r['started'])
        except BaseException as e:problem=e
        finally:
            for role,host in HOSTS.items():
                try:
                    remaining=110-(time.monotonic()-r['started'])
                    if remaining<=0:raise TimeoutError('original cleanup budget expired')
                    a=['ssh','-F',r['argv'][1],'-T','--',host,shlex.join([ROOT+'/venv/bin/python','-B',CONTROL+'/remote_ops.py','finalize',role])]
                    p=subprocess.run(a,capture_output=True,timeout=min(12,remaining))
                    (out/(role+'-cleanup-stdout.log')).write_bytes(p.stdout)
                    (out/(role+'-cleanup-stderr.log')).write_bytes(p.stderr)
                    if p.returncode:raise RuntimeError('cleanup command exit '+str(p.returncode))
                    receipts[role]=json.loads(p.stdout)
                except BaseException as e:cleanup_errors[role]=type(e).__name__
            (out/'independent-cleanup.json').write_text(json.dumps({'receipts':receipts,'errors':cleanup_errors},indent=2))
            (out/'worker-ended.json').write_text(json.dumps({'elapsed':time.monotonic()-r['started']}))
        if problem:raise problem
        if cleanup_errors:raise RuntimeError('independent cleanup unconfirmed')
        (out/'final-result.json').write_text(json.dumps({'status':final_gate(result,receipts)}))
        return
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        p=subprocess.run(r['argv'],stdout=stdout,stderr=stderr)
    (out/'exit.json').write_text(json.dumps({'exit_code':p.returncode}))
    raise SystemExit(p.returncode)

if __name__=='__main__':
    if sys.argv[1]=='worker':worker(sys.argv[2])
    elif sys.argv[1]=='run':run(sys.argv[4:],sys.argv[2],int(sys.argv[3]))
    else:raise SystemExit('run OUTPUT WORK_SECONDS COMMAND ARGS...')
