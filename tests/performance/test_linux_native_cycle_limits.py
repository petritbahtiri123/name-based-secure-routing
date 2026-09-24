import importlib
from pathlib import PurePosixPath

import pytest

from scripts.performance.linux_native_lifecycle import cycle_command
from scripts.performance.linux_native_lifecycle_coordinator import Manager
from scripts.performance.linux_native_cycle_endpoint import decode_cycle_control


def limits(cycles):
    return importlib.import_module('scripts.performance.linux_native_cycle_limits').cycle_bounds(cycles)


@pytest.mark.parametrize('cycles', [1,2,4,8,10,16])
def test_short_cycle_budget_stays_120(cycles):
    assert limits(cycles)['controller_seconds'] == 120


@pytest.mark.parametrize('cycles', [25,50,100])
def test_declared_long_cycle_budget_includes_hold_cooldown_and_control_allowance(cycles, tmp_path, monkeypatch):
    assert limits(cycles)['controller_seconds'] == 120 + cycles * 4
    monkeypatch.setattr('scripts.performance.linux_native_lifecycle_coordinator.time.monotonic', lambda: 1000)
    manager = Manager(cycles,tmp_path,ledger=object(),lifecycle_cycles=cycles)
    try:
        assert manager.deadline == 1000 + 120 + cycles * 4
    finally:
        manager.close()
    argv,_ = cycle_command(role='source',cycles=cycles,binaries=PurePosixPath('/bin'),
        authority=PurePosixPath('/auth'),lifecycle=PurePosixPath('/cycles'),output=PurePosixPath('/out'),
        bind='192.0.2.1:0',endpoint='192.0.2.2:4000')
    assert argv[argv.index('--connections')+1] == str(cycles)
    assert not any('timeout' in arg for arg in argv)


@pytest.mark.parametrize('cycles', [True,0,3,32,101,50.0,'50'])
def test_unsupported_lengths_reject(cycles):
    with pytest.raises(ValueError):
        limits(cycles)


def test_controller_cycle_and_duration_modes_cannot_be_mixed(tmp_path):
    with pytest.raises(ValueError):
        Manager(50,tmp_path,ledger=object(),lifecycle_cycles=50,diagnostic_seconds=60)
    assert not (tmp_path/'management.ndjson').exists()


def test_extended_private_frame_bound_does_not_allow_unbounded_ordinals():
    assert decode_cycle_control(b'{"op":"start","cycle":49}') == dict(op='start',cycle=49)
    with pytest.raises(ValueError):
        decode_cycle_control(b'{"op":"start","cycle":100}')
