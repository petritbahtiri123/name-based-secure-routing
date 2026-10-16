"""Generate exact review argv only. Never connects or executes."""

import pathlib,json,shlex

from plan import ROOT,CONTROL,HOSTS,UNIT,service,config,remote_argv

HERE=pathlib.Path(__file__).resolve().parent

SSH=str(HERE.parent/'preflight-2026-10-16/ssh-readonly.conf')

def ssh(role,argv):return ['ssh','-F',SSH,'-T','--',HOSTS[role],shlex.join(argv)]

def commands(prior_commands=None):

    # Synthetic argv are review fixtures, never deployment instructions.
    old=prior_commands if prior_commands is not None else {'destination': {n: ['EXPLICIT_REVIEWED_INPUT_REQUIRED'] for n in ['create_fresh_root','transfer_existing_zip','transfer_public_support','setup','install']}}

    result={r:{} for r in HOSTS}

    for n in ['create_fresh_root','transfer_existing_zip','transfer_public_support','setup','install']:

        result['destination'][n]=old['destination'][n]

    public=['plan.py','remote_ops.py','sparse_source.py','peer_guard.py','tls_roles.py','mountpoints.py','tls_lifetime.py']

    create="import pathlib,os; p=pathlib.Path("+repr(ROOT)+"); assert str(p.resolve(strict=True))==str(p) and p.stat().st_uid==os.getuid()==1001; (p/'control07').mkdir(mode=0o700,exist_ok=False)"

    for r in HOSTS:

        call=lambda action:[ROOT+'/venv/bin/python','-B',CONTROL+'/remote_ops.py',action,r]

        result[r].update({

            'create_control':ssh(r,['python3','-B','-c',create]),

            'transfer_control':['scp','-F',SSH,*[str(HERE/n) for n in public],HOSTS[r]+':'+CONTROL+'/'],

            'preflight':ssh(r,call('preflight')),

            'prepare_mountpoints':ssh(r,call('prepare-mountpoints')),

            'verify_mountpoints':ssh(r,call('verify-mountpoints')),

            'cleanup_mountpoints':ssh(r,call('cleanup-mountpoints')),

            'capability_smoke':ssh(r,service(r,call('smoke'),smoke=True)),

            'smoke_absence':ssh(r,call('smoke-absence')),

            'start_key_reaper':ssh(r,call('start-tls')),

            'verify_tls':ssh(r,call('verify-tls')),

            'public_csr_only':ssh(r,[ROOT+'/venv/bin/python','-B',CONTROL+'/tls_roles.py',r]),

            'transfer_public_certificates':['scp','-F',SSH,str(HERE/'tls-public/certificates/ca.der'),str(HERE/('tls-public/certificates/'+r+'.der')),str(HERE/'tls-public/certificates/public-hashes.json'),HOSTS[r]+':/run/'+UNIT[r]+'-tls/'],

            'independent_absence':ssh(r,call('absence')),

            'finalize':ssh(r,call('finalize')),

            'stop_owned_endpoint':ssh(r,['sudo','-i','--','/usr/bin/systemctl','--system','stop',UNIT[r]+'.service']),

            'stop_owned_smoke':ssh(r,['sudo','-i','--','/usr/bin/systemctl','--system','stop',UNIT[r]+'-smoke.service']),

            'reset_failed_smoke_after_capture':ssh(r,['sudo','-i','--','/usr/bin/systemctl','--system','reset-failed',UNIT[r]+'-smoke.service']),

            'reset_failed_endpoint_after_capture':ssh(r,['sudo','-i','--','/usr/bin/systemctl','--system','reset-failed',UNIT[r]+'.service']),

            'remove_private_tls':ssh(r,call('remove-tls')),

            'stop_owned_key_reaper':ssh(r,call('stop-tls'))})

    result['trial']=['python','-B',str(HERE/'bounded.py'),'run',str(HERE/'run01-trial'),'100','@COORDINATOR@',SSH]

    result['sign_public_csrs']=['python','-B',str(HERE/'public_tls_sign.py'),str(HERE/'tls-public')]

    from scripts.performance.linux_native_finite_run import endpoint_arguments

    result['exact_trial_endpoints']={r:remote_argv(config()[r],endpoint_arguments(config(),r),SSH) for r in HOSTS}

    from tls_lifetime import start_command

    result['exact_tls_lifetime_administration']={r:start_command(r) for r in HOSTS}

    result['exact_mountpoint_administration']={

        'create_if_absent':[['sudo','-i','--','/usr/bin/mkdir','--mode=0755','--',n] for n in ['/input','/vectors']],

        'remove_only_confirmed_task_created_empty':[['sudo','-i','--','/usr/bin/rmdir','--',n] for n in ['/input','/vectors']]}

    return result

if __name__=='__main__':

    import sys

    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]))

    (HERE/'commands.json').write_text(json.dumps(commands(),indent=2))
