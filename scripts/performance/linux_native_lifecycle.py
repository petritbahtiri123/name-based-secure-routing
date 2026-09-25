"""Bounded per-host materialized lifecycle fixture; coordinator supplies barriers.

This is functional, diagnostic-only scale, not a sustained admission benchmark.
Each role owns one child. Remote readiness/barrier transfer uses the operator's
existing authenticated management channel; this module does not implement SSH.
"""

import argparse
from contextlib import nullcontext
from collections import Counter
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
from scripts.performance.linux_loopback import ROOT, digest, physical_cpu_sets, write_json, sample_process
from scripts.performance.linux_native_cycle_memory import CycleMemoryObserver
from scripts.performance.linux_native_lifecycle_control import BUNDLE_COUNTS, LIVE_BUNDLE_COUNTS, CYCLE_COUNTS
from scripts.performance.linux_native_cycle_limits import cycle_bounds, validate_shape, validate_active_shape
from scripts.performance.linux_native_peer import observe_child, readiness_endpoint, validate_endpoint, wait_target_exec
from scripts.performance.linux_udp_failure import capture_owned_udp
from scripts.performance.post_close_cleanup import FIELDS
from scripts.performance.process_cancellation import Cancellation, not_cancelled


def validate_cpu_pool(pool, cores):
    require(type(cores) is int and cores in (1, 2, 4) and type(pool) is list and len(pool) == cores
            and all(type(cpu) is int and cpu >= 0 for cpu in pool)
            and pool == sorted(set(pool)), 'invalid explicit CPU pool')
    return pool


def parse_cpu_pool(value):
    require(isinstance(value, str) and 0 < len(value) <= 64, 'invalid CPU pool text')
    pool = [int(part) for part in value.split(',')]
    require(value == ','.join(map(str, pool)), 'canonical CPU pool required')
    return validate_cpu_pool(pool, len(pool))


def select_cpu_pool(host, cores, pool):
    if pool is None:
        return host
    validate_cpu_pool(pool, cores)
    require(set(pool) <= set(host['inherited_cpus']), 'requested CPU is unavailable')
    selected = physical_cpu_sets(host['topology'], pool, [cores])[cores]
    require(selected == pool, 'explicit pool does not cover distinct cores on one NUMA node')
    return dict(host, selected_cpus=selected, requested_cpu_pool=list(pool))


def validate_bundle_mode(mode, cycles=None):
    require(type(mode) is str and mode in ('idle-bundles', 'live-bundles'), 'invalid bundle mode')
    require(cycles is None or mode == 'idle-bundles', 'sequential cycles cannot use live bundle mode')
    return mode


def bundle_counts(mode):
    return LIVE_BUNDLE_COUNTS if validate_bundle_mode(mode) == 'live-bundles' else BUNDLE_COUNTS


def command(*, role, count, shards, rate, binaries, authority, lifecycle, output, bind, endpoint, bundle_mode='idle-bundles'):
    validate_bundle_mode(bundle_mode)
    require(role in ('source', 'destination'), 'invalid lifecycle role')
    require(type(count) is int and count in bundle_counts(bundle_mode), 'invalid bundle count')
    require(type(shards) is int and shards in (1, 2), 'invalid source shards')
    require(type(rate) is int and 1 <= rate <= 1000, 'invalid offered rate')
    _, port = validate_endpoint(bind, allow_zero=True)
    common = ['--authority-dir', str(authority), '--b3-materialized-streams', '1']
    if role == 'source':
        require(port == 0, 'source requires ephemeral bind port')
        validate_endpoint(endpoint, allow_zero=False)
        return ([str(binaries / 'perf_rust_source'), *common, '--endpoint', endpoint,
                 '--samples', '1', '--payload-bytes', '1024', '--lifecycle-authority-dir', str(lifecycle),
                 '--connections', '1', '--services', '1', '--streams-per-service', '1',
                 '--concurrent-streams', '--hold-for-release', '--connection-offset', '0',
                 '--diagnostics', '1', '--lifecycle-clients', str(count),
                 '--lifecycle-source-shards', str(shards), '--lifecycle-offered-rate', str(rate),
                 '--benchmark-client-bind', bind] + (['--b3-keep-alive-seconds', '1'] if bundle_mode == 'live-bundles' else []), {})
    require(endpoint is None, 'destination has no remote endpoint')
    return ([str(binaries / 'wp8_interop_server'), *common, '--ready', str(output / 'ready.json'),
             '--result', str(output / 'server-result.json'), '--completion-ack', str(output / 'completion.ack'),
             '--destination-diagnostics-file', str(output / 'diagnostics.ndjson'),
             '--diagnostic-drain-seconds', '2', '--b3-report-gate', str(lifecycle),
             '--benchmark-listen', bind], dict(NBSR_PERF_LIFECYCLE_ROOT=str(lifecycle),
             NBSR_PERF_LIFECYCLE_CONNECTIONS=str(count), NBSR_PERF_LIFECYCLE_SERVICES='1',
             NBSR_PERF_STREAMS_PER_SERVICE='1', NBSR_PERF_CONCURRENT_STREAMS='1',
             NBSR_PERF_CONCURRENT_SESSIONS='1', NBSR_PERF_LIFECYCLE_SERIAL_ACCEPT='1',
             NBSR_PERF_LIFECYCLE_OFFERED_RATE=str(rate)))



def cycle_command(*, role, cycles, binaries, authority, lifecycle, output, bind, endpoint, streams=1, channels=1):
    """Separate sequential workload; private cycle barriers must drive each start.

    This command builder does not make the bundle endpoint cycle-aware. A cycle
    coordinator must retain both peer process epochs and release the source's
    final gate only after the final cooldown.
    """
    require(type(cycles) is int and cycles in CYCLE_COUNTS, 'invalid cycle count')
    validate_shape(streams, channels)
    argv, overrides = command(role=role, count=16, shards=1, rate=100,
        binaries=binaries, authority=authority, lifecycle=lifecycle, output=output,
        bind=bind, endpoint=endpoint)
    if role == 'source':
        argv[argv.index('--connections') + 1] = str(cycles)
        argv[argv.index('--streams-per-service') + 1] = str(streams)
        argv[argv.index('--services') + 1] = str(channels)
        for flag in ('--lifecycle-clients', '--lifecycle-source-shards', '--lifecycle-offered-rate'):
            position = argv.index(flag)
            del argv[position:position + 2]
        argv.extend(['--lifecycle-final-release', str(lifecycle / 'source.final-release')])
    else:
        overrides['NBSR_PERF_LIFECYCLE_CONNECTIONS'] = str(cycles)
        overrides['NBSR_PERF_STREAMS_PER_SERVICE'] = str(streams)
        overrides['NBSR_PERF_LIFECYCLE_SERVICES'] = str(channels)
        for key in ('NBSR_PERF_CONCURRENT_SESSIONS', 'NBSR_PERF_LIFECYCLE_SERIAL_ACCEPT',
                    'NBSR_PERF_LIFECYCLE_OFFERED_RATE'):
            del overrides[key]
    return argv, overrides


def validate_runtime_workers(workers, cores):
    require(type(workers) is int and workers in (1, 2, 4)
            and type(cores) is int and cores in (1, 2, 4) and workers <= cores, 'invalid runtime workers/allocation')
    return workers


def workload_command(args, **paths):
    cycles = getattr(args, 'cycles', None)
    bundle_mode = validate_bundle_mode(getattr(args, 'bundle_mode', 'idle-bundles'), cycles)
    workers = getattr(args, 'runtime_workers', None)
    if workers is not None:
        require(args.role == 'destination', 'explicit runtime workers supported only for destination')
        validate_runtime_workers(workers, args.cores)
        require(cycles is None, 'explicit runtime workers only supported for bundles')
    if cycles is not None:
        require(args.count == cycles and args.rate is None and args.shards is None,
                'sequential cycles have no offered-rate/fanout contract')
        return cycle_command(role=args.role, cycles=cycles, streams=getattr(args, 'streams', 1), channels=getattr(args, 'channels', 1), **paths)
    argv, overrides = command(role=args.role, count=args.count, shards=args.shards, rate=args.rate, bundle_mode=bundle_mode, **paths)
    return argv + (['--p2a-runtime-workers', str(workers)] if workers is not None else []), overrides


def validate_result(role, count, rows, server, *, streams=1, channels=1):
    total = validate_shape(streams, channels)
    require(role in ('source', 'destination') and rows, 'missing lifecycle result')
    if role == 'source':
        require(not any(row.get('success') is False or row.get('error') for row in rows), 'source failure')
        completed = [row for row in rows if row.get('success') is True]
        ids = [row.get('logical_client_id') for row in completed]
        require(len(completed) == count * total and all(type(i) is int for i in ids)
                and Counter(ids) == dict.fromkeys(range(count), total), 'source client cardinality mismatch')
        if total > 1:
            require([row.get('sample_id') for row in completed] == list(range(count * total))
                    and all(type(row.get('sample_id')) is int for row in completed)
                    and ids == [i // total for i in range(count * total)], 'source stream sample identity mismatch')
            active = [row for row in rows if row.get('phase') == 'b3_materialized_streams_ready']
            require(len(active) == count, 'source active cycle cardinality mismatch')
            for row in active:
                validate_active_shape(row, streams, channels)
        require(all(type(row.get(key)) is int and row[key] == 1024 for row in completed
                    for key in ('bytes_transmitted', 'bytes_received')), 'source payload mismatch')
        final = [row for row in rows if row.get('phase') == 'lifecycle_cleanup']
        require(len(final) == 1, 'missing or duplicate source cleanup')
        final = final[0]
    else:
        require(isinstance(server, dict) and server.get('status') == 'PASS'
                and type(server.get('connections')) is int and server['connections'] == count
                and isinstance(server.get('samples'), list) and len(server['samples']) == count * total,
                'destination cardinality mismatch')
        if total > 1:
            require(type(server.get('streams_per_service')) is int and server['streams_per_service'] == streams
                    and type(server.get('services_per_connection')) is int and server['services_per_connection'] == channels,
                    'destination stream shape mismatch')
        final = rows[-1]
    require(all(type(final.get(field)) is int and final[field] == 0 for field in FIELDS),
            'all eleven final ownership counters must be explicitly zero')
    return dict(successful=count, ownership_all_zero=True,
                ownership={field: final[field] for field in FIELDS})


def immutable_fixture(authority, lifecycle, role, channels=1):
    names = ('name.txt', 'route-open-body.cbor', 'federation-context.cbor', 'source.cose',
             'destination.cose', 'request-id.bin', 'channel-id.bin', 'route-id.bin', 'grant-digest.bin')
    require((authority / f'{role}-key.der').is_file(), 'role private key required')
    return dict(certificates={n: digest(authority / n) for n in ('ca.der', 'source.der', 'destination.der')},
                service={(n if channels == 1 else f'{i:02}/{n}'): digest(lifecycle / f'{i:02}' / n)
                         for i in range(channels) for n in names})


def wait_readiness(path, address, *, check_cancelled=not_cancelled):
    """Management-only readiness wait; no transport exists during this wait."""
    deadline = time.monotonic() + 30
    while True:
        check_cancelled()
        if time.monotonic() >= deadline:
            raise TimeoutError('prepared source readiness deadline')
        try:
            return readiness_endpoint(path, address)
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(.01)


def execute(args, *, check_cancelled=not_cancelled):
    require(platform.system() == 'Linux', 'Linux required')
    require(not any(k.startswith('NBSR_') for k in os.environ), 'remove inherited NBSR settings')
    sha, dirty = git_state()
    require(not dirty, 'clean checkout required')
    output, authority, lifecycle, binaries = (p.resolve() for p in
        (args.output, args.authority, args.lifecycle, args.binaries))
    require(not output.is_relative_to(ROOT), 'evidence must be outside checkout')
    for private in (authority, lifecycle):
        require(not private.is_relative_to(output) and not output.is_relative_to(private),
                'private fixture and evidence must be disjoint')
    require(lifecycle.is_dir(), 'existing fresh lifecycle fixture required')
    memory_observer = getattr(args, 'memory_observer', False)
    require(type(memory_observer) is bool, 'boolean memory observer required')
    bundle_mode = validate_bundle_mode(getattr(args, 'bundle_mode', 'idle-bundles'), getattr(args, 'cycles', None))
    channels = getattr(args, 'channels', 1)
    validate_shape(getattr(args, 'streams', 1), channels)
    require(all((p.is_dir() and p.name in {f'{i:02}' for i in range(channels)}) or (p.is_file() and p.name in
                {f'connection-{i}.start' for i in range(args.count)}) for p in lifecycle.iterdir()),
            'lifecycle fixture contains stale or unexpected markers')
    bind_ip, _ = validate_endpoint(args.bind, allow_zero=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind((bind_ip, 0))
    prepared = getattr(args, 'prepare_before_readiness', False)
    require(not prepared or args.role == 'source', 'only source may prepare before readiness')
    if args.role == 'source':
        require(args.ready_input is not None and args.destination_address is not None,
                'source requires transferred readiness and expected destination')
        require(not prepared or not args.ready_input.exists(), 'prepared source requires fresh readiness path')
        endpoint = None if prepared else readiness_endpoint(args.ready_input, args.destination_address)
    else:
        require(args.ready_input is None and args.destination_address is None, 'unexpected readiness input')
        endpoint = None
    build = json.loads(args.build_manifest.read_bytes())
    hashes = {name: digest(binaries / name) for name in NAMES.values()}
    require(build.get('source_sha') == sha and build.get('build_profile') == 'release'
            and build.get('binary_sha256') == hashes and build.get('build_commands')
            and build.get('toolchains'), 'exact current release build manifest required')
    controller_seconds = cycle_bounds(args.cycles)['controller_seconds'] if getattr(args, 'cycles', None) is not None else 120
    fixture = immutable_fixture(authority, lifecycle, args.role, channels)
    # Validate the declared workload before advertising preparation. The real
    # endpoint is validated again after transfer; this placeholder is never run.
    workload_command(args,
        binaries=binaries, authority=authority, lifecycle=lifecycle, output=output,
        bind=args.bind, endpoint=f'{args.destination_address}:1' if prepared else endpoint)
    binary = binaries / ('perf_rust_source' if args.role == 'source' else 'wp8_interop_server')
    require(os.access(binary, os.X_OK), 'executable peer required')
    host = select_cpu_pool(environment(args.cores), args.cores, getattr(args, 'cpu_pool', None))
    check_cancelled()
    output.mkdir(parents=True, exist_ok=False)
    child = None
    try:
        shutil.copyfile(binary, output / 'executed-binary')
        if prepared:
            write_json(output / 'source-prepared.json', dict(status='PREPARED_NOT_CONNECTED',
                repository_sha=sha, timestamp_ns=time.monotonic_ns(), readiness_deadline_seconds=30))
            endpoint = wait_readiness(args.ready_input, args.destination_address, check_cancelled=check_cancelled)
        argv, overrides = workload_command(args,
            binaries=binaries, authority=authority, lifecycle=lifecycle, output=output,
            bind=args.bind, endpoint=endpoint)
        argv = [host['taskset'], '--cpu-list', ','.join(map(str, host['selected_cpus'])), *argv]
        write_json(output / 'environment.json', dict(repository_sha=sha, role=args.role,
            count=args.count, offered_rate=args.rate, source_shards=args.shards, linux_environment=host,
            **({'runtime_workers': args.runtime_workers} if getattr(args, 'runtime_workers', None) is not None else {}),
            uid=os.getuid(), binary_sha256=hashes, fixture_sha256=fixture,
            controller_deadline_seconds=controller_seconds, memory_observer=memory_observer, bundle_mode=bundle_mode, timing='DIAGNOSTIC_ONLY', physical_host='NOT_PROVEN',
            **({'cycles': args.cycles, 'streams': getattr(args, 'streams', 1), 'channels': channels, 'workload_mode': 'same_process_sequential'}
               if getattr(args, 'cycles', None) is not None else {})))
        write_json(output / 'command.json', dict(argv=argv, environment_overrides=overrides))
        write_json(output / 'build-manifest.json', build)
        if args.ready_input is not None:
            shutil.copyfile(args.ready_input, output / 'input-readiness.json')
        with (output / 'stdout').open('xb') as stdout, (output / 'stderr').open('xb') as stderr:
            child = subprocess.Popen(argv, cwd=ROOT, env=os.environ | overrides,
                stdout=stdout, stderr=stderr, start_new_session=True)
            write_json(output / 'pid.json', dict(pid=child.pid, owns_process_group=True))
            check_cancelled()
            deadline = time.monotonic() + controller_seconds
            wait_target_exec(child, binary, check_cancelled=check_cancelled)
            observer = nullcontext(None)
            if memory_observer:
                initial = sample_process(child.pid, host['selected_cpus'])
                observer = CycleMemoryObserver(output, pid=child.pid, start_ticks=initial['start_ticks'],
                                               cpus=host['selected_cpus'], cycles=getattr(args, 'cycles', None))
            with observer as memory:
                observed = observe_child(child, host['selected_cpus'], output, deadline=deadline,
                    check_cancelled=check_cancelled, **({'live_observer': memory} if memory_observer else {}))
            if memory_observer:
                write_json(output / 'exit.json', observed)
        rows = [json.loads(line) for line in (output / ('stdout' if args.role == 'source'
                    else 'diagnostics.ndjson')).read_text().splitlines() if line.strip()]
        server = json.loads((output / 'server-result.json').read_bytes()) if args.role == 'destination' else None
        result = validate_result(args.role, args.count, rows, server, streams=getattr(args, 'streams', 1), channels=channels)
        require(not list(lifecycle.glob('*.failed')), 'failed lifecycle marker')
        require(git_state() == (sha, '') and json.loads(args.build_manifest.read_bytes()) == build,
                'source or build manifest changed')
        require(all(digest(binaries / n) == h for n, h in hashes.items())
                and digest(output / 'executed-binary') == hashes[binary.name], 'binary changed')
        require(immutable_fixture(authority, lifecycle, args.role, channels) == fixture, 'public fixture changed')
        check_cancelled()
        write_json(output / 'result.json', dict(status='PASS_FUNCTIONAL_PEER', role=args.role,
            **result, process=observed, timing='DIAGNOSTIC_ONLY', paired_active_hold='COORDINATOR_REQUIRED',
            sustainable_capacity='NOT_ESTABLISHED', external_hardware='NOT_PROVEN'))
        return result
    except BaseException as error:
        write_json(output / 'failure.json', dict(status='INVALID_PARTIAL', error_type=type(error).__name__, error=str(error)))
        if child is not None and child.returncode is None and (output / 'resources.ndjson').exists():
            try:
                first = json.loads((output / 'resources.ndjson').read_text().splitlines()[0])
                write_json(output / 'failure-udp.json', capture_owned_udp({args.role: child},
                           {child.pid: first['start_ticks']}))
            except (OSError, ValueError, IndexError) as diagnostic_error:
                write_json(output / 'failure-udp-unavailable.json', dict(error=str(diagnostic_error)))
        raise
    finally:
        if child is not None and child.returncode is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            code = child.wait(timeout=5)
            write_json(output / 'forced-cleanup.json', dict(exit_code=code, valid=False, group_killed=True))
        seal_output(output)


def argument_parser(*, sequential=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=('source', 'destination'), required=True)
    for name in ('binaries', 'build-manifest', 'authority', 'lifecycle', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--bind', required=True)
    parser.add_argument('--ready-input', type=Path)
    parser.add_argument('--destination-address')
    parser.add_argument('--prepare-before-readiness', action='store_true',
                        help='source: finish preflight/copy, publish prepared marker, then await fresh readiness')
    if sequential:
        parser.add_argument('--cycles', type=int, choices=CYCLE_COUNTS, required=True)
        parser.add_argument('--streams', type=int, default=1)
        parser.add_argument('--channels', type=int, default=1)
        parser.set_defaults(count=None, shards=None, rate=None)
    else:
        parser.add_argument('--count', type=int, choices=LIVE_BUNDLE_COUNTS, default=16)
        parser.add_argument('--bundle-mode', choices=('idle-bundles', 'live-bundles'), default='idle-bundles')
        parser.add_argument('--shards', type=int, choices=(1, 2), default=2)
        parser.add_argument('--rate', type=int, default=100)
    if not sequential:
        parser.add_argument('--runtime-workers', type=int, choices=(1, 2, 4), help='Explicit benchmark runtime workers; cannot exceed allocated cores')
    parser.add_argument('--memory-observer', action='store_true')
    parser.add_argument('--cores', type=int, choices=(1, 2, 4), default=1)
    parser.add_argument('--cpu-pool', type=parse_cpu_pool,
                        help='Optional canonical logical CPU IDs; requires distinct advertised cores on one NUMA node')
    return parser


def main():
    args = argument_parser().parse_args()
    with Cancellation() as cancellation:
        execute(args, check_cancelled=cancellation.check)


if __name__ == '__main__':
    main()
