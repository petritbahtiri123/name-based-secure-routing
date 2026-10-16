"""Run one explicitly approved sealed step. Never retries or advances a stage itself."""
import argparse,hashlib,json,pathlib,shutil,sys
import bounded
from plan import HOSTS,final_gate
HERE=pathlib.Path(__file__).resolve().parent

def execute(role,step,pin):
    wire=(HERE/'bundle-manifest.json').read_bytes()
    if hashlib.sha256(wire).hexdigest()!=pin:raise ValueError('approval bundle pin')
    if json.loads((HERE/'approval-status.json').read_text()).get('execution_ready') is not True:
        raise RuntimeError('BLOCKED: approval bundle has not passed independent review; no execution')
    for n,row in json.loads(wire)['files'].items():
        p=HERE/n
        if p.is_symlink() or p.stat().st_size!=row['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('bundle drift')
    for row in json.loads((HERE/'external-inputs.json').read_text()):
        p=pathlib.Path(row['path'])
        if p.is_symlink() or p.stat().st_size!=row['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('referenced input drift')
    # Preserve the exact local coordinator source too; no validator imports from a dirty original checkout.
    inventory=json.loads((HERE/'source-inventory.json').read_bytes())['files']
    for n,row in inventory.items():
        p=bounded.V5/n
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('immutable coordinator source drift')
    cmds=json.loads((HERE/'commands.json').read_text())
    if step in ['start_key_reaper','public_csr_only','transfer_public_certificates','trial','sign_public_csrs','verify_tls']:
        for r in HOSTS:
            if not (HERE/(r+'-smoke-PASS.json')).is_file():raise RuntimeError('both capability gates required')
    if step=='trial':
        for r in HOSTS:
            transfer=json.loads((HERE/('step-'+r+'-transfer_public_certificates/supervision.json')).read_text())
            if transfer.get('status')!='LOCAL_WORKER_COMPLETED' or transfer.get('owned_handles') is not False:raise ValueError('public certificate transfer incomplete')
            bounded.run(cmds[r]['verify_mountpoints'],HERE/('step-'+r+'-trial-mountpoint-check'),20)
            tls_output=HERE/('step-'+r+'-trial-tls-check')
            bounded.run(cmds[r]['verify_tls'],tls_output,20)
            observed=json.loads((tls_output/'stdout.log').read_bytes())['public_hashes']
            expected=json.loads((HERE/'tls-public/certificates/public-hashes.json').read_text())
            if set(observed)!={'ca.der',r+'.der'} or any(expected.get(n)!=v for n,v in observed.items()):raise ValueError('public certificate receipt mismatch')
        return bounded.run(['@COORDINATOR@',cmds['trial'][-1]],HERE/'run01-trial',100)
    if step=='sign_public_csrs':argv=cmds[step]
    else:argv=cmds[role][step]
    output=HERE/('step-'+role+'-'+step)
    if step=='capability_smoke':
        bounded.run(cmds[role]['verify_mountpoints'],HERE/('step-'+role+'-smoke-mountpoint-check'),20)
    result=bounded.run(argv,output,90 if step in ['setup','install','transfer_existing_zip','transfer_public_support'] else 20)
    if step=='capability_smoke':
        row=json.loads((output/'stdout.log').read_bytes())
        if row.get('status')!='PASS_CAPABILITY_ONLY' or row.get('role')!=role:raise ValueError('capability receipt')
        bounded.run(cmds[role]['smoke_absence'],HERE/('step-'+role+'-smoke-absence'),20)
        (HERE/(role+'-smoke-PASS.json')).write_text(json.dumps(row))
    if step=='public_csr_only':
        public=HERE/'tls-public';public.mkdir(exist_ok=True)
        wire=(output/'stdout.log').read_bytes()
        if len(wire)>4096:raise ValueError('CSR bound')
        with (public/(role+'.csr')).open('xb') as f:f.write(wire)
    if step=='independent_absence':
        row=json.loads((output/'stdout.log').read_bytes())
        (HERE/(role+'-absence.json')).write_text(json.dumps(row))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--approved-bundle-sha256',required=True);p.add_argument('role',choices=[*HOSTS,'local']);p.add_argument('step');a=p.parse_args()
    execute(a.role,a.step,a.approved_bundle_sha256)
