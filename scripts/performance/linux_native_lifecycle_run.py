"""Run one functional native lifecycle pair through private management streams."""

import argparse
import json
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
from scripts.performance.process_cancellation import Cancellation, not_cancelled


def collect(target, role, output, *, check_cancelled=not_cancelled):
    archive = output / (role + '.tar')
    result = download_archive(remote_command(target, ['tar', '-C', target['output'], '-cf', '-', '.']),
        archive, output / (role + '-transfer-stderr.log'), check_cancelled=check_cancelled)
    destination = output / role
    extract_public_archive(archive, destination)
    result['index_sha256'] = verify_index(destination)
    # Verified canonical extraction retains every archive member; remove only this duplicate.
    archive.unlink()
    result['archive_disposition'] = 'duplicate removed after extracted checksum inventory verification'
    write_json(output / (role + '-transfer.json'), result)


def execute(config, output, *, check_cancelled=not_cancelled):
    validate_config(config)
    require(not output.is_symlink() and not output.resolve().is_relative_to(ROOT), 'external evidence directory required')
    output.mkdir(parents=False, exist_ok=False)
    manager, problem = None, None
    try:
        write_json(output / 'config.json', config)
        manager = Manager(config['count'], output, check_cancelled=check_cancelled)
        try:
            drive(lambda role: manager.start_command(role, remote_command(config[role], endpoint_arguments(config, role))),
                  manager.wait, manager.send, manager.finish, sleep=manager.sleep)
        except BaseException as error:
            problem = error
        finally:
            write_json(output / 'cleanup.json', manager.close())
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
                collect(config[role], role, output, check_cancelled=check_cancelled)
            except (OSError, ValueError, TimeoutError, InterruptedError) as error:
                write_json(output / (role + '-collection-failure.json'), dict(error_type=type(error).__name__, error=str(error)))
                if problem is None:
                    problem = error
        if problem is not None:
            raise problem
        endpoints = {role: check_endpoint(output / role, role, config['count']) for role in ('source', 'destination')}
        for role, checked in endpoints.items():
            for name, value in checked['events'].items():
                require(value == manager.ledger.received[role, name], 'retained/control event mismatch')
        result = analyze(output / 'source' / 'peer', output / 'destination' / 'peer',
                         source_sha=config['source_sha'], count=config['count'])
        for role in ('source', 'destination'):
            environment = json.loads((output / role / 'peer' / 'environment.json').read_bytes())
            require(environment['offered_rate'] == config['rate'] and environment['source_shards'] == config['shards'],
                    'requested/actual workload mismatch')
        result.update(status='PASS_FUNCTIONAL_CONTROLLED_PAIR', paired_active_hold='COORDINATED_TWO_SECONDS',
                      endpoint_indexes={role: value['index_sha256'] for role, value in endpoints.items()})
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
