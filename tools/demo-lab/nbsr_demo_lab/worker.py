"""One positive local Go/Rust lifecycle, always invoked inside the owned supervisor."""
import ipaddress
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

from .evidence import BODY
from .setup import digest, environment, private_path, validate_build


def endpoint(value, https=False):
    if https:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or parsed.username or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('ACP endpoint rejected')
        host, port = parsed.hostname, parsed.port
    else:
        host, number = value.rsplit(':', 1)
        host, port = host.strip('[]'), int(number)
    if not ipaddress.ip_address(host).is_loopback or not 0 < port < 65536:
        raise ValueError('Non-loopback endpoint rejected')
    return host, port


def read_ready(path, proc, schema=None):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError('Component exited before readiness')
        if path.is_file() and path.stat().st_size <= 65536:
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
                normalized = {k.lower(): v for k, v in value.items()}
                if schema is None or normalized.get('schema') == schema:
                    return normalized
            except (ValueError, UnicodeError):
                pass
        time.sleep(0.05)
    raise TimeoutError('Readiness deadline exceeded')


def request(proxy):
    address = endpoint(proxy)
    with socket.create_connection(address, timeout=10) as sock:
        sock.settimeout(15)
        sock.sendall(b'CONNECT service-a.nbsr.test:8080 HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\n\r\n')
        headers = b''
        while not headers.endswith(b'\r\n\r\n') and len(headers) < 4096:
            chunk = sock.recv(1)
            if not chunk:
                raise ValueError('Proxy closed before CONNECT')
            headers += chunk
        if not headers.startswith(b'HTTP/1.1 200 ') or not headers.endswith(b'\r\n\r\n'):
            raise ValueError('CONNECT rejected')
        sock.sendall(b'GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nUser-Agent: nbsr-demo-lab\r\nConnection: close\r\n\r\n')
        sock.shutdown(socket.SHUT_WR)
        response = b''
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                break
            response += chunk
            if len(response) > 16384:
                raise ValueError('Application response exceeded bound')
    if not response.startswith(b'HTTP/1.1 200 ') or b'\r\n\r\n' not in response:
        raise ValueError('Invalid backend response')
    body = response.split(b'\r\n\r\n', 1)[1].decode('ascii').rstrip('\r\n')
    if body != BODY:
        raise ValueError('Unexpected application payload')
    return body


def run(request_file):
    if platform.system() == 'Darwin':
        raise ValueError('macOS live backend is blocked pending secure executable launch support')
    container = platform.system() == 'Linux' and os.environ.get('NBSR_DEMO_CONTAINER') == '1'
    if platform.system() != 'Windows' and not container:
        raise ValueError('Live runner currently supports Windows only')
    request_data = json.loads(private_path(request_file).read_text(encoding='utf-8'))
    if set(request_data) != {'repo', 'state', 'run_id', 'manifest'}:
        raise ValueError('Invalid worker request')
    repo, state = Path(request_data['repo']), Path(request_data['state'])
    run_id = request_data['run_id']
    import re
    if not re.fullmatch(r'demo-[0-9a-f]{32}', run_id):
        raise ValueError('Invalid run ID')
    run_dir = private_path(state / 'runs' / run_id)
    if private_path(request_file) != run_dir / 'worker.json':
        raise ValueError('Worker request identity mismatch')
    manifest = validate_build(repo, state)
    if manifest != request_data['manifest']:
        raise ValueError('Build manifest changed before worker execution')
    demo = repo / 'client/nbsr-go-client/demo'
    relative = 'test-results/nbsr-demo/runtime/' + run_id
    runtime = private_path(demo / relative)
    runtime.mkdir(parents=True, exist_ok=False, mode=0o700)
    build_parent = Path('/opt/nbsr-build/nbsr-demo') if container else Path('C:/NBSR-build/nbsr-demo')
    build_root = private_path(build_parent / run_id)
    if container:
        if not build_root.is_dir() or any(build_root.iterdir()):
            raise ValueError('Fresh run-specific container tmpfs required')
    else:
        build_root.mkdir(parents=True, exist_ok=False, mode=0o700)
    executables = {}
    for role in ('authority', 'client', 'backend', 'destination', 'fixturegen'):
        source = Path(manifest['artifacts'][role]['path'])
        dest = build_root / source.name
        shutil.copy2(source, dest)
        if digest(dest) != manifest['artifacts'][role]['sha256']:
            raise ValueError('Copied executable hash mismatch')
        executables[role] = str(dest)
    for directory in ('authority', 'client', 'destination', 'readiness', 'evidence'):
        (runtime / directory).mkdir(mode=0o700)
    procs = []
    def start(role, args, cwd):
        proc = subprocess.Popen([executables[role], *map(str, args)], cwd=cwd, env=environment(),
                                stdin=subprocess.DEVNULL, close_fds=True)
        procs.append(proc)
        return proc
    try:
        bootstrap = relative + '/client/bootstrap'
        admission = relative + '/destination/runtime-admission.conf'
        authority = start('authority', ['--listen', '127.0.0.1:0', '--runtime', relative,
                                       '--client-bootstrap', bootstrap, '--runtime-admission', admission], demo)
        boot = read_ready(runtime / 'client/bootstrap/client-bootstrap.json', authority, 'nbsr-demo-client-bootstrap-v1')
        endpoint(boot['endpoint'], https=True)
        transport = runtime / 'destination/authority'
        generator = start('fixturegen', ['--output', str(transport)], repo)
        if generator.wait(timeout=10) != 0:
            raise RuntimeError('Transport fixture creation failed')
        backend_map = runtime / 'destination/backend.map'
        backend_map.write_text('NBSR-DEMO-BACKEND-MAP-v1\nservice_id=nbsr-demo-service-a-v1\nexecutable=' +
                               executables['backend'].replace('\\', '/') + '\nsha256=' +
                               manifest['artifacts']['backend']['sha256'] + '\n', encoding='utf-8')
        ready = runtime / 'readiness/destination.json'
        gate = runtime / 'readiness/destination-start.gate'
        ack = runtime / 'destination/completion.ack'
        result = runtime / 'destination/result.json'
        destination = start('destination', ['--ready', ready, '--result', result, '--authority-dir', transport,
                            '--completion-ack', ack, '--demo-backend-map', backend_map,
                            '--runtime-admission', runtime / 'destination/runtime-admission.conf', '--demo-start-gate', gate], repo)
        destination_ready = read_ready(ready, destination)
        endpoint(destination_ready['endpoint'])
        if destination_ready.get('alpn') != 'nbsr-quic-1':
            raise ValueError('Destination ALPN mismatch')
        config = {'schema': 'nbsr-demo-config-v1', 'production_semantic': {'alpn': 'nbsr-quic-1', 'quic_version': 'v1', 'tls_version': '1.3', 'stream_credit_profile': 'nbsr-stream-credit-1'},
                  'client': {'service_fixture': 'testdata/service-a.json', 'shared_synthetic_ip': '127.0.0.2', 'proxy_endpoint': '127.0.0.1:0', 'acp_endpoint': boot['endpoint'], 'destination_readiness': relative + '/readiness/destination.json', 'application_transport': 'tcp', 'service_port': 8080},
                  'acp_fixture': {'classification': 'DEMO FIXTURE \u2014 NOT PRODUCTION AUTHORITY', 'public_fixture': bootstrap + '/client-bootstrap.json'},
                  'destination': {'authority_fixture': relative + '/destination/authority', 'rust_artifact': {'path': executables['destination'], 'sha256': manifest['artifacts']['destination']['sha256']}},
                  'evidence': {'directory': relative + '/evidence'}, 'secrets': {'directory': bootstrap},
                  'timeouts': {'handshake_seconds': 5, 'operation_seconds': 15}, 'limits': {'max_proxy_connections': 16, 'max_request_bytes': 4096}}
        (runtime / 'client/config.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        client = start('client', ['--config', relative + '/client/config.json', '--bootstrap', bootstrap,
                                '--ready', relative + '/readiness/client.json', '--runtime-root', relative, '--build-root', build_root], demo)
        client_ready = read_ready(runtime / 'readiness/client.json', client, 'nbsr-demo-client-ready-v1')
        if client_ready.get('state') != 'ready':
            raise ValueError('Client not ready')
        gate.touch(exist_ok=False)
        body = request(client_ready['proxy'])
        ack.write_text('complete', encoding='ascii')
        deadline = time.monotonic() + 10
        while not result.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        with result.open('rb') as stream:
            raw = stream.read(4 * 1024**2 + 1)
        if len(raw) > 4 * 1024**2:
            raise ValueError('Destination result exceeds bound')
        (run_dir / 'worker-destination.json').write_bytes(raw)
        (run_dir / 'worker-application.json').write_text(json.dumps({'body': body}), encoding='utf-8')
    finally:
        for proc in reversed(procs):
            if proc.poll() is None:
                proc.terminate()
        for proc in reversed(procs):
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        # Outer supervisor independently confirms the full owned tree is gone.
