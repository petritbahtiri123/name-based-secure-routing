"""Explicit preparation/build; check never installs, fetches, or starts a demo."""
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOTS = ('client/nbsr-go-client', 'interop/nbsr-go-peer', 'crates/nbsr-transport', 'tools/demo-lab', 'scripts/demo', 'vectors')
EXCLUDE = {'.git', '.state', '__pycache__', '.pytest_cache', 'target', 'test-results', '.venv', 'node_modules', 'runtime', 'credentials', 'archives', 'archive'}
SOURCE_SUFFIXES = {'.go', '.rs', '.toml', '.lock', '.mod', '.sum', '.py', '.json', '.html', '.js', '.css', '.ps1', '.sh', '.txt', '.cbor', '.cose', '.bin', '.frame', '.hex'}
REQUIRED = ('client/nbsr-go-client/demo/go.mod', 'client/nbsr-go-client/go.mod',
            'interop/nbsr-go-peer/go.mod', 'crates/nbsr-transport/Cargo.lock',
            'client/nbsr-go-client/demo/testdata/service-a.json', 'tools/demo-lab/fixturegen/go.mod')
INSTALL = {
    'Go 1.26.5 or compatible newer installed toolchain': 'https://go.dev/dl/',
    'Rust 1.97.1 historical baseline (no automatic upgrade)': 'https://rust-lang.org/tools/install/',
    'Windows MSVC and SDK': 'https://rust-lang.github.io/rustup/installation/windows-msvc.html',
    'macOS Apple Command Line Tools': 'https://developer.apple.com/documentation/xcode/installing-the-command-line-tools',
    'Python 3.12-3.14 (3.13 recommended)': 'https://www.python.org/downloads/',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def private_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            if item.is_symlink() or getattr(item.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('Symlink/reparse path is not accepted')
    return path


def environment():
    env = os.environ.copy()
    env.update(GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off', GOWORK='off',
               CARGO_NET_OFFLINE='true', GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0',
               PYTHONDONTWRITEBYTECODE='1', GOMAXPROCS='2', CARGO_BUILD_JOBS='2')
    return env


def command(exe, args, cwd):
    result = subprocess.run([exe, *args], cwd=cwd, env=environment(), text=True,
                            capture_output=True, timeout=5, creationflags=0x08000000 if os.name == 'nt' else 0)
    if result.returncode:
        raise ValueError(f'{Path(exe).name} inspection failed')
    return result.stdout.strip()


def inventory(repo):
    output = {}
    for name in ROOTS:
        root = repo / name
        private_path(root)
        for base, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE)
            for directory in dirs:
                private_path(Path(base) / directory)
            for name in sorted(files):
                path = Path(base) / name
                if path.suffix in SOURCE_SUFFIXES or name.endswith(('Dockerfile', '.dockerignore')) or name == 'demo-container-worker':
                    private_path(path)
                    output[path.relative_to(repo).as_posix()] = digest(path)
    if not output:
        raise ValueError('Source inventory empty')
    return output


def check(repo):
    repo = private_path(repo).resolve()
    issues = []
    host = platform.system()
    machine = platform.machine().lower()
    if host not in ('Windows', 'Darwin') or machine not in ('amd64', 'x86_64', 'arm64', 'aarch64'):
        issues.append('Only Windows x64 and native macOS arm64/x86_64 are targeted')
    if host == 'Windows' and machine not in ('amd64', 'x86_64'):
        issues.append('Windows ARM is not a supported target')
    if not (3, 12) <= sys.version_info[:2] < (3, 15):
        issues.append('Python must be >=3.12,<3.15')
    missing = [p for p in REQUIRED if not (repo / p).is_file()]
    if missing:
        issues.append('Required source absent; use full checkout (no automatic sparse restore): ' + ', '.join(missing))
    if (repo / 'client/nbsr-go-client/demo/test-results/nbsr-demo/runtime/active.lock').exists():
        issues.append('Historical demo lock exists; reconcile its owner before preparation or execution')
    if host == 'Darwin':
        from .container_runner import native_architecture
        try:
            native_architecture()
        except (ValueError, OSError):
            issues.append('Native Mac execution could not be established; Rosetta Python is not supported')
        tools = {name: shutil.which(name) for name in ('git', 'docker')}
        versions = {'python': platform.python_version()}
        commit = None
        for name, path in tools.items():
            if not path:
                issues.append('Missing tool: ' + name)
            else:
                try:
                    versions[name] = command(path, ['--version'], repo)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    issues.append('Cannot inspect ' + name)
        if tools['git']:
            try:
                commit = command(tools['git'], ['rev-parse', 'HEAD'], repo)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                issues.append('Repository provenance unavailable')
        if shutil.disk_usage(repo).free < 8 * 1024**3:
            issues.append('At least 8 GiB free disk required')
        return {'ready_for_build': False, 'host_prerequisites_ok': not issues, 'issues': issues, 'tools': tools, 'toolchain': versions,
                'source_commit': commit, 'platform': f'{host}-{machine}',
                'execution': 'Mac host / Linux container',
                'install_sources': {'Docker Desktop': 'https://docs.docker.com/desktop/setup/install/mac-install/'},
                'validation': 'Host prerequisites only; reviewed image, local engine and native Mac acceptance unverified'}
    tools = {name: shutil.which(name) for name in ('git', 'go', 'cargo', 'rustc')}
    for name, path in tools.items():
        if not path:
            issues.append(f'Missing tool: {name}')
    versions = {'python': platform.python_version()}
    commit = None
    for name, args in (('git', ['--version']), ('go', ['version'])):
        if tools[name]:
            try:
                versions[name] = command(tools[name], args, repo)
            except (ValueError, subprocess.TimeoutExpired):
                issues.append(f'Cannot inspect {name}')
    if 'go' in versions:
        match = re.search(r'go(\d+)\.(\d+)\.(\d+)', versions['go'])
        if not match or tuple(map(int, match.groups())) < (1, 26, 5):
            issues.append('Installed Go must be at least 1.26.5; auto toolchain download disabled')
    # Resolve rustup shims read-only before invoking actual tools, avoiding auto-install.
    rustup = shutil.which('rustup')
    for name in ('rustc', 'cargo'):
        if tools[name]:
            try:
                actual = command(rustup, ['which', name], repo) if rustup else tools[name]
                if not Path(actual).is_file():
                    raise ValueError()
                tools[name] = actual
                versions[name] = command(actual, ['--version'], repo)
            except (ValueError, subprocess.TimeoutExpired):
                issues.append(f'Installed {name} unavailable; install explicitly first')
    if tools['git']:
        try:
            commit = command(tools['git'], ['rev-parse', 'HEAD'], repo)
            branch = command(tools['git'], ['branch', '--show-current'], repo)
            if branch != 'codex/nbsr-v3-wp0-wp1':
                issues.append('Use development branch codex/nbsr-v3-wp0-wp1')
        except (ValueError, subprocess.TimeoutExpired):
            issues.append('Repository provenance unavailable')
    if shutil.disk_usage(repo).free < 8 * 1024**3:
        issues.append('At least 8 GiB free disk required')
    if host == 'Darwin':
        try:
            command('/usr/bin/xcrun', ['--find', 'clang'], repo)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            issues.append('Apple Command Line Tools/SDK not selected; install explicitly')
    windows = None
    if host == 'Windows':
        from .windows_setup import discover
        try:
            windows = discover(repo, command)
            if not windows['complete']:
                issues.append('MSVC x64 compiler/linker/headers/libraries or Windows SDK inventory incomplete; install explicitly')
        except (OSError, ValueError, subprocess.TimeoutExpired):
            issues.append('Cannot inspect installed MSVC/Windows SDK; no readiness claim')
    return {'ready_for_build': not issues, 'issues': issues, 'tools': tools, 'toolchain': versions,
            'source_commit': commit, 'platform': f'{host}-{machine}', 'install_sources': INSTALL,
            'windows_tooling': windows, 'staging_write_access': 'NOT_PROBED: build performs an owned write/read/delete check',
            'validation': 'Preliminary read-only admission only; build success, cache completeness, staging permissions and clean-machine setup are not established'}


def guarded(argv, cwd, env, log_dir):
    from .supervision import run_owned
    free = shutil.disk_usage(cwd).free
    if free < 8 * 1024**3:
        raise ValueError('8 GiB free required before build/preparation')
    cancel, stop = threading.Event(), threading.Event()
    def monitor():
        while not stop.wait(0.2):
            remaining = shutil.disk_usage(cwd).free
            if remaining < 6 * 1024**3 or free - remaining > 2 * 1024**3:
                cancel.set()
                return
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        result = run_owned(argv, cwd, env, log_dir, timeout=95, cancel=cancel)
    finally:
        stop.set()
        thread.join(1)
    if result['exit_code'] != 0 or result['cleanup'] != 'CLEAN' or result['reason'] != 'completed':
        raise RuntimeError(f"Stage stopped: {result}. Logs retained in {log_dir}")


def prepare(repo, state, *, allow_downloads=False):
    if platform.system() == 'Darwin':
        raise ValueError('Mac uses explicit pinned container preparation; see tools/demo-lab/container/README.md')
    report = check(repo)
    if not report['ready_for_build']:
        return report
    if not allow_downloads:
        return {'download_plan': ['Go modules pinned by go.mod/go.sum', 'Cargo dependencies pinned by Cargo.lock'],
                'effects': 'Explicit downloads into existing Go/Cargo caches; no global tool install, no keys, no demo.',
                'next': 'prepare --allow-downloads after reviewing official prerequisites'}
    from tempfile import TemporaryDirectory
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = environment()
    env.update(GOPROXY='https://proxy.golang.org', GOSUMDB='sum.golang.org', CARGO_NET_OFFLINE='false')
    # Mirrors avoid dependency tools modifying the working source manifests.
    with TemporaryDirectory(prefix='prepare-', dir=state) as temp:
        mirror = Path(temp)
        for name in ROOTS[:3]:
            shutil.copytree(repo / name, mirror / name, ignore=shutil.ignore_patterns(*EXCLUDE))
        for i, name in enumerate(('client/nbsr-go-client/demo', 'client/nbsr-go-client', 'interop/nbsr-go-peer')):
            guarded([report['tools']['go'], 'mod', 'download'], mirror / name, env,
                    state / ('prepare-go-' + str(i) + '-' + uuid.uuid4().hex))
        guarded([report['tools']['cargo'], 'fetch', '--locked', '--manifest-path', str(mirror / 'crates/nbsr-transport/Cargo.toml')],
                mirror, env, state / ('prepare-rust-' + uuid.uuid4().hex))
    return {'prepared': True, 'validation': 'Dependencies fetched; no runtime validation'}


def build(repo, state):
    if platform.system() == 'Darwin':
        raise ValueError('Mac builds the reviewed Linux image; see tools/demo-lab/container/README.md')
    report = check(repo)
    if not report['ready_for_build']:
        raise ValueError('; '.join(report['issues']))
    if platform.system() == 'Windows':
        from .windows_setup import probe_staging
        probe_staging()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    build_dir = state / ('build-' + uuid.uuid4().hex)
    build_dir.mkdir(mode=0o700)
    env = environment()
    env['CARGO_TARGET_DIR'] = str(private_path(os.environ.get('CARGO_TARGET_DIR', state / 'cargo-target')))
    env['GOFLAGS'] = '-mod=readonly'
    before = inventory(repo)
    ext = '.exe' if os.name == 'nt' else ''
    artifacts = {}
    jobs = [('authority', 'client/nbsr-go-client/demo', './cmd/nbsr-demo-authority', False),
            ('client', 'client/nbsr-go-client/demo', './cmd/nbsr-demo-client', False),
            ('backend', 'client/nbsr-go-client/demo', './cmd/nbsr-demo-backend', False),
            ('fixturegen', 'tools/demo-lab/fixturegen', '.', False),
            ('test-client', 'client/nbsr-go-client/demo', './internal/client', True),
            ('test-corestate', 'client/nbsr-go-client', './internal/corestate', True),
            ('test-resolution', 'client/nbsr-go-client', './internal/resolution', True)]
    for name, cwd, target, test in jobs:
        destination = build_dir / (name + ext)
        args = ['test', '-c'] if test else ['build']
        guarded([report['tools']['go'], *args, '-p', '2', '-o', str(destination), target], repo / cwd, env, build_dir / ('log-' + name))
        artifacts[name] = {'path': str(destination), 'sha256': digest(destination)}
    guarded([report['tools']['cargo'], 'build', '--locked', '--offline', '--release', '--jobs', '2',
             '--manifest-path', str(repo / 'crates/nbsr-transport/Cargo.toml'), '--bin', 'wp8_interop_server'],
            repo, env, build_dir / 'log-rust')
    destination = build_dir / ('destination' + ext)
    shutil.copy2(Path(env['CARGO_TARGET_DIR']) / 'release' / ('wp8_interop_server' + ext), destination)
    artifacts['destination'] = {'path': str(destination), 'sha256': digest(destination)}
    if before != inventory(repo):
        raise ValueError('Source changed during build; evidence not accepted')
    manifest = {'artifacts': artifacts, 'source_hashes': before, 'source_commit': report['source_commit'],
                'platform': report['platform'], 'toolchain': report['toolchain']}
    pending = state / 'build.pending.json'
    pending.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    pending.replace(state / 'build.json')
    return {'built': True, 'validation': 'Built only; live/native acceptance still required'}


def validate_build(repo, state):
    if (repo / 'client/nbsr-go-client/demo/test-results/nbsr-demo/runtime/active.lock').exists():
        raise ValueError('Historical demo lock exists; reconcile its owner first')
    container = platform.system() == 'Linux' and os.environ.get('NBSR_DEMO_CONTAINER') == '1'
    if container and (repo != Path('/src') or state != Path('/work')):
        raise ValueError('Unexpected immutable container roots')
    path = private_path(Path('/opt/nbsr-image/build.json') if container else state / 'build.json')
    if not path.is_file():
        raise ValueError('Prepared binaries missing. Run check, prepare and build in terminal first.')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or set(manifest) != {'artifacts', 'source_hashes', 'source_commit', 'platform', 'toolchain'}:
        raise ValueError('Invalid build manifest schema')
    if not isinstance(manifest['artifacts'], dict) or set(manifest['artifacts']) != {'authority', 'client', 'backend', 'fixturegen', 'destination', 'test-client', 'test-corestate', 'test-resolution'}:
        raise ValueError('Build manifest has incomplete artifact roles')
    if manifest['source_hashes'] != inventory(repo):
        raise ValueError('Source differs from build inventory; rebuild explicitly')
    if manifest['platform'] != f'{platform.system()}-{platform.machine().lower()}':
        raise ValueError('Prepared platform differs from current host')
    for value in manifest['artifacts'].values():
        binary = private_path(value['path'])
        binary_root = Path('/opt/nbsr-build/nbsr-demo/image') if container else state.resolve()
        if not binary.is_relative_to(binary_root) or digest(binary) != value['sha256']:
            raise ValueError('Binary path/hash mismatch')
    return manifest
