"""External recipe only; not executed or accepted as a benchmark result."""
import hashlib
import json
import pathlib
import platform
import shutil
import subprocess

root = pathlib.Path('/evidence')
sha = '3644c324a535586e89af72a8c9796e8d58fadf48'
def save(name, value):
    (root / name).write_text(json.dumps(value, indent=2) + '\n')

assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == sha
assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], text=True)
assert platform.python_version() == '3.14.6'
for executable in ('git', 'taskset', 'lscpu'):
    assert shutil.which(executable), executable
provenance = pathlib.Path('/opt/nbsr/provenance')
shutil.copytree(provenance, root / 'build-provenance')
assert 'rustc 1.97.1' in (provenance / 'rustc.txt').read_text()
save('smoke-matrix.json', {'schema': 'nbsr-linux-loopback-v1', 'cores': [1],
     'workloads': [{'payload_bytes': 1024, 'streams': 64, 'outstanding': 1}],
     'warmup_seconds': 3, 'duration_seconds': 20})
names = ('perf_direct_peer', 'perf_rust_source', 'wp8_interop_server')
save('build-manifest.json', {'source_sha': sha, 'build_profile': 'release',
     'binary_sha256': {name: hashlib.sha256((pathlib.Path('/opt/nbsr/bin') / name).read_bytes()).hexdigest() for name in names},
     'build_commands': ['CARGO_TARGET_DIR=/build cargo build --locked --release --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_direct_peer --bin perf_rust_source --bin wp8_interop_server'],
     'toolchains': {'rustc': (provenance / 'rustc.txt').read_text(), 'cargo': (provenance / 'cargo.txt').read_text(), 'python': platform.python_version()}})
cgroups = {}
for name in ('cpu.max', 'cpuset.cpus.effective', 'memory.max', 'cpu.stat'):
    path = pathlib.Path('/sys/fs/cgroup') / name
    cgroups[name] = path.read_text() if path.exists() else None
save('container-scope.json', {'classification': 'DOCKER_DESKTOP_LINUX_VM_LOOPBACK_SMOKE_ONLY',
     'physical_server_validation': 'NOT_RUN', 'physical_core_topology': 'NOT_ESTABLISHED',
     'guest_topology_only': True, 'cgroup_v2': cgroups})
result = subprocess.run(['python3', '-m', 'scripts.performance.linux_loopback',
    '--matrix', str(root / 'smoke-matrix.json'), '--binaries', '/opt/nbsr/bin',
    '--build-manifest', str(root / 'build-manifest.json'), '--output', str(root / 'run')])
save('wrapper-result.json', {'runner_exit_code': result.returncode, 'scope': 'container software smoke'})
raise SystemExit(result.returncode)
