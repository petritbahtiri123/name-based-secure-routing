import json
import sys

import pytest

from scripts.performance import linux_native_lifecycle_coordinator as coordinator


def test_manager_cancels_and_reaps_owned_relay_on_early_eof(tmp_path):
    manager = coordinator.Manager(16, tmp_path, timeout=2)
    child = manager.start_command('source', [sys.executable, '-c', 'pass'])
    try:
        with pytest.raises(InterruptedError, match='EOF'):
            manager.wait('source', 'prepared')
    finally:
        manager.close()
    assert child.poll() is not None


def test_manager_deadline_kills_uncooperative_owned_relay(tmp_path):
    manager = coordinator.Manager(16, tmp_path, timeout=.15, cleanup_timeout=.1)
    child = manager.start_command('source', [sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        with pytest.raises(TimeoutError):
            manager.wait('source', 'prepared')
    finally:
        cleanup = manager.close()
    assert child.poll() is not None
    assert cleanup['source']['remote_cleanup'] == 'UNCONFIRMED'


def test_manager_reads_phase_and_transmits_control(tmp_path):
    event = dict(schema='nbsr-native-lifecycle-control-v1', role='source', event='prepared', timestamp_ns=1)
    code = ('import sys,json; print(' + repr(json.dumps(event)) + ',flush=True); '
            'value=json.loads(sys.stdin.readline()); sys.exit(0 if value=={"op":"cancel"} else 2)')
    manager = coordinator.Manager(16, tmp_path, timeout=3)
    child = manager.start_command('source', [sys.executable, '-u', '-c', code])
    try:
        assert manager.wait('source', 'prepared') == event
        manager.send('source', dict(op='cancel'))
        assert child.wait(timeout=2) == 0
    finally:
        manager.close()


def test_manager_rejects_unbounded_event_and_reaps(tmp_path):
    manager = coordinator.Manager(16, tmp_path, timeout=3)
    child = manager.start_command('source', [sys.executable, '-c', 'print("x"*65537,flush=True)'])
    try:
        with pytest.raises(ValueError, match='bounded'):
            manager.wait('source', 'prepared')
    finally:
        manager.close()
    assert child.poll() is not None


def test_endpoint_arguments_preserve_workload_and_manage_readiness():
    from tests.performance.test_linux_native_lifecycle_coordinator import config
    value = config()
    argv = coordinator.endpoint_arguments(value, 'source')
    assert argv[:4] == ['python3', '-B', '-m', 'scripts.performance.linux_native_lifecycle_endpoint']
    assert argv[argv.index('--count') + 1] == '16'
    assert argv[argv.index('--destination-address') + 1] == '192.0.2.2'
    assert '--ready-input' not in argv
