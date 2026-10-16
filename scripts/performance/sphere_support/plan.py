"""Pure command construction. Importing this module performs no operations."""

import shlex



SHA = '47d2ae41df49fedd21768db5fa6be71377acebf3'

PIN = '6ccc7a97451ffc424e1f4f7dfdeb61d125406f35b7962d4cd24d6b3ee735049d'

RUN = 'nbsr-sphere-20261016-07'

ROOT = '/home/benchmark-user/nbsr-sphere-20261016-01'

CONTROL = ROOT + '/control07'

HOSTS = {'source': 'source.example.invalid', 'destination': 'destination.example.invalid'}

IPS = {'source': '192.0.2.2', 'destination': '192.0.2.1'}

UNIT = {r: RUN + '-' + r for r in HOSTS}



def config():

    c = dict(schema='nbsr-native-finite-coordinator-v1', source_sha=SHA,

             path='nbsr', payload=1024, streams=2, depth=1, post_close_reports=True,

             debug_correctness_manifest_sha256=PIN)

    for r in HOSTS:

        c[r] = dict(transport='ssh', host=HOSTS[r], checkout=ROOT+'/repo',

                    binaries=ROOT+'/payload/bin', build_manifest=ROOT+'/payload/inputs/debug-build-manifest.json',

                    authority='/run/'+UNIT[r]+'-tls', output=ROOT+'/evidence/run07/'+r,

                    bind=IPS[r]+':0', cores=1)

    return c



def service(role, argv, *, smoke=False):

    if role not in HOSTS or not argv or any(not isinstance(x,str) or '\x00' in x or '\n' in x for x in argv):

        raise ValueError('role/argv')

    props = ['CPUQuota=100%', 'MemoryMax=536870912', 'MemorySwapMax=0',

             'TasksMax=128', 'RuntimeMaxSec='+('10' if smoke else '65'),

             'TimeoutStopSec=5', 'KillMode=control-group', 'SendSIGKILL=yes',

             'LimitCORE=0', 'LimitFSIZE=16777216', 'UMask=0077', 'PrivateUsers=yes', 'PrivateMounts=yes',

             'NoNewPrivileges=yes', 'CapabilityBoundingSet=', 'AmbientCapabilities=',

             'Slice=system.slice', 'WorkingDirectory='+ROOT+'/repo',

             'BindReadOnlyPaths='+ROOT+'/repo:/input',

             'BindReadOnlyPaths='+ROOT+'/repo/vectors:/vectors',

             'BindReadOnlyPaths='+ROOT+'/repo',

             'Environment=PATH='+ROOT+'/venv/bin:/usr/bin:/bin',

             'Environment=PYTHONDONTWRITEBYTECODE=1', 'Environment=GIT_OPTIONAL_LOCKS=0']

    if not smoke:

        props += ['ExecStopPost='+ROOT+'/venv/bin/python -B '+CONTROL+'/remote_ops.py receipt '+role]

    cmd=['sudo','-i','--','/usr/bin/systemd-run','--system','--uid=1001','--gid=1001','--quiet','--pipe','--wait',

         '--unit='+UNIT[role]+('-smoke' if smoke else '')]

    for p in props: cmd += ['--property='+p]

    return cmd + ['--', *argv]



def remote_argv(target, argv, ssh_config):

    roles=[r for r in HOSTS if target == config()[r]]

    if len(roles)!=1: raise ValueError('unapproved target')

    role=roles[0]

    if argv[:4]==['python3','-B','-m','scripts.performance.linux_native_finite_endpoint']:

        from scripts.performance.linux_native_finite_run import endpoint_arguments

        if argv!=endpoint_arguments(config(),role):raise ValueError('unapproved endpoint arguments')

        command=service(role,[ROOT+'/venv/bin/python','-B',CONTROL+'/peer_guard.py',*argv[1:]])

    else:

        # Only collector tar / validation true are supported outside the owned unit.

        if not (argv==['true'] or argv==['tar','-C',target['output'],'-cf','-','.']):

            raise ValueError('unapproved remote operation')

        command=['/usr/bin/timeout','--kill-after=2','15',*argv]

    return ['ssh','-F',str(ssh_config),'-T','--',HOSTS[role],shlex.join(command)]



def cleanup_pass(properties, *, expected_unit):

    expected={'Id':expected_unit+'.service','ActiveState':'inactive','SubState':'dead',

              'Result':'success','ExecMainCode':'1','ExecMainStatus':'0',

              'MemoryMax':'536870912','TasksMax':'128'}

    return all(properties.get(k)==v for k,v in expected.items())



def final_gate(result, receipts):

    from scripts.performance import native_debug_correctness as debug

    if result.get('status')!=debug.status('PASS_CONTROLLED_FINITE_PAIR',PIN):raise ValueError('paired result')

    if set(receipts)!=set(HOSTS):raise ValueError('missing receipt')

    for role,row in receipts.items():

        expected={'role':role,'unit':UNIT[role]+'.service','SERVICE_RESULT':'success',

                  'EXIT_CODE':'exited','EXIT_STATUS':'0','cgroup_absent':True,

                  'tls_cleanup':'REMOVED','tls_path_absent':True,

                  'manager':'system','uid':1001,'gid':1001,'mountpoint_cleanup':'CONFIRMED'}

        if any(row.get(k)!=v for k,v in expected.items()):raise ValueError('unsuccessful or missing cleanup')

    return 'PASS_DEBUG_CORRECTNESS_WITH_INDEPENDENT_CGROUP_ABSENCE'
