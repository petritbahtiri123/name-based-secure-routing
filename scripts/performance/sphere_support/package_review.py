"""Local review packaging only; no remote execution."""
import pathlib,json,hashlib,shlex,subprocess,sys
HERE=pathlib.Path(__file__).resolve().parent
def digest(p):return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
if __name__=='__main__':
    c=json.loads((HERE/'commands.json').read_text())
    inputs=sorted(set(c['destination']['transfer_public_support'][3:-1]+[c['destination']['transfer_existing_zip'][3]]))
    (HERE/'external-inputs.json').write_text(json.dumps([{'path':n,**digest(pathlib.Path(n))} for n in inputs],indent=2))
    rows=['PROPOSED COMMANDS — REQUIRE USER APPROVAL. See APPROVAL.md.\n']
    for action,commands in c['exact_mountpoint_administration'].items():
        rows+=['\nOn each host only after mountpoints.py checks: '+action,*[shlex.join(a) for a in commands]]
    for role in ['source','destination']:
        for step in ['capability_smoke','stop_owned_smoke','stop_owned_endpoint','reset_failed_smoke_after_capture','reset_failed_endpoint_after_capture']:
            rows+=['\n'+role+' / '+step+' on '+c[role][step][-2],c[role][step][-1]]
        rows+=['\n'+role+' / conditional one-trial endpoint on '+c['exact_trial_endpoints'][role][-2],c['exact_trial_endpoints'][role][-1]]
    (HERE/'commands-review.txt').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'],capture_output=True,text=True,timeout=30)
    (HERE/'tests-final.txt').write_text(p.stdout+p.stderr+'\nexit_code='+str(p.returncode)+'\n')
    if p.returncode:raise SystemExit(p.returncode)
    print('All local candidate tests passed; not a remote execution approval.')
