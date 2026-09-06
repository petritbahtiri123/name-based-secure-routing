import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import run_b3_v2 as runner


def test_explicit_platform_binary_names_keep_windows_default():
    assert runner.binary_names('windows') == {'rust': 'perf_rust_source.exe', 'server': 'wp8_interop_server.exe'}
    assert runner.binary_names('linux') == {'rust': 'perf_rust_source', 'server': 'wp8_interop_server'}
    with pytest.raises(ValueError):
        runner.binary_names('other')


def test_linux_manifest_binds_actual_binary_bytes_and_declared_source(tmp_path):
    binaries = {}
    for role, name in runner.binary_names('linux').items():
        binaries[role] = tmp_path / name
        binaries[role].write_bytes(role.encode())
    manifest = dict(source_sha='a' * 40, build_profile='release',
        binary_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries.values()},
        build_commands=['retained immutable image build'], toolchains={'rust': 'retained build metadata'})
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest))
    assert runner.validate_linux_manifest(path, binaries)['source_sha'] == 'a' * 40
    binaries['rust'].write_bytes(b'changed')
    with pytest.raises(ValueError):
        runner.validate_linux_manifest(path, binaries)


def test_linux_manifest_cannot_omit_build_metadata(tmp_path):
    path = tmp_path / 'manifest.json'
    path.write_text('{}')
    with pytest.raises(ValueError):
        runner.validate_linux_manifest(path, {})


@pytest.mark.parametrize('platform_name', ['windows', 'linux'])
def test_linux_executes_verified_original_windows_keeps_retained(tmp_path, monkeypatch, platform_name):
    from scripts.performance import b3_linux
    target = tmp_path / 'target'
    (target / 'release').mkdir(parents=True)
    binaries = {}
    for role, name in runner.binary_names(platform_name).items():
        binaries[role] = target / 'release' / name
        binaries[role].write_bytes(role.encode())
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(dict(source_sha='a' * 40, build_profile='release',
        binary_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries.values()},
        build_commands=['recorded'], toolchains={'rust': 'recorded'})))
    monkeypatch.setattr(b3_linux, 'environment', lambda _: dict(selected_cpus=[0], taskset='/usr/bin/taskset', scope='diagnostic'))
    monkeypatch.setattr(runner.subprocess, 'check_output', lambda *a, **kw: 'a' * 40 if kw.get('text') else b'')
    output = tmp_path / 'output'

    def run(path, spec, observed, root, **kwargs):
        for role, original in binaries.items():
            assert observed[role] == (original if platform_name == 'linux' else output / 'binaries' / original.name)
            assert (output / 'binaries' / original.name).read_bytes() == original.read_bytes()
        assert ('capture_backend' in kwargs) == (platform_name == 'linux')
        return {'cleanup': {'all_zero': True}}

    monkeypatch.setattr(runner.b3, 'run_cell', run)
    runner.execute(SimpleNamespace(platform=platform_name, cores=1, axis='streams', counts=[8],
        repeats=1, materialized_streams=True, fixed_channels=8, target=target,
        output=output, build_manifest=manifest))


@pytest.mark.parametrize('changed', ['original', 'retained'])
def test_immediate_execution_check_rejects_changed_bytes(tmp_path, changed):
    original = tmp_path / 'original'
    original.mkdir()
    retained = tmp_path / 'retained'
    retained.mkdir()
    binaries = {role: original / name for role, name in runner.binary_names('linux').items()}
    for path in binaries.values():
        path.write_bytes(b'original')
        (retained / path.name).write_bytes(b'original')
    build = {'binary_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries.values()}}
    runner.verify_linux_execution(binaries, retained, build)
    path = binaries['rust'] if changed == 'original' else retained / binaries['rust'].name
    path.write_bytes(b'changed')
    with pytest.raises(ValueError):
        runner.verify_linux_execution(binaries, retained, build)
