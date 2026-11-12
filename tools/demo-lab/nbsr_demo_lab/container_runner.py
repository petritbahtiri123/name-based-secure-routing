"""Mac host / Linux container adapter. Native Mac acceptance remains pending.

The detached helper is the lifecycle owner. Killing a Docker CLI never counts as
container cleanup. Only an exact inspected ID with matching labels/image may be
mutated; any uncertainty retains a blocking receipt for the caller.
"""
import json
import os
import platform
import re
import subprocess
import stat
import sys
import time
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nbsr_demo_lab.supervision import run_owned

OWNER = 'org.nbsr.demo-lab.run'
ENTRYPOINT = '/opt/nbsr/demo-container-worker'
SCENARIOS = {'allowed_service_a', 'unknown_service', 'stale_authority',
             'digest_mismatch', 'expired_mapping', 'shared_ip_isolation'}
WORK_SECONDS = 70  # Reserve 49 seconds for bounded CLI cleanup/observation.
TOTAL_SECONDS = 119


def _rosetta_status():
    import ctypes
    import errno
    libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    query = libc.sysctlbyname
    query.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
    query.restype = ctypes.c_int
    value = ctypes.c_int()
    size = ctypes.c_size_t(ctypes.sizeof(value))
    result = query(b'sysctl.proc_translated', ctypes.byref(value), ctypes.byref(size), None, 0)
    if result == -1 and ctypes.get_errno() == errno.ENOENT:
        return 0  # The translated-process property is absent on native Intel.
    if result != 0 or size.value != ctypes.sizeof(value) or value.value not in (0, 1):
        raise ValueError('Cannot establish native Mac execution status')
    return value.value


def native_architecture():
    if _rosetta_status() != 0:
        raise ValueError('Rosetta-translated Python is not supported; use native Python')
    architecture = {'arm64': 'arm64', 'x86_64': 'amd64'}.get(platform.machine())
    if architecture is None:
        raise ValueError('Unsupported native Mac architecture')
    return architecture


def _identity(run_id, image_id):
    if not re.fullmatch(r'demo-[0-9a-f]{32}', run_id):
        raise ValueError('invalid owned run ID')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('immutable local image ID required')


def create_args(image_id, run_id, mounts, command, architecture, uid=65532, gid=65532):
    _identity(run_id, image_id)
    if architecture not in ('amd64', 'arm64'):
        raise ValueError('unsupported native architecture')
    if command not in ([scenario] for scenario in SCENARIOS):
        raise ValueError('only a fixed scenario is accepted')
    if type(uid) is not int or type(gid) is not int or uid <= 0 or gid <= 0:
        raise ValueError('non-root host UID/GID required')
    ownership = ',uid=%d,gid=%d,mode=700' % (uid, gid)
    # Fixed mount targets and permissions; no socket, ports, credentials, or host root.
    if set(mounts) != {'source', 'artifacts'}:
        raise ValueError('source and artifacts mounts required')
    args = ['create', '--pull=never', '--platform=linux/' + architecture,
            '--name=' + run_id, '--label=' + OWNER + '=' + run_id,
            '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--pids-limit=128', '--memory=1g',
            '--cpus=2', '--user=%d:%d' % (uid, gid), '--log-driver=none', '--no-healthcheck',
            '--env=NBSR_DEMO_RUN_ID=' + run_id, '--env=NBSR_DEMO_CONTAINER=1',
            '--workdir=/work',
            '--tmpfs=/opt/nbsr-build/nbsr-demo/' + run_id + ':rw,exec,nosuid,size=128m' + ownership,
            '--tmpfs=/src/client/nbsr-go-client/demo/test-results/nbsr-demo/runtime:rw,nosuid,size=32m' + ownership,
            '--tmpfs=/work:rw,exec,nosuid,size=32m' + ownership,
            '--tmpfs=/tmp:rw,noexec,nosuid,size=64m', '--entrypoint=' + ENTRYPOINT]
    resolved = {}
    for role, target in (('source', '/source'), ('artifacts', '/artifacts')):
        path = Path(mounts[role])
        if (not path.is_absolute() or not path.is_dir() or path.is_symlink()
                or path == Path(path.anchor) or ',' in str(path) or '\n' in str(path)
                or '\0' in str(path)):
            raise ValueError('unsafe mount path')
        for parent in path.parents:
            if parent.is_symlink():
                raise ValueError('symlink in mount path')
        resolved[role] = path.resolve()
        args += ['--mount', 'type=bind,src=' + str(path.resolve()) + ',dst=' + target
                 + (',readonly' if role == 'source' else '')]
    if (resolved['source'] == resolved['artifacts']
            or resolved['source'] in resolved['artifacts'].parents
            or resolved['artifacts'] in resolved['source'].parents):
        raise ValueError('mounts must be disjoint')
    return args + [image_id, *command]


def owned_state(raw, container_id, run_id, image_id):
    data = json.loads(raw)
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError('ambiguous inspection')
    item = data[0]
    if (not re.fullmatch(r'[0-9a-f]{64}', container_id)
            or item.get('Id') != container_id or item.get('Image') != image_id
            or item.get('Config', {}).get('Labels', {}).get(OWNER) != run_id):
        raise ValueError('container ownership mismatch')
    state = item.get('State', {})
    if type(state.get('Running')) is not bool:
        raise ValueError('missing running state')
    return state


def lifecycle(spec, invoke, clock=time.monotonic, sleep=time.sleep):
    """Testable lifecycle. invoke returns (exit code, bounded stdout text)."""
    start = clock()
    cid = None
    create_attempted = False
    result = {'exit_code': None, 'cleanup': 'UNCONFIRMED', 'reason': 'launch_error',
              'container_id': None, 'image_id': spec['image_id'],
              'host_runtime': 'Mac host / Linux container'}
    directory = Path(spec['logdir'])

    def call(args):
        if clock() - start >= TOTAL_SECONDS - 9:
            raise TimeoutError('cleanup budget exhausted')
        code, output = invoke(args)
        if code != 0:
            raise RuntimeError('Docker command failed')
        return output

    def inspect():
        return owned_state(call(['container', 'inspect', cid]), cid,
                           spec['run_id'], spec['image_id'])

    try:
        image = json.loads(call(['image', 'inspect', spec['image_id']]))
        if (len(image) != 1 or image[0]['Id'] != spec['image_id']
                or image[0]['Os'] != 'linux' or image[0]['Architecture'] != spec['architecture']
                or image[0].get('Config', {}).get('Volumes')):
            raise ValueError('image identity/platform mismatch')
        create_attempted = True
        raw_id = call(create_args(spec['image_id'], spec['run_id'], spec['mounts'],
                                  spec['command'], spec['architecture'], spec.get('uid', 65532),
                                  spec.get('gid', 65532))).strip()
        if not re.fullmatch(r'[0-9a-f]{64}', raw_id):
            raise ValueError('missing exact created container ID')
        cid = raw_id
        result['container_id'] = cid
        # Durable identity precedes start; never rediscover by a generic name scan.
        (directory / 'container-id').write_text(cid, encoding='ascii')
        inspect()
        call(['container', 'start', cid])
        result['reason'] = 'timeout'
        while clock() - start < WORK_SECONDS:
            if (directory / 'cancel').exists():
                result['reason'] = 'cancelled'
                break
            state = inspect()
            if not state['Running']:
                if type(state.get('ExitCode')) is not int:
                    raise ValueError('missing exit code')
                result.update(exit_code=state['ExitCode'], reason='completed')
                break
            sleep(0.1)
    except Exception:
        result['reason'] = 'ownership_error' if cid else 'launch_error'
    finally:
        if cid is None and create_attempted:
            try:
                recovered = json.loads(call(['container', 'inspect', spec['run_id']]))
                candidate = recovered[0]['Id']
                owned_state(json.dumps(recovered), candidate, spec['run_id'], spec['image_id'])
                cid = candidate
                result['container_id'] = cid
                (directory / 'container-id').write_text(cid, encoding='ascii')
            except Exception:
                pass
        if cid:
            try:
                state = inspect()  # Revalidate identity immediately before mutation.
                if state['Running']:
                    call(['container', 'kill', '--signal=KILL', cid])
                state = inspect()
                if state['Running']:
                    raise ValueError('container still running')
                call(['container', 'rm', cid])  # No force, volumes, or global cleanup.
                remaining = call(['container', 'ls', '--all', '--no-trunc',
                                  '--filter=id=' + cid, '--format={{.ID}}']).strip()
                if remaining:
                    raise ValueError('container removal unconfirmed')
                result['cleanup'] = 'CLEAN'
            except Exception:
                result['cleanup'] = 'UNCONFIRMED'
        if not create_attempted:
            result['cleanup'] = 'CLEAN'  # No create command was attempted.
        # Missing ID after create may mean the daemon created a container anyway.
        result['elapsed'] = clock() - start
    return result


def _helper(spec_path):
    spec = json.loads(Path(spec_path).read_text(encoding='utf-8'))
    directory = Path(spec['logdir'])
    number = 0

    def invoke(args):
        nonlocal number
        number += 1
        logs = directory / ('cli-%04d' % number)
        outcome = run_owned([spec['docker_exe'], '--host', spec['docker_host'], *args], directory,
                            {k: v for k, v in os.environ.items() if not k.startswith('DOCKER_')},
                            logs, timeout=3)
        if outcome['cleanup'] != 'CLEAN' or outcome['reason'] != 'completed':
            raise RuntimeError('Docker CLI outcome unconfirmed')
        return outcome['exit_code'], (logs / 'stdout.log').read_text(encoding='utf-8')

    result = lifecycle(spec, invoke)
    temporary = directory / 'result.tmp'
    temporary.write_text(json.dumps(result), encoding='utf-8')
    temporary.replace(directory / 'result.json')


def local_docker_host(environ):
    """Pin local Desktop socket explicitly; never follow context-selected remotes."""
    if environ.get('DOCKER_CONTEXT') not in (None, '', 'default', 'desktop-linux'):
        raise ValueError('non-default Docker context is not authorized')
    allowed = [Path.home() / '.docker/run/docker.sock', Path('/var/run/docker.sock')]
    configured = environ.get('DOCKER_HOST')
    if configured:
        if configured not in ('unix://' + str(path) for path in allowed):
            raise ValueError('only a local Docker Desktop Unix socket is authorized')
        candidates = [Path(configured[7:])]
    else:
        candidates = allowed
    for path in candidates:
        try:
            if stat.S_ISSOCK(path.stat().st_mode):
                return 'unix://' + str(path)
        except OSError:
            pass
    raise ValueError('local Docker Desktop socket is unavailable')


def run_container(docker_exe, image_id, run_id, mounts, command, logdir, cancel):
    """Launch detached lifecycle owner; caller must latch UNCONFIRMED across runs.

    Requires an already prepared audited image; performs no pulls/builds. macOS
    only. The caller validates source/binary manifests before and after execution.
    """
    if sys.platform != 'darwin':
        raise ValueError('container adapter currently targets macOS hosts only')
    architecture = native_architecture()
    if not Path(docker_exe).is_absolute() or not Path(docker_exe).is_file():
        raise ValueError('existing absolute Docker executable required')
    uid, gid = os.getuid(), os.getgid()
    docker_host = local_docker_host(os.environ)
    create_args(image_id, run_id, mounts, command, architecture, uid, gid)
    directory = Path(logdir).resolve()
    for mounted in mounts.values():
        mounted = Path(mounted).resolve()
        if directory == mounted or mounted in directory.parents or directory in mounted.parents:
            raise ValueError('watchdog controls must be disjoint from container mounts')
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    spec = dict(docker_exe=str(docker_exe), image_id=image_id, run_id=run_id,
                mounts={k: str(v) for k, v in mounts.items()}, command=command,
                architecture=architecture, logdir=str(directory), uid=uid, gid=gid, docker_host=docker_host)
    path = directory / 'request.json'
    path.write_text(json.dumps(spec), encoding='utf-8')
    # Isolated helper survives UI/API process death and owns its own monotonic limit.
    # No Popen pipe or inherited socket connects its lifetime to the web server.
    helper = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), str(path)],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    start = time.monotonic()
    while time.monotonic() - start < TOTAL_SECONDS:
        if cancel is not None and cancel.is_set():
            (directory / 'cancel').touch(exist_ok=True)
        receipt = directory / 'result.json'
        if receipt.is_file():
            result = json.loads(receipt.read_text(encoding='utf-8'))
            helper.wait(timeout=1)
            return result
        if helper.poll() is not None:
            break
        time.sleep(0.05)
    (directory / 'cancel').touch(exist_ok=True)
    return dict(exit_code=None, cleanup='UNCONFIRMED', reason='ownership_error',
                container_id=(directory / 'container-id').read_text() if (directory / 'container-id').exists() else None,
                image_id=image_id, elapsed=time.monotonic() - start,
                host_runtime='Mac host / Linux container')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(2)
    _helper(sys.argv[1])
