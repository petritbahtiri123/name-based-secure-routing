"""Coordinate and independently verify one finite native Direct/NBSR pair."""

import argparse
from pathlib import Path, PurePosixPath
import re

from scripts.performance.linux_native_duration import bounds
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_loopback import ROOT, validate_matrix, write_json
from scripts.performance.linux_native_finite_control import FiniteLedger, SCHEMA, drive
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.linux_native_lifecycle_coordinator import Manager
from scripts.performance.linux_native_lifecycle_remote import remote_command, remote_path
from scripts.performance.linux_native_lifecycle_run import collect
from scripts.performance.linux_native_pair import analyze_pair, read, verify_index
from scripts.performance.linux_native_peer import validate_endpoint
from scripts.performance.linux_native_paced import validate_rate
from scripts.performance.linux_native_live_relay import LiveLedger
from scripts.performance.linux_native_source_observer import source_records
from scripts.performance.linux_native_destination_observer import replay_destination
from scripts.performance.process_cancellation import Cancellation, not_cancelled


ROLES = ('source', 'destination')


def validate_config(value):
    require(isinstance(value, dict) and set(value) - {'post_close_reports', 'diagnostic_rate', 'source_live_guard', 'paired_live_guards', 'diagnostic_seconds'} == {'schema', 'source_sha', 'path', 'payload', 'streams', 'depth', *ROLES},
            'invalid finite configuration fields')
    require(type(value.get('post_close_reports', False)) is bool, 'boolean post-close mode required')
    require(type(value.get('source_live_guard', False)) is bool
            and (not value.get('source_live_guard') or 'diagnostic_rate' in value), 'paced source guard required')
    require(type(value.get('paired_live_guards', False)) is bool
            and (not value.get('paired_live_guards') or value.get('source_live_guard') is True),
            'paired guards require observed source')
    if 'diagnostic_seconds' in value:
        require('diagnostic_rate' in value and value['diagnostic_seconds'] is not None, 'long diagnostic requires pacing')
        bounds(value['diagnostic_seconds'])
    if 'diagnostic_rate' in value:
        validate_rate(value['diagnostic_rate'])
        require(value.get('post_close_reports') is True, 'paced diagnostic requires post-close mode')
    require(value['schema'] == 'nbsr-native-finite-coordinator-v1'
            and isinstance(value['source_sha'], str) and re.fullmatch('[0-9a-f]{40}', value['source_sha']), 'invalid schema/SHA')
    require(value['path'] in ('direct', 'nbsr'), 'invalid path')
    for field in ('payload', 'streams', 'depth'):
        require(type(value[field]) is int, 'integer shape required')
    for role in ROLES:
        target = value[role]
        require(isinstance(target, dict) and set(target) == {'transport', 'host', 'checkout', 'binaries',
            'build_manifest', 'authority', 'output', 'bind', 'cores'}, 'invalid target fields')
        remote_command(target, ['true'])
        for field in ('binaries', 'build_manifest', 'authority', 'output'):
            remote_path(target[field])
        require(type(target['cores']) is int, 'integer cores required')
        validate_matrix(dict(schema='nbsr-linux-loopback-v1', cores=[target['cores']],
            workloads=[dict(payload_bytes=value['payload'], streams=value['streams'], outstanding=value['depth'])],
            warmup_seconds=3, duration_seconds=20))
        _, port = validate_endpoint(target['bind'], allow_zero=True)
        require(role != 'source' or port == 0, 'source ephemeral bind required')
        output, private = (PurePosixPath(target[key]) for key in ('output', 'authority'))
        require(not output.is_relative_to(PurePosixPath(target['checkout'])), 'output in checkout')
        require(not output.is_relative_to(private) and not private.is_relative_to(output), 'private/output overlap')
    src, dst = (value[r] for r in ROLES)
    require(src['cores'] == dst['cores'], 'matched peer core count required')
    if (src['transport'], src['host']) == (dst['transport'], dst['host']):
        a, b = PurePosixPath(src['output']), PurePosixPath(dst['output'])
        require(not a.is_relative_to(b) and not b.is_relative_to(a), 'same-host output overlap')
    return value


def endpoint_arguments(config, role):
    target = config[role]
    argv = ['python3', '-B', '-m', 'scripts.performance.linux_native_finite_endpoint', '--role', role]
    for field in ('binaries', 'build_manifest', 'authority', 'output', 'bind', 'cores'):
        argv += ['--' + field.replace('_', '-'), str(target[field])]
    for field in ('path', 'payload', 'streams', 'depth'):
        argv += ['--' + field, str(config[field])]
    if config.get('post_close_reports', False):
        argv += ['--post-close-reports']
    if 'diagnostic_rate' in config:
        argv += ['--diagnostic-rate', *map(str, config['diagnostic_rate'])]
    if 'diagnostic_seconds' in config:
        argv += ['--diagnostic-seconds', str(config['diagnostic_seconds'])]
    if config.get('paired_live_guards', False):
        argv += ['--paired-live-guards']
    if role == 'source':
        if config.get('source_live_guard', False):
            argv += ['--source-live-guard']
        argv += ['--destination-address', validate_endpoint(config['destination']['bind'], allow_zero=True)[0]]
    return argv


def check_endpoint(root, role):
    index = verify_index(root)
    require(not (root / 'failure.json').exists(), 'failed endpoint')
    result, controller = read(root, 'result.json'), read(root, 'controller.json')
    require(result['status'] == 'PASS_FINITE_ENDPOINT' and result['role'] == role
            and controller['role'] == role and controller['schema'] == SCHEMA, 'endpoint identity/status mismatch')
    env = read(root / 'peer', 'environment.json')
    paired = controller.get('paired_live_guards', False)
    require(type(paired) is bool and env.get('paired_live_guards', False) == paired, 'endpoint/peer live mode mismatch')
    ledger = LiveLedger(payload_bytes=env['cell']['payload_bytes'], diagnostic_seconds=env['cell'].get('diagnostic_seconds')) if paired else FiniteLedger()
    with (root / 'events.ndjson').open('rb') as stream:
        for wire in stream:
            require(len(wire) <= 65536 and wire.endswith(b'\n'), 'invalid retained frame')
            ledger.accept(role, wire)
    ledger.eof(role)
    telemetry = ledger.telemetry if paired else []
    if paired and role == 'source':
        require([row['value'] for row in telemetry] == source_records(root / 'peer', diagnostic_seconds=env['cell'].get('diagnostic_seconds')), 'source control/stdout mismatch')
    return dict(index_sha256=index, events={name: value for (r, name), value in ledger.received.items() if r == role},
                telemetry=telemetry)


def execute(config, output, *, check_cancelled=not_cancelled):
    validate_config(config)
    require(not output.is_symlink() and not output.resolve().is_relative_to(ROOT), 'external evidence directory required')
    output.mkdir(parents=False, exist_ok=False)
    problem = None
    try:
        write_json(output / 'config.json', config)
        paired = config.get('paired_live_guards', False)
        ledger = LiveLedger(payload_bytes=config['payload'], diagnostic_seconds=config.get('diagnostic_seconds')) if paired else FiniteLedger()
        manager = Manager(None, output, check_cancelled=check_cancelled, ledger=ledger, diagnostic_seconds=config.get('diagnostic_seconds'))
        if paired:
            def forward(role, value):
                if role == 'source' and value['event'] in ('paced_progress', 'paced_final'):
                    manager.send('destination', dict(op=value['event'], value=value['value']))
            manager.on_receive = forward
        try:
            drive(lambda role: manager.start_command(role, remote_command(config[role], endpoint_arguments(config, role))),
                  manager.wait, manager.send, manager.finish)
        except BaseException as error:
            problem = error
        finally:
            cleanup = manager.close()
            write_json(output / 'cleanup.json', cleanup)
        for role in ROLES:
            if role not in manager.children:
                continue
            if manager.ledger.positions[role] == 0:
                write_json(output / (role + '-collection-skipped.json'), dict(status='UNCONFIRMED_OUTPUT_OWNERSHIP'))
                continue
            try:
                collect(config[role], role, output, check_cancelled=check_cancelled)
            except (OSError, ValueError, TimeoutError, InterruptedError) as error:
                write_json(output / (role + '-collection-failure.json'), dict(error_type=type(error).__name__, error=str(error)))
                if problem is None:
                    problem = error
        if problem is not None:
            raise problem
        require(set(cleanup) == set(ROLES) and all(v['exit_code'] == 0 and not v['local_relay_forced']
                for v in cleanup.values()), 'relay cleanup failed')
        endpoints = {role: check_endpoint(output / role, role) for role in ROLES}
        for role, checked in endpoints.items():
            for name, event in checked['events'].items():
                require(event == manager.ledger.received[role, name], 'retained/live event mismatch')
        if paired:
            require(endpoints['source']['telemetry'] == ledger.telemetry, 'retained/live source telemetry mismatch')
        result = analyze_pair(output / 'source' / 'peer', output / 'destination' / 'peer', source_sha=config['source_sha'])
        expected = dict(path=config['path'], payload_bytes=config['payload'], streams=config['streams'],
                        outstanding=config['depth'], cores=config['source']['cores'])
        if 'diagnostic_rate' in config:
            expected['diagnostic_rate'] = config['diagnostic_rate']
        if 'diagnostic_seconds' in config:
            expected['diagnostic_seconds'] = config['diagnostic_seconds']
        require(result['cell'] == expected, 'requested/actual workload mismatch')
        for role in ROLES:
            environment = read(output / role / 'peer', 'environment.json')
            require(environment['bind'] == config[role]['bind'],
                    'requested/actual bind mismatch')
            require(environment.get('post_close_reports', False) == config.get('post_close_reports', False),
                    'requested/actual cleanup mode mismatch')
            require(environment.get('source_live_guard', False) ==
                    (role == 'source' and config.get('source_live_guard', False)), 'requested/actual live guard mismatch')
            require(environment.get('paired_live_guards', False) == paired, 'requested/actual paired mode mismatch')
        if paired:
            result.update(live_private_growth='PAIRED_DIAGNOSTIC', destination_private_growth='DIAGNOSTIC',
                destination_live_guard=replay_destination(output / 'destination', output / 'source' / 'peer',
                                                         payload_bytes=config['payload'], diagnostic_seconds=config.get('diagnostic_seconds')))
        result.update(status='PASS_CONTROLLED_FINITE_PAIR',
            endpoint_indexes={role: value['index_sha256'] for role, value in endpoints.items()},
            sustained_capacity='NOT_ESTABLISHED')
        write_json(output / 'result.json', result)
        return result
    except BaseException as error:
        write_json(output / 'failure.json', dict(status='INVALID_PARTIAL', error_type=type(error).__name__, error=str(error)))
        raise
    finally:
        seal_output(output)


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
