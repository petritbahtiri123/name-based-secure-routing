"""B3 Rust same-process lifecycle and simultaneous resource scale."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_b3_session_lifecycle as b3
from scripts.run_b4b_task4k import checksums
from scripts.performance.process_cancellation import Cancellation, not_cancelled


def binary_names(platform_name, path="rust-rust"):
    if platform_name not in ('windows', 'linux'):
        raise ValueError('explicit supported platform required')
    suffix = '.exe' if platform_name == 'windows' else ''
    if path not in ('rust-rust', 'go-rust'):
        raise ValueError('explicit supported peer path required')
    source = {'rust': 'perf_rust_source' + suffix} if path == 'rust-rust' else {'go': 'nbsr-go-peer' + suffix}
    return {**source, 'server': 'wp8_interop_server' + suffix}


def validate_linux_manifest(path, binaries, peer_path="rust-rust"):
    if path is None:
        raise ValueError('Linux build manifest required')
    manifest = json.loads(Path(path).read_text())
    expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries.values()}
    if (set(binaries) != set(binary_names('linux', peer_path)) or not re.fullmatch(r'[0-9a-f]{40}', str(manifest.get('source_sha', '')))
            or manifest.get('build_profile') != 'release' or not manifest.get('build_commands')
            or not manifest.get('toolchains') or not isinstance(manifest.get('binary_sha256'), dict)
            or any(manifest['binary_sha256'].get(name) != digest for name, digest in expected.items())):
        raise ValueError('Linux binary hashes/source/build metadata mismatch')
    return manifest


def verify_linux_execution(binaries, retained, build):
    for original in binaries.values():
        expected = build['binary_sha256'][original.name]
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != expected
               for path in (original, retained / original.name)):
            raise ValueError('Linux executable/retained bytes changed before launch')


def spec_for(axis, count, repeat, *, materialized_streams=False, fixed_channels=8, accept_window=None):
    if accept_window is not None and (
            type(accept_window) is not int or accept_window not in (1, 2, 4, 8, 16, 32)
            or axis not in ('bundles', 'live-bundles') or count < 2 or accept_window > count):
        raise ValueError('accept window requires an explicit bounded simultaneous-bundle diagnostic')
    if type(fixed_channels) is not int or not 1 <= fixed_channels <= 32:
        raise ValueError("fixed channels must fit the existing 1..32 authority bound")
    if axis != "streams" and fixed_channels != 8:
        raise ValueError("fixed channel override applies only to the streams axis")
    spec = dict(name=f"{axis}-{count}-r{repeat}", kind=axis, active_count=count,
                sessions=1, channels=1, streams=1, cycles=1, start_rate=100)
    if axis in ("bundles", "live-bundles"):
        maximum = 4096 if axis == "live-bundles" else 1024
        if not 1 <= count <= maximum:
            raise ValueError(f"logical client bound is {maximum}")
        spec.update(sessions=count, kind="sessions",
                    resource_scope="one authenticated connection + session + channel + stream per bundle")
        if axis == "live-bundles":
            spec.update(keep_alive_seconds=1,
                        resource_scope="one authenticated connection + session + channel + stream per bundle; QUIC keepalive every 1 second")
    elif axis == "channels":
        if not 1 <= count <= 32:
            raise ValueError("frozen harness authority supports at most 32 services per connection")
        spec.update(channels=count, resource_scope="channels with one stream each; one connection/session")
    elif axis == "streams":
        if count % fixed_channels or not fixed_channels <= count <= 64 * fixed_channels:
            raise ValueError("stream axis requires 1..64 streams per fixed channel")
        label = "eight" if fixed_channels == 8 else str(fixed_channels)
        spec.update(channels=fixed_channels, streams=count // fixed_channels,
                    resource_scope=f"application streams across {label} fixed channels; one connection/session")
        if fixed_channels != 8:
            spec["name"] = f"streams-c{fixed_channels}-{count}-r{repeat}"
    elif axis == "cycles":
        if not 1 <= count <= 100:
            raise ValueError("bounded cycle count required")
        spec.update(cycles=count, streams=64, active_count=64, cycle_mode="same-process",
                    resource_scope="same source/destination processes; one session/channel and 64 streams per cycle")
    else:
        raise ValueError("unknown resource axis")
    spec.update(materialized_streams=materialized_streams,
                stream_residency="materialized request and both endpoint handles" if materialized_streams else "registry-only; destination stream handles not proven during hold")
    if accept_window is not None:
        spec['accept_window'] = accept_window
    return spec


def go_specs(args, specs):
    if (args.axis not in ('channels', 'streams', 'cycles') or args.materialized_streams
            or getattr(args, 'allocator_snapshots', False)):
        raise ValueError('Go B3 supports sequential channels/streams/cycles without Rust-only observers')
    return [dict(spec, destination_completion=True, start_rate=0,
                 resource_scope=spec.get('resource_scope', '') + '; Go local handles, not destination materialization')
            for spec in specs]


def execute(args, *, check_cancelled=not_cancelled):
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    source_status = subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=all'], text=True)
    if source_status:
        raise ValueError('B3 requires a clean checkout before evidence creation')
    platform_name = getattr(args, 'platform', 'windows')
    peer_path = getattr(args, 'path', 'rust-rust')
    binary_names(platform_name, peer_path)
    linux = None
    if platform_name == 'linux':
        from scripts.performance.b3_linux import LinuxCapture, environment
        linux = environment(args.cores)
    specs = [spec_for(args.axis, count, repeat, materialized_streams=args.materialized_streams,
                      fixed_channels=args.fixed_channels, accept_window=getattr(args, 'accept_window', None))
             for count in args.counts for repeat in range(1, args.repeats + 1)]
    if peer_path == 'go-rust':
        specs = go_specs(args, specs)
    from scripts.performance.b3_allocator_snapshot import observer_spec
    specs = [observer_spec(spec, platform=platform_name,
                           enabled=getattr(args, 'allocator_snapshots', False)) for spec in specs]
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "binaries").mkdir()
    binaries = {}
    for role, name in binary_names(platform_name, peer_path).items():
        original = args.target / "release" / name
        retained = args.output / "binaries" / name
        shutil.copy2(original, retained)
        binaries[role] = original if linux else retained
    build = validate_linux_manifest(args.build_manifest, binaries, peer_path) if linux else None
    metadata = {"schema": "nbsr-b3-v2-raw-v1", "classification": "DIAGNOSTIC" if args.repeats < 3 else "MEASURED_PENDING_ANALYSIS",
                "source_sha": source_sha, "git_status": source_status,
                "binary_sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in binaries.items()},
                "workloads": specs, "scope": "Windows loopback; Rust to Rust; no server-class claim",
                "stream_residency": specs[0]["stream_residency"],
                "destination_ready_snapshot_scope": "aggregate ownership across all live sessions; not per-connection",
                "source_processes": 1, "source_runtime_shards": "2 for simultaneous bundles; 1 for sequential cycles",
                "acceptance_scope": f"B3-only {specs[0].get('accept_window', 1)} armed accepts, concurrent held sessions; not the B4 admission-capacity workload",
                "memory_scope": "private bytes/working set/handles/threads and ownership, not allocator heap attribution",
                "live_resource_proof": "all named .active markers observed before active sampling and before any release"}
    metadata.update(peer_path=peer_path, ownership_scope='rust-all-11-current-fields' if peer_path == 'rust-rust' else 'historical-go-destination-8-fields; source process exit only')
    if peer_path == 'go-rust':
        metadata.update(scope='Windows loopback; Go to Rust; diagnostic resource totals only',
                        source_runtime_shards='one sequential Go source',
                        acceptance_scope='local held-resource lifecycle, not sustainable admission',
                        final_source_cooldown='unavailable after natural exit; no zero substitution')
    if linux:
        metadata.update(platform='linux', linux_environment=linux, build_manifest=build,
                        benchmark_udp_receive_buffer_request=os.environ.get('NBSR_BENCH_UDP_RECEIVE_BUFFER_BYTES'),
                        scope=linux['scope'],
                        memory_scope='Linux smaps private resident/RSS/PSS/separate hugetlb, FD/thread counts; no Windows commit/handle aliases',
                        binary_source_sha=build['source_sha'],
                        execution_paths={role: str(path.resolve()) for role, path in binaries.items()},
                        retained_paths={role: str((args.output / 'binaries' / path.name).resolve()) for role, path in binaries.items()},
                        binary_provenance='declared build source SHA and actual-byte hash verification; distinct from controller source SHA')
        if build['source_sha'] != metadata['source_sha']:
            metadata['classification'] = 'DIAGNOSTIC_BINARY_SOURCE_MISMATCH'
        b3.write_json(args.output / 'build-manifest.json', build)
    b3.write_json(args.output / "environment.json", metadata)
    (args.output / "source.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary"]))
    sources = ["scripts/run_b3_v2.py", "scripts/run_b3_session_lifecycle.py",
                   "scripts/performance/b3_failure_markers.py",
                   "crates/nbsr-transport/src/config.rs",
                   "crates/nbsr-transport/src/udp_socket.rs",
                   "crates/nbsr-transport/src/bin/perf_rust_source.rs",
                   "crates/nbsr-transport/src/bin/benchmark_support/allocator_snapshot.rs",
                   "scripts/performance/b3_allocator_snapshot.py",
                   "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
                   "crates/nbsr-transport/src/bin/b3_support/mod.rs",
                   "crates/nbsr-transport/src/bin/b3_support/marker_monitor.rs",
                   "crates/nbsr-transport/src/bin/b3_support/marker_notifications.rs",
                   "crates/nbsr-transport/src/bin/benchmark_support/lifecycle_accept_window.rs"]
    if peer_path == 'go-rust':
        sources += ['interop/nbsr-go-peer/cmd/nbsr-go-peer/main.go',
                    'interop/nbsr-go-peer/cmd/nbsr-go-peer/lifecycle_completion.go',
                    'crates/nbsr-transport/src/bin/benchmark_support/b3_peer_completion.rs',
                    'scripts/performance/b3_go_linux_analysis.py']
    if linux:
        sources += ['scripts/performance/b3_linux.py', 'scripts/performance/b3_linux_analysis.py',
                    'scripts/performance/process_cancellation.py',
                    'scripts/performance/linux_resources.py', 'scripts/performance/linux_loopback.py',
                    'scripts/performance/linux_udp_failure.py']
    for source in sources:
        dest = args.output / "source" / source
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    records = []
    try:
        for spec in specs:
            check_cancelled()
            print(spec["name"], flush=True)
            options = {}
            if linux:
                verify_linux_execution(binaries, args.output / 'binaries', build)
                rounds = 1 if spec['sessions'] > 1 else spec['cycles']
                cap = 2 * (rounds + 1) * (3 * (math.ceil(2 / .5) + 2))
                options['capture_backend'] = LinuxCapture(linux['selected_cpus'], linux['taskset'], max_records=cap,
                                                         check_cancelled=check_cancelled)
            row = b3.run_cell(peer_path, spec, binaries, args.output,
                              idle_seconds=2, active_seconds=2, cooldown_seconds=2, cadence=0.5, **options)
            check_cancelled()
            records.append(row)
            b3.write_json(args.output / "records.json", records)
            if not row["cleanup"]["all_zero"]:
                raise RuntimeError("nonzero ownership; preserve and investigate")
    except Exception as error:
        b3.write_json(args.output / 'failure.json', dict(classification='INVALID_PARTIAL',
                      error_type=type(error).__name__, error=str(error)))
        raise
    finally:
        checksums(args.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=Path(r"C:\NBSR-build\b4b-task4k"))
    parser.add_argument('--path', choices=('rust-rust', 'go-rust'), default='rust-rust')
    parser.add_argument('--platform', choices=('windows', 'linux'), default='windows')
    parser.add_argument('--cores', type=int, choices=(1, 2, 4), default=1,
                        help='Linux only: shared physical-core-selected logical pool')
    parser.add_argument('--build-manifest', type=Path, help='Linux only: release source SHA, binary hashes and build metadata')
    parser.add_argument("--axis", choices=("bundles", "live-bundles", "channels", "streams", "cycles"), required=True)
    parser.add_argument('--allocator-snapshots', action='store_true',
                        help='Linux/glibc cycles only: diagnostic source allocator XML at entry and post-close')
    parser.add_argument("--counts", type=int, nargs="+", required=True)
    parser.add_argument("--repeats", type=int, choices=(1, 3, 5), default=5)
    parser.add_argument("--fixed-channels", type=int, default=8,
                        help="streams axis only: hold 1..32 channels fixed; default 8")
    parser.add_argument("--accept-window", type=int, choices=(1, 2, 4, 8, 16, 32),
                        help="B3 simultaneous bundles only: diagnostic armed accepts; omitted keeps serial default")
    parser.add_argument("--materialized-streams", action="store_true", help="retain authorized request and both endpoint stream handles during active hold")
    args = parser.parse_args()
    try:
        if args.platform == 'linux':
            with Cancellation() as cancellation:
                execute(args, check_cancelled=cancellation.check)
        else:
            execute(args)
    except Exception as error:
        print(f"B3_FAILED: {type(error).__name__}; retained details under {args.output}", file=sys.stderr)
        sys.exit(1)
