import importlib
from types import SimpleNamespace

import pytest

from scripts.performance import linux_native_lifecycle_run as run
from tests.performance.test_linux_native_lifecycle_coordinator import config as bundle_config


def config():
    value = bundle_config()
    for name in ('count', 'rate', 'shards'):
        del value[name]
    return value | dict(schema='nbsr-native-cycle-coordinator-v1', cycles=2)


def test_cycle_config_and_remote_command_have_no_fanout_controls():
    module = importlib.import_module('scripts.performance.linux_native_cycle_run')
    value = config()
    assert module.validate_config(value) == value
    argv = module.endpoint_arguments(value, 'source')
    assert 'scripts.performance.linux_native_cycle_endpoint' in argv
    assert argv[argv.index('--cycles') + 1] == '2'
    assert not any(flag in argv for flag in ('--count', '--rate', '--shards'))
    for change in (dict(cycles=True), dict(cycles=32), dict(rate=100)):
        with pytest.raises(ValueError):
            module.validate_config(value | change)


def test_cycle_failure_closes_and_preserves_without_success(tmp_path, monkeypatch):
    module = importlib.import_module('scripts.performance.linux_native_cycle_run')
    actions = []
    class Manager:
        def __init__(self, *args, **kwargs):
            assert kwargs['ledger'].__class__.__name__ == 'CycleLedger'
            self.children = {'source': object()}
            self.ledger = SimpleNamespace(positions=dict(source=1, destination=0))
        def start_command(self, *args):
            raise InterruptedError('cycle control failed')
        wait = send = finish = sleep = lambda *args: None
        def close(self):
            actions.append('close')
            return {}
    monkeypatch.setattr(run, 'Manager', Manager)
    monkeypatch.setattr(run, 'collect', lambda target, role, output, **kw: actions.append(role))
    output = tmp_path / 'output'
    with pytest.raises(InterruptedError, match='cycle control failed'):
        module.execute(config(), output)
    assert actions == ['close', 'source']
    assert (output / 'failure.json').exists() and (output / 'checksums.sha256').exists()
    assert not (output / 'result.json').exists()
