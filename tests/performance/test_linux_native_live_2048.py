import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance.linux_native_lifecycle_control import LifecycleBarrier
from scripts.performance.linux_native_lifecycle_coordinator import EventLedger, validate_config, endpoint_arguments
from tests.performance.test_linux_native_lifecycle import fixture
from tests.performance.test_linux_native_lifecycle_coordinator import config


def test_2048_requires_explicit_live_mode_in_config_and_command():
    value = config() | dict(count=2048, bundle_mode='live-bundles')
    assert validate_config(value) == value
    args = native.argument_parser().parse_args(endpoint_arguments(value, 'source')[4:])
    assert args.count == 2048 and args.bundle_mode == 'live-bundles'
    argv, _ = fixture(count=2048, bundle_mode='live-bundles')
    assert argv[argv.index('--lifecycle-clients') + 1] == '2048'
    assert argv[-2:] == ['--b3-keep-alive-seconds', '1']
    for mode in ('idle-bundles',):
        with pytest.raises(ValueError):
            fixture(count=2048, bundle_mode=mode)
        with pytest.raises(ValueError):
            validate_config(value | dict(bundle_mode=mode))


def test_control_barrier_accepts_bounded_live_count(tmp_path):
    root, output = tmp_path / 'private', tmp_path / 'output'
    root.mkdir()
    output.mkdir()
    barrier = LifecycleBarrier(role='source', count=2048, root=root, output=output, capture=lambda: {})
    assert len(barrier.expected_active) == 2048
    assert EventLedger(2048).count == 2048


@pytest.mark.parametrize('count', [True, 2049, 4097, 8193])
def test_undeclared_count_remains_rejected(count):
    with pytest.raises(ValueError):
        fixture(count=count, bundle_mode='live-bundles')
    with pytest.raises(ValueError):
        validate_config(config() | dict(count=count, bundle_mode='live-bundles'))
