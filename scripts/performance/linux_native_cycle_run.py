"""Run a bounded native same-process sequential lifecycle diagnostic pair."""

import argparse
from pathlib import Path

from scripts.performance import linux_native_lifecycle_run as shared
from scripts.performance import linux_native_lifecycle_coordinator as bundle
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_lifecycle_control import CYCLE_COUNTS, decode_object
from scripts.performance.process_cancellation import Cancellation
from scripts.performance.linux_native_cycle_limits import validate_shape


def bundle_shape(value):
    return {key: item for key, item in value.items() if key not in ('cycles', 'streams', 'channels', 'memory_observer')} | dict(
        schema='nbsr-native-lifecycle-coordinator-v1', count=16, rate=100, shards=1)


def validate_config(value):
    require(isinstance(value, dict) and set(value) - {'streams', 'channels', 'memory_observer'} == {'schema', 'source_sha', 'cycles', 'source', 'destination'}
            and value['schema'] == 'nbsr-native-cycle-coordinator-v1'
            and type(value['cycles']) is int and value['cycles'] in CYCLE_COUNTS, 'invalid cycle configuration')
    require(type(value.get('memory_observer', False)) is bool, 'boolean memory observer required')
    validate_shape(value.get('streams', 1), value.get('channels', 1))
    bundle.validate_config(bundle_shape(value))
    return value


def endpoint_arguments(config, role):
    validate_config(config)
    argv = bundle.endpoint_arguments(bundle_shape(config), role)
    argv[argv.index('scripts.performance.linux_native_lifecycle_endpoint')] = 'scripts.performance.linux_native_cycle_endpoint'
    for flag in ('--count', '--rate', '--shards'):
        i = argv.index(flag)
        del argv[i:i + 2]
    return argv + ['--cycles', str(config['cycles']), '--streams', str(config.get('streams', 1)), '--channels', str(config.get('channels', 1))] + (['--memory-observer'] if config.get('memory_observer', False) else [])


def execute(config, output, **kwargs):
    validate_config(config)
    return shared.execute(config, output, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.config.open('rb') as stream:
        config = decode_object(stream.read(65537))
    with Cancellation() as cancellation:
        execute(config, args.output, check_cancelled=cancellation.check)


if __name__ == '__main__':
    main()
