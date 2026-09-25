"""Explicit native benchmark runtime workers preserve default replay contracts."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance import linux_native_lifecycle_coordinator as coordinator
from scripts.performance.linux_native_lifecycle_pair import analyze
from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_native_lifecycle_coordinator import config
from tests.performance.test_linux_native_lifecycle_pair import peers, SHA, write


def test_config_cli_explicit_workers():
    value = config()
    value['destination'].update(cores=2, runtime_workers=2)
    assert coordinator.validate_config(value) == value
    argv = coordinator.endpoint_arguments(value, 'destination')
    assert native.argument_parser().parse_args(argv[4:]).runtime_workers == 2
    assert '--runtime-workers' not in coordinator.endpoint_arguments(config(), 'source')


def test_workload_adds_only_existing_worker_flag():
    args = SimpleNamespace(role='destination', count=16, shards=2, rate=100, cores=2)
    paths = dict(binaries=Path('/bins'), authority=Path('/tls'), lifecycle=Path('/life'), output=Path('/out'), bind='192.0.2.2:0', endpoint=None)
    old = native.workload_command(args, **paths)
    args.runtime_workers = 2
    new = native.workload_command(args, **paths)
    assert new == (old[0]+['--p2a-runtime-workers','2'], old[1])


@pytest.mark.parametrize('workers', [True, 0, 3, 4, '2', None])
def test_config_rejects_invalid_or_oversubscribed_workers(workers):
    value = config()
    value['destination'].update(cores=2, runtime_workers=workers)
    with pytest.raises(ValueError):
        coordinator.validate_config(value)


@pytest.mark.parametrize('tamper', [False, 'missing', 'wrong', 'undeclared'])
def test_peer_replay_binds_explicit_workers(tmp_path, tamper):
    source, dest = peers(tmp_path)
    # One explicit worker is enough to test binding without changing fixture affinity.
    env = json.loads((dest/'environment.json').read_bytes())
    if tamper != 'undeclared':
        env['runtime_workers'] = 1
    write(dest, 'environment.json', env)
    command = json.loads((dest/'command.json').read_bytes())
    if tamper != 'missing':
        command['argv'] += ['--p2a-runtime-workers', '2' if tamper=='wrong' else '1']
    write(dest, 'command.json', command)
    seal_output(dest)
    if tamper:
        with pytest.raises(ValueError):
            analyze(source,dest,source_sha=SHA,count=16)
    else:
        assert analyze(source,dest,source_sha=SHA,count=16)['successful_connections']==16


def test_cycles_reject_explicit_workers_before_remote_launch():
    from scripts.performance import linux_native_cycle_run
    from tests.performance.test_linux_native_cycle_run import config as cycle_config
    value = cycle_config()
    value['source']['runtime_workers'] = 1
    with pytest.raises(ValueError, match='workers'):
        linux_native_cycle_run.validate_config(value)


def test_source_cannot_claim_ignored_runtime_workers():
    value = config()
    value['source'].update(cores=2, runtime_workers=2)
    with pytest.raises(ValueError, match='destination'):
        coordinator.validate_config(value)
    args = SimpleNamespace(role='source', count=16, shards=2, rate=100, cores=2, runtime_workers=2)
    with pytest.raises(ValueError, match='destination'):
        native.workload_command(args)
