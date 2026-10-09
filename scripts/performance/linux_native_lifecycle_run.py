"""Run one functional native lifecycle pair through private management streams."""

import argparse
import json
import time
from pathlib import Path

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_loopback import ROOT, write_json
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.linux_native_lifecycle_coordinator import Manager, drive, endpoint_arguments, validate_config
from scripts.performance.linux_native_lifecycle_gate import check_endpoint
from scripts.performance.linux_native_lifecycle_pair import analyze
from scripts.performance.linux_native_lifecycle_remote import download_archive, extract_public_archive, remote_command
from scripts.performance.linux_native_pair import verify_index
from scripts.performance.linux_native_archive import archive_root
from scripts.performance.process_cancellation import Cancellation, not_cancelled


def collect(target, role, output, *, check_cancelled=not_cancelled, maximum_entries=10000, archive_collection=False):
    started = time.monotonic()
    archive = output / (role + '.tar')
    result = download_archive(remote_command(target, ['tar', '-C', target['output'], '-cf', '-', '.']),
        archive, output / (role + '-transfer-stderr.log'), check_cancelled=check_cancelled)
    transferred = time.monotonic()
    if archive_collection:
        root = archive_root(archive, maximum_entries=maximum_entries)
        loaded = time.monotonic()
        result['index_sha256'] = verify_index(root)
        result.update(archive_disposition='retained complete archive; validated without extraction',
                      transfer_seconds=transferred - started, load_seconds=loaded - transferred,
                      inventory_seconds=time.monotonic() - loaded)
        write_json(output / (role + '-transfer.json'), result)
        return root
    destination = output / role
    extract_public_archive(archive, destination, **({"maximum_entries": maximum_entries} if maximum_entries != 10000 else {}))
    result['index_sha256'] = verify_index(destination)
    # Verified canonical extraction retains every archive member; remove only this duplicate.
    archive.unlink()
    result['archive_disposition'] = 'duplicate removed after extracted checksum inventory verification'
    write_json(output / (role + '-transfer.json'), result)


def collect_reports(target, role, output, *, check_cancelled=not_cancelled):
    """Retain a small diagnostic subset before either peer's bulk extraction.

    Missing reports are expected after failures. This subset never substitutes
    for the complete checksum inventory or paired result validation.
    """
    require(role in ('source', 'destination'), 'invalid report role')
    names = ('failure.json', 'result.json', 'events.ndjson',
             'peer/failure.json', 'peer/result.json', 'peer/exit.json',
             'peer/server-result.json', 'peer/stderr')
    archive = output / (role + '-reports.tar')
    result = download_archive(
        remote_command(target, ['tar', '--ignore-failed-read', '-C', target['output'],
                                '-cf', '-', *names]),
        archive, output / (role + '-reports-stderr.log'), timeout=3,
        maximum_bytes=4 * 1024 * 1024, check_cancelled=check_cancelled)
    destination = output / (role + '-reports')
    extract_public_archive(archive, destination, maximum_entries=32,
                           maximum_bytes=4 * 1024 * 1024)
    result.update(status='DIAGNOSTIC_SUBSET_NOT_PAIRED_VALIDATION',
                  files=sorted(p.relative_to(destination).as_posix()
                               for p in destination.rglob('*') if p.is_file()))
    write_json(output / (role + '-reports-transfer.json'), result)


def execute(config, output, *, check_cancelled=not_cancelled, archive_collection=False):
    cycles = config.get('cycles') if isinstance(config, dict) and config.get('schema') == 'nbsr-native-cycle-coordinator-v1' else None
    validate, arguments, replay, endpoint_gate, run_driver = validate_config, endpoint_arguments, analyze, check_endpoint, drive
    ledger_options = {}
    cycle_shape = {}
    if cycles is not None:
        from scripts.performance import linux_native_cycle_run as cycle_run
        from scripts.performance import linux_native_cycle_gate as cycle_gate
        from scripts.performance.linux_native_cycle_coordinator import CycleLedger, drive_cycles
        validate, arguments = cycle_run.validate_config, cycle_run.endpoint_arguments
        replay, endpoint_gate = cycle_gate.analyze, cycle_gate.check_endpoint
        def run_driver(*args, **kwargs):
            return drive_cycles(cycles, *args, **kwargs)
        ledger_options['ledger'] = CycleLedger(cycles)
        ledger_options['lifecycle_cycles'] = cycles
        cycle_shape['streams'] = config.get('streams', 1)
        cycle_shape['channels'] = config.get('channels', 1)
        cycle_shape['memory_observer'] = config.get('memory_observer', False)
    validate(config)
    if config.get('memory_observer', False):
        cycle_shape['memory_observer'] = True
    if 'bundle_mode' in config:
        cycle_shape['bundle_mode'] = config['bundle_mode']
    count = cycles if cycles is not None else config['count']
    require(not output.is_symlink() and not output.resolve().is_relative_to(ROOT), 'external evidence directory required')
    output.mkdir(parents=False, exist_ok=False)
    require(type(archive_collection) is bool, 'boolean archive collection required')
    roots = {role: output / role for role in ('source', 'destination')}
    manager, problem = None, None
    try:
        write_json(output / 'config.json', config)
        manager = Manager(count, output, check_cancelled=check_cancelled, **ledger_options)
        try:
            run_driver(lambda role: manager.start_command(role, remote_command(config[role], arguments(config, role))),
                  manager.wait, manager.send, manager.finish, sleep=manager.sleep)
        except BaseException as error:
            problem = error
        finally:
            write_json(output / 'cleanup.json', manager.close())
        # A slow first bulk extraction must not starve the other peer's reports.
        # Use the same live-event ownership proof as full collection below.
        for role in ('destination', 'source'):
            if role not in manager.children or manager.ledger.positions[role] == 0:
                continue
            try:
                collect_reports(config[role], role, output, check_cancelled=check_cancelled)
            except (OSError, ValueError, TimeoutError, InterruptedError) as error:
                write_json(output / (role + '-reports-failure.json'),
                           dict(error_type=type(error).__name__, error=str(error)))
        # Preserve available failed endpoints as well. Each transfer has its own bound.
        for role in ('source', 'destination'):
            if role not in manager.children:
                continue
            if manager.ledger.positions[role] == 0:
                # A started relay is not proof that exclusive output creation succeeded.
                # The first validated live phase binds this invocation to a fresh root.
                write_json(output / (role + '-collection-skipped.json'),
                           dict(status='UNCONFIRMED_OUTPUT_OWNERSHIP',
                                retained='local management/stderr; remote path left untouched'))
                continue
            try:
                entry_bounds = {(4096, 'source'): 20000, (6144, 'source'): 30000,
                                (6144, 'destination'): 15000, (8192, 'source'): 40000,
                                (8192, 'destination'): 20000}
                entry_bound = entry_bounds.get((count, role)) if cycles is None else None
                collected = collect(config[role], role, output, check_cancelled=check_cancelled,
                        **({'maximum_entries': entry_bound} if entry_bound is not None else {}),
                        **({'archive_collection': True} if archive_collection else {}))
                if archive_collection:
                    roots[role] = collected
            except (OSError, ValueError, TimeoutError, InterruptedError) as error:
                write_json(output / (role + '-collection-failure.json'), dict(error_type=type(error).__name__, error=str(error)))
                if problem is None:
                    problem = error
        if problem is not None:
            raise problem
        endpoints = {role: endpoint_gate(roots[role], role, count, **cycle_shape) for role in ('source', 'destination')}
        for role, checked in endpoints.items():
            for name, value in checked['events'].items():
                require(value == manager.ledger.received[role, name], 'retained/control event mismatch')
        result = replay(roots['source'] / 'peer', roots['destination'] / 'peer',
                        source_sha=config['source_sha'], count=count, **cycle_shape)
        for role in ('source', 'destination'):
            environment = json.loads((roots[role] / 'peer' / 'environment.json').read_bytes())
            require(config[role].get('runtime_workers') == environment.get('runtime_workers'),
                    'requested/actual runtime worker mismatch')
            require(environment['offered_rate'] == config.get('rate') and environment['source_shards'] == config.get('shards'),
                    'requested/actual workload mismatch')
            cpus = environment['linux_environment']['selected_cpus']
            require(len(cpus) == config[role]['cores'] and ('cpu_pool' not in config[role]
                    or cpus == config[role]['cpu_pool']), 'requested/actual CPU allocation mismatch')
        result.update(status='PASS_FUNCTIONAL_SAME_PROCESS_CYCLES' if cycles is not None else 'PASS_FUNCTIONAL_CONTROLLED_PAIR',
                      paired_active_hold='COORDINATED_TWO_SECONDS',
                      endpoint_indexes={role: value['index_sha256'] for role, value in endpoints.items()})
        if archive_collection:
            result['collection_mode'] = 'COMPLETE_ARCHIVES_VALIDATED_WITHOUT_EXTRACTION'
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
    parser.add_argument('--archive-collection', action='store_true',
                        help='retain complete bounded TARs and validate without filesystem extraction')
    args = parser.parse_args()
    with args.config.open('rb') as stream:
        config = decode_object(stream.read(65537))
    with Cancellation() as cancellation:
        execute(config, args.output, check_cancelled=cancellation.check, archive_collection=args.archive_collection)


if __name__ == '__main__':
    main()
