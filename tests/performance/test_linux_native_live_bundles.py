import json
from types import SimpleNamespace

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance import linux_native_lifecycle_coordinator as coordinator
from scripts.performance import linux_native_lifecycle_pair as pair
from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_native_lifecycle import fixture
from tests.performance.test_linux_native_lifecycle_coordinator import config
from tests.performance.test_linux_native_lifecycle_pair import peers, write, SHA


def test_live_config_cli_and_source_keepalive_are_explicit():
    value = config() | dict(bundle_mode='live-bundles')
    assert coordinator.validate_config(value) == value
    argv = coordinator.endpoint_arguments(value, 'source')
    assert native.argument_parser().parse_args(argv[4:]).bundle_mode == 'live-bundles'
    old, old_env = fixture()
    live, live_env = fixture(bundle_mode='live-bundles')
    assert live == old + ['--b3-keep-alive-seconds', '1'] and live_env == old_env
    assert fixture('destination', bundle_mode='live-bundles') == fixture('destination')
    assert '--bundle-mode' not in coordinator.endpoint_arguments(config(), 'source')


@pytest.mark.parametrize('value', [True, 1, None, 'live', 'idle', ''])
def test_invalid_bundle_mode_rejects(value):
    with pytest.raises(ValueError):
        coordinator.validate_config(config() | dict(bundle_mode=value))
    with pytest.raises(ValueError):
        fixture(bundle_mode=value)


def test_sequential_workload_cannot_silently_use_live_bundles():
    with pytest.raises(ValueError, match='bundle'):
        native.workload_command(SimpleNamespace(cycles=4, count=4, rate=None, shards=None,
                                               role='source', bundle_mode='live-bundles'))


@pytest.mark.parametrize('tamper', [False, 'source-mode', 'destination-mode', 'missing-flag', 'interval'])
def test_live_peer_replay_binds_mode_and_exact_keepalive(tmp_path, tamper):
    source, destination = peers(tmp_path)
    for role, root in [('source', source), ('destination', destination)]:
        env = json.loads((root / 'environment.json').read_bytes())
        env['bundle_mode'] = 'idle-bundles' if tamper == role + '-mode' else 'live-bundles'
        write(root, 'environment.json', env)
        if role == 'source' and tamper != 'missing-flag':
            command = json.loads((root / 'command.json').read_bytes())
            command['argv'] += ['--b3-keep-alive-seconds', '2' if tamper == 'interval' else '1']
            write(root, 'command.json', command)
        seal_output(root)
    if tamper:
        with pytest.raises(ValueError):
            pair.analyze(source, destination, source_sha=SHA, count=16, bundle_mode='live-bundles')
    else:
        assert pair.analyze(source, destination, source_sha=SHA, count=16, bundle_mode='live-bundles')['successful_connections'] == 16
        with pytest.raises(ValueError):
            pair.analyze(source, destination, source_sha=SHA, count=16)
