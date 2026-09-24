"""One owned native-address Linux finite peer; no SSH or host-policy changes.

Each host invokes this independently. Readiness transfer and completion ACK
remain the coordinator's responsibility; source validation authorizes the ACK.
Lifetime CPU is not steady-state CPU and process exit is not runtime ownership.
"""

import argparse
from contextlib import nullcontext
import ipaddress
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import time

from scripts.performance.b3_linux import environment
from scripts.performance.linux_b5_ceiling import NAMES, require
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_b5_reference import git_state
from scripts.performance.linux_exit import observe_owned_exit
from scripts.performance.linux_loopback import ROOT, build_commands, digest, sample_process, validate_matrix, write_json
from scripts.performance.p2a_established import validate_repeat
from scripts.performance.post_close_cleanup import validate_report
from scripts.performance.process_cancellation import Cancellation, not_cancelled
from scripts.performance.linux_socket_ownership import snapshot
from scripts.performance.linux_native_paced import read_paced, validate_rate
from scripts.performance.linux_native_source_observer import SourceObserver


def validate_endpoint(value, *, allow_zero):
    try:
        address, port_text = value.rsplit(':', 1)
        ip = ipaddress.IPv4Address(address)
        port = int(port_text)
    except (ValueError, AttributeError) as error:
        raise ValueError('concrete IPv4:port required') from error
    require(not ip.is_unspecified and not ip.is_multicast and str(ip) != '255.255.255.255'
            and str(ip) == address and port_text == str(port)
            and (0 if allow_zero else 1) <= port <= 65535, 'invalid native IPv4 endpoint')
    return address, port


def readiness_endpoint(path, expected_address):
    value = json.loads(path.read_bytes())
    host, _ = validate_endpoint(value['endpoint'], allow_zero=False)
    require(host == expected_address and value.get('alpn') == 'nbsr-quic-1', 'readiness address/ALPN mismatch')
    return value['endpoint']


def measurement_contract(cell):
    """Keep historical timed cells separate from equal-work packet fixtures."""
    if 'diagnostic_rate' in cell:
        validate_rate(cell['diagnostic_rate'])
        require('operations_per_stream' not in cell, 'paced and fixed work are exclusive')
    if 'operations_per_stream' not in cell:
        return 3, 20
    count = cell['operations_per_stream']
    require(type(count) is int and 1 <= count <= 10000 and cell['outstanding'] == 1,
            'fixed work requires 1..10000 operations per stream at depth one')
    return 0, None


def validate_fixed_work(row, cell):
    measurement_contract(cell)
    if 'operations_per_stream' in cell:
        require(type(row.get('completed_operations')) is int
                and row['completed_operations'] == cell['streams'] * cell['operations_per_stream'],
                'fixed operation count differs from declared workload')


def native_command(cell, role, binaries, authority, output, *, bind, endpoint, phase_control=None, post_close_reports=False):
    require(type(post_close_reports) is bool, 'boolean post-close mode required')
    require(role in ('source', 'destination'), 'invalid role')
    _, port = validate_endpoint(bind, allow_zero=True)
    if role == 'source':
        require(port == 0, 'source bind must use an ephemeral port')
        validate_endpoint(endpoint, allow_zero=False)
    else:
        require(endpoint is None, 'destination cannot take a remote endpoint')
    matrix = dict(schema='nbsr-linux-loopback-v1', cores=[cell['cores']],
        workloads=[{k: cell[k] for k in ('payload_bytes', 'streams', 'outstanding')}],
        warmup_seconds=3, duration_seconds=20)
    validate_matrix(matrix)
    require(cell['path'] in ('direct', 'nbsr'), 'invalid path')
    warmup, duration = measurement_contract(cell)
    if 'diagnostic_rate' in cell:
        require(post_close_reports and phase_control is None, 'paced mode requires reports and no phase observer')
    server, client, env = build_commands(cell, binaries, authority, output, endpoint, warmup, 20)
    if 'diagnostic_rate' in cell:
        numerator, denominator = cell['diagnostic_rate']
        client += ['--p2a-groups', '1', '--p2a-progress-seconds', '5',
                   '--b5-rate-numerator', str(numerator), '--b5-rate-denominator', str(denominator)]
    if post_close_reports and cell['path'] == 'nbsr':
        server += ['--p2a-cleanup-report', str(output / 'cleanup.json')]
        client += ['--p2a-cleanup-report', str(output / 'cleanup.json')]
    if duration is None:
        pos = client.index('--p2a-duration-seconds')
        client[pos:pos + 2] = ['--p2a-operations-per-stream', str(cell['operations_per_stream'])]
    if phase_control is not None:
        require(role == 'source' and validate_endpoint(phase_control, allow_zero=False)[0] == '127.0.0.1',
                'phase control requires source-local loopback endpoint')
        client += ['--p2a-counter-control', phase_control]
    return ((client + ['--benchmark-client-bind', bind], {}) if role == 'source'
            else (server + ['--benchmark-listen', bind], env))


def observe_child(child, cpus, output, *, deadline, check_cancelled=not_cancelled, socket_identity=None, live_observer=None):
    identity = None
    previous_cpu = None
    socket_observed = False
    socket_attempts = 0
    with (output / 'resources.ndjson').open('x') as stream:
        while True:
            check_cancelled()
            sample = sample_process(child.pid, cpus, allow_exiting=True)
            current = sample['pid'], sample['start_ticks']
            if sample['pid'] != child.pid or (identity is not None and current != identity):
                raise RuntimeError('owned process identity changed')
            identity = current
            if previous_cpu is not None and sample['cpu_ns'] < previous_cpu:
                raise RuntimeError('owned process CPU counter decreased')
            previous_cpu = sample.get('cpu_ns')
            stream.write(json.dumps(sample) + '\n')
            stream.flush()
            if live_observer is not None:
                live_observer.poll()
            if socket_identity is not None and not socket_observed and socket_attempts < 20 and sample['state'] != 'Z':
                observation = snapshot(child.pid, sample['start_ticks'], *socket_identity)
                socket_attempts += 1
                with (output / 'socket-observations.ndjson').open('a') as observations:
                    observations.write(json.dumps(observation) + '\n')
                if observation['status'] == 'MEASURED_LIVE_SOCKET_SNAPSHOT':
                    write_json(output / 'socket-ownership.json', observation)
                    socket_observed = True
            if sample['state'] == 'Z':
                if live_observer is not None:
                    live_observer.stop()
                result = dict(exit_code=child.wait(timeout=5), final_sample=sample)
                write_json(output / 'exit.json', result)
                if result['exit_code'] != 0:
                    raise RuntimeError('peer exited unsuccessfully; see retained stderr')
                require(socket_identity is None or socket_observed, 'requested live UDP ownership not observed')
                if live_observer is not None:
                    result[getattr(live_observer, 'result_key', 'source_live_guard')] = live_observer.finish(result['exit_code'])
                return result
            if time.monotonic() >= deadline:
                raise TimeoutError('finite peer controller deadline')
            time.sleep(.1)


def validate_post_close(output, cell, role, pid, requested):
    require(type(requested) is bool, 'boolean post-close mode required')
    if not requested:
        return 'NOT_MEASURED'
    if cell['path'] == 'direct':
        return 'NOT_APPLICABLE_DIRECT'
    value = json.loads((output / 'cleanup.json').read_bytes())
    require(validate_report(value, role, pid), 'owned post-close report failed')
    return 'ALL_11_ZERO'


def validate_source(output, cell=None):
    if cell is not None and 'diagnostic_rate' in cell:
        row = read_paced(output / 'stdout', cell)
        write_json(output / 'validated-result.json', row)
        return row
    row = json.loads((output / 'stdout').read_text().strip().splitlines()[-1])
    require(validate_repeat(row) and type(row.get('measured_ns')) is int and row['measured_ns'] > 0,
            'source validity contract failed')
    if cell is not None:
        require(all(row.get(k) == cell[k] for k in ('path', 'payload_bytes', 'streams'))
                and row.get('outstanding_per_stream') == cell['outstanding'], 'source workload mismatch')
        validate_fixed_work(row, cell)
    write_json(output / 'validated-result.json', row)
    return row


def wait_target_exec(child, binary, *, check_cancelled=not_cancelled):
    deadline = time.monotonic() + 5
    while (Path('/proc') / str(child.pid) / 'exe').resolve() != binary.resolve():
        check_cancelled()
        if observe_owned_exit(child.pid) is not None:
            raise RuntimeError('owned child exited before target exec verification')
        if time.monotonic() >= deadline:
            raise TimeoutError('taskset target exec verification deadline')
        time.sleep(.001)


def execute(args, *, check_cancelled=not_cancelled, live_events=None, destination_observer_factory=None):
    require(platform.system() == 'Linux', 'Linux required')
    require(not any(k.startswith('NBSR_') for k in os.environ), 'remove inherited NBSR experiment settings')
    sha, dirty = git_state()
    require(not dirty, 'clean checkout required')
    output, authority, binaries = args.output.resolve(), args.authority.resolve(), args.binaries.resolve()
    require(not output.is_relative_to(ROOT), 'evidence must be outside checkout')
    require(not authority.is_relative_to(output) and not output.is_relative_to(authority),
            'private authority and publishable evidence must be disjoint')
    bind_ip, _ = validate_endpoint(args.bind, allow_zero=True)
    # This proves only local bind availability, not NIC ownership or isolation.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind((bind_ip, 0))
    if args.role == 'source':
        require(args.ready_input is not None and args.destination_address is not None,
                'source requires transferred readiness and expected destination address')
        endpoint = readiness_endpoint(args.ready_input, args.destination_address)
    else:
        require(args.ready_input is None and args.destination_address is None, 'destination has no readiness input')
        endpoint = None
    build = json.loads(args.build_manifest.read_bytes())
    hashes = {name: digest(binaries / name) for name in NAMES.values()}
    require(build.get('source_sha') == sha and build.get('build_profile') == 'release'
            and build.get('binary_sha256') == hashes and build.get('build_commands')
            and build.get('toolchains'), 'exact current release build manifest required')
    host = environment(args.cores)
    cell = dict(path=args.path, cores=args.cores, payload_bytes=args.payload,
                streams=args.streams, outstanding=args.depth)
    if getattr(args, 'operations_per_stream', None) is not None:
        cell['operations_per_stream'] = args.operations_per_stream
    if getattr(args, 'diagnostic_rate', None) is not None:
        cell['diagnostic_rate'] = args.diagnostic_rate
    warmup, duration = measurement_contract(cell)
    phase_control = getattr(args, 'phase_control', None)
    post_close_reports = getattr(args, 'post_close_reports', False)
    source_live_guard = getattr(args, 'source_live_guard', False)
    paired_live_guards = getattr(args, 'paired_live_guards', False)
    require(type(paired_live_guards) is bool and (not paired_live_guards or
        ('diagnostic_rate' in cell and post_close_reports and phase_control is None
         and ((args.role == 'source' and source_live_guard and callable(live_events))
              or (args.role == 'destination' and callable(destination_observer_factory))))),
        'paired live guards require endpoint-owned telemetry')
    require((live_events is None and destination_observer_factory is None) or paired_live_guards,
            'undeclared paired observer callbacks')
    require(type(source_live_guard) is bool and (not source_live_guard or
        (args.role == 'source' and 'diagnostic_rate' in cell and post_close_reports
         and phase_control is None and not getattr(args, 'observe_socket_ownership', False))),
        'source live guard requires paced source without other live observers')
    command, overrides = native_command(cell, args.role, binaries, authority, output, bind=args.bind,
                                       endpoint=endpoint, phase_control=phase_control, post_close_reports=post_close_reports)
    executable = Path(command[0])
    require(os.access(executable, os.X_OK), 'executable peer required')
    cert_names = ('ca.der', f'{args.role}.der')
    certificate_hashes = {name: digest(authority / name) for name in cert_names}
    require((authority / f'{args.role}-key.der').is_file(), 'role private key required')
    cpus = host['selected_cpus']
    command = [host['taskset'], '--cpu-list', ','.join(map(str, cpus)), *command]
    check_cancelled()
    output.mkdir(parents=True, exist_ok=False)
    child = None
    success = False
    try:
        write_json(output / 'environment.json', dict(repository_sha=sha, cell=cell, role=args.role,
            bind=args.bind, endpoint=endpoint, linux_environment=host, uid=os.getuid(),
            controller_deadline_seconds=120, warmup_seconds=warmup, duration_seconds=duration,
            live_socket_observer=bool(getattr(args, 'observe_socket_ownership', False)),
            phase_control_endpoint=phase_control,
            post_close_reports=post_close_reports, output_root=str(output),
            source_live_guard=source_live_guard,
            paired_live_guards=paired_live_guards,
            binary_sha256=hashes, certificates_sha256=certificate_hashes,
            scope='finite native-address peer; external/physical hardware unqualified',
            cpu_scope='whole peer lifetime including startup/warmup/drain; not steady CPU ns/op',
            cleanup_scope='explicit requested report plus owned exit; otherwise process exit only'))
        write_json(output / 'build-manifest.json', build)
        write_json(output / 'command.json', dict(argv=command, environment_overrides=overrides))
        shutil.copyfile(executable, output / 'executed-binary')
        if args.ready_input is not None:
            shutil.copyfile(args.ready_input, output / 'input-readiness.json')
        with (output / 'stdout').open('xb') as stdout, (output / 'stderr').open('xb') as stderr:
            child = subprocess.Popen(command, cwd=ROOT, env={**os.environ, **overrides},
                stdout=stdout, stderr=stderr, start_new_session=True)
            write_json(output / 'pid.json', dict(pid=child.pid, owns_process_group=True))
            check_cancelled()
            deadline = time.monotonic() + 120
            wait_target_exec(child, executable, check_cancelled=check_cancelled)
            socket_identity = ((str(executable), bind_ip)
                               if getattr(args, 'observe_socket_ownership', False) else None)
            observer = (SourceObserver(output, pid=child.pid, cpus=cpus, payload_bytes=cell['payload_bytes'],
                                       deadline_ns=int(deadline * 1e9), on_record=live_events)
                        if source_live_guard else nullcontext())
            if destination_observer_factory is not None:
                require(args.role == 'destination', 'destination observer role mismatch')
                observer = destination_observer_factory(output, pid=child.pid, cpus=cpus,
                    payload_bytes=cell['payload_bytes'], deadline_ns=int(deadline * 1e9))
            with observer as live:
                result = observe_child(child, cpus, output, deadline=deadline,
                    check_cancelled=check_cancelled, socket_identity=socket_identity, live_observer=live)
        if args.role == 'source':
            row = validate_source(output, cell)
            result.update(completed_operations=row['completed_operations'],
                          application_gbps=16 * cell['payload_bytes'] * row['completed_operations'] / row['measured_ns'])
        elif args.path == 'nbsr':
            row = json.loads((output / 'server-result.json').read_bytes())
            require(row.get('status') == 'PASS' and row.get('streams') == args.streams,
                    'destination validity contract failed')
        cleanup = validate_post_close(output, cell, args.role, child.pid, post_close_reports)
        result['runtime_ownership_cleanup'] = cleanup
        require(git_state() == (sha, ''), 'source changed during cell')
        require(all(digest(binaries / n) == h for n, h in hashes.items())
                and digest(output / 'executed-binary') == hashes[executable.name], 'binary changed')
        require(json.loads(args.build_manifest.read_bytes()) == build, 'build manifest changed')
        require({n: digest(authority / n) for n in cert_names} == certificate_hashes, 'certificate changed')
        check_cancelled()
        write_json(output / 'result.json', dict(status='PASS_FINITE_PEER', role=args.role, **result,
            strict_stable_capacity='NOT_ESTABLISHED', steady_cpu_ns_per_operation=None,
            external_hardware='NOT_PROVEN'))
        success = True
        return result
    except BaseException as error:
        write_json(output / 'failure.json', dict(status='INVALID_PARTIAL', error_type=type(error).__name__, error=str(error)))
        raise
    finally:
        if child is not None and child.returncode is None:
            # The unreaped, exclusively owned child's PID reserves its new group.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            code = child.wait(timeout=5)
            write_json(output / 'forced-cleanup.json', dict(exit_code=code, valid=False, group_killed=True))
        if not success:
            (output / 'validated-result.json').unlink(missing_ok=True)
        seal_output(output)


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase-control', help='Source-only local capture phase control IPv4:port')
    parser.add_argument('--role', choices=('source', 'destination'), required=True)
    parser.add_argument('--observe-socket-ownership', action='store_true',
                        help='Opt-in bounded live FD observer; timing is diagnostic only')
    parser.add_argument('--post-close-reports', action='store_true',
                        help='Require existing NBSR eleven-counter post-close reports; Direct remains process-exit only')
    parser.add_argument('--diagnostic-rate', type=int, nargs=2, metavar=('NUMERATOR', 'DENOMINATOR'),
                        help='Short diagnostic B5 ops/s rate; requires post-close reports, never a stable reference')
    parser.add_argument('--source-live-guard', action='store_true',
                        help='Opt-in source-only paced private-memory diagnostic; observer unqualified')
    parser.add_argument('--paired-live-guards', action='store_true',
                        help='Private endpoint-only paired paced telemetry; never a standalone capacity claim')
    parser.add_argument('--path', choices=('direct', 'nbsr'), required=True)
    for name in ('binaries', 'build-manifest', 'authority', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--bind', required=True)
    parser.add_argument('--ready-input', type=Path)
    parser.add_argument('--destination-address')
    parser.add_argument('--cores', type=int, choices=(1, 2, 4, 8, 16, 32), default=1)
    parser.add_argument('--payload', type=int, choices=(1024, 16384), default=1024)
    parser.add_argument('--streams', type=int, default=64)
    parser.add_argument('--depth', type=int, choices=(1, 2, 4, 8, 16), default=1)
    parser.add_argument('--operations-per-stream', type=int,
                        help='Distinct fixed-work mode: 1..10000 operations, zero warmup, depth one; both peers must agree')
    return parser


def main():
    args = argument_parser().parse_args()
    with Cancellation() as cancellation:
        execute(args, check_cancelled=cancellation.check)


if __name__ == '__main__':
    main()
