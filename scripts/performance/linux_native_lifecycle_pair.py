"""Read-only pair verification for native lifecycle peers; no capacity claim.

Checksums detect corruption, not forgery or remote-host identity. Paired active
barriers remain a coordinator obligation, independently of per-peer outcomes.
"""

import argparse
import json
from pathlib import Path, PurePosixPath
import re
from types import SimpleNamespace

from scripts.performance.linux_b5_ceiling import NAMES, require
from scripts.performance.linux_loopback import digest
from scripts.performance.linux_native_lifecycle import workload_command, select_cpu_pool, validate_result, validate_bundle_mode
from scripts.performance.linux_native_lifecycle_control import BUNDLE_COUNTS, CYCLE_COUNTS
from scripts.performance.linux_native_cycle_limits import cycle_bounds
from scripts.performance.linux_native_cycle_memory import verify_memory
from scripts.performance.linux_native_pair import read, verify_index
from scripts.performance.linux_native_peer import validate_endpoint


def check_peer(root, role, source_sha, count, *, cycles=None, streams=1, channels=1, memory_observer=False, bundle_mode='idle-bundles'):
    validate_bundle_mode(bundle_mode, cycles)
    require(type(memory_observer) is bool, 'invalid memory observer mode')
    index = verify_index(root)
    require(not any((root / name).exists() for name in ("failure.json", "forced-cleanup.json")), "failed or forced peer cannot pass")
    env, result, build = (read(root, n) for n in ("environment.json", "result.json", "build-manifest.json"))
    require(
        env["role"] == result["role"] == role
        and env["repository_sha"] == source_sha
        and type(env["count"]) is int
        and env["count"] == count,
        "role/source/count mismatch",
    )
    require(
        type(env["uid"]) is int
        and env["uid"] > 0
        and env["controller_deadline_seconds"] == (120 if cycles is None else cycle_bounds(cycles)["controller_seconds"])
        and env["timing"] == result["timing"] == "DIAGNOSTIC_ONLY",
        "peer execution scope mismatch",
    )
    require(type(env.get('memory_observer', False)) is bool and env.get('memory_observer', False) == memory_observer,
            'memory observer mode mismatch')
    require(env.get('bundle_mode', 'idle-bundles') == bundle_mode, 'bundle mode mismatch')
    if cycles is not None:
        require(type(cycles) is int and cycles in CYCLE_COUNTS and count == cycles
                and type(env.get('cycles')) is int and env['cycles'] == cycles
                and env.get('workload_mode') == 'same_process_sequential'
                and env['offered_rate'] is None and env['source_shards'] is None
                and type(env.get('channels', 1)) is int and env.get('channels', 1) == channels
                and type(env.get('streams', 1)) is int and env.get('streams', 1) == streams,
                'sequential cycle contract mismatch')
    else:
        require(channels == streams == 1 and 'cycles' not in env and 'workload_mode' not in env, 'unexpected cycle mode')
    hashes = env["binary_sha256"]
    require(set(hashes) == set(NAMES.values()) and all(re.fullmatch("[0-9a-f]{64}", h) for h in hashes.values()), "invalid binary hashes")
    require(
        build["source_sha"] == source_sha
        and build["build_profile"] == "release"
        and build["binary_sha256"] == hashes
        and build["build_commands"]
        and build["toolchains"],
        "release build mismatch",
    )
    name = NAMES["nbsr" if role == "source" else "server"]
    require(digest(root / "executed-binary") == hashes[name], "executed binary mismatch")
    fixture = env["fixture_sha256"]
    expected_service = {
        "name.txt",
        "route-open-body.cbor",
        "federation-context.cbor",
        "source.cose",
        "destination.cose",
        "request-id.bin",
        "channel-id.bin",
        "route-id.bin",
        "grant-digest.bin",
    }
    if channels > 1:
        expected_service = {f'{i:02}/{n}' for i in range(channels) for n in expected_service}
    require(
        set(fixture) == {"certificates", "service"}
        and set(fixture["certificates"]) == {"ca.der", "source.der", "destination.der"}
        and set(fixture["service"]) == expected_service
        and all(re.fullmatch("[0-9a-f]{64}", h) for group in fixture.values() for h in group.values()),
        "invalid public fixture hashes",
    )
    recorded = read(root, "command.json")
    argv = recorded["argv"]
    require(len(argv) > 4 and all(type(a) is str for a in argv), "invalid argv")

    def option(flag):
        require(argv.count(flag) == 1 and argv.index(flag) + 1 < len(argv), "missing/duplicate option " + flag)
        return argv[argv.index(flag) + 1]

    cpus = env["linux_environment"]["selected_cpus"]
    require(len(cpus) in (1, 2, 4) and all(type(c) is int and c >= 0 for c in cpus) and len(set(cpus)) == len(cpus), "invalid CPU pool")
    if 'requested_cpu_pool' in env['linux_environment']:
        selected = select_cpu_pool(env['linux_environment'], len(cpus), env['linux_environment']['requested_cpu_pool'])
        require(selected['selected_cpus'] == cpus, 'requested/observed CPU pool mismatch')
    binary = PurePosixPath(argv[3])
    require(binary.name == name, "wrong role binary")
    bind = option("--benchmark-client-bind" if role == "source" else "--benchmark-listen")
    bind_host, _ = validate_endpoint(bind, allow_zero=True)
    endpoint = option("--endpoint") if role == "source" else None
    lifecycle = option("--lifecycle-authority-dir" if role == "source" else "--b3-report-gate")
    output = PurePosixPath(option("--ready")).parent if role == "destination" else PurePosixPath("/unused")
    expected, overrides = workload_command(
        SimpleNamespace(role=role, count=count, cycles=cycles, streams=streams, channels=channels, bundle_mode=bundle_mode, shards=env["source_shards"], rate=env["offered_rate"]),
        binaries=binary.parent,
        authority=PurePosixPath(option("--authority-dir")),
        lifecycle=PurePosixPath(lifecycle),
        output=output,
        bind=bind,
        endpoint=endpoint,
    )
    require(
        argv == [env["linux_environment"]["taskset"], "--cpu-list", ",".join(map(str, cpus)), *expected]
        and recorded["environment_overrides"] == overrides,
        "command/environment mismatch",
    )
    ready = read(root, "input-readiness.json" if role == "source" else "ready.json")
    ready_host, ready_port = validate_endpoint(ready["endpoint"], allow_zero=False)
    require(ready["alpn"] == "nbsr-quic-1", "readiness ALPN mismatch")
    if role == "source":
        require(ready["endpoint"] == endpoint, "source readiness/endpoint mismatch")
    else:
        _, requested_port = validate_endpoint(bind, allow_zero=True)
        require(ready_host == bind_host and (requested_port == 0 or requested_port == ready_port), "destination readiness/bind mismatch")
    pid, exited = read(root, "pid.json"), read(root, "exit.json")
    require(
        pid["owns_process_group"] is True
        and result["status"] == "PASS_FUNCTIONAL_PEER"
        and result["process"] == exited
        and exited["exit_code"] == 0,
        "exit contract failed",
    )
    first = last = None
    first_resource = None
    with (root / "resources.ndjson").open() as stream:
        for line in stream:
            row = json.loads(line)
            if first_resource is None:
                first_resource = row
            identity = row["pid"], row["start_ticks"]
            first = identity if first is None else first
            require(identity == first and row["pid"] == pid["pid"], "resource PID epoch changed")
            require(
                all(type(row.get(n)) is int and row[n] >= 0 for n in ("timestamp_ns", "cpu_ns", "rss_bytes")), "invalid resource counters"
            )
            require(
                row["affinity"] == cpus
                and (last is None or (row["cpu_ns"] >= last["cpu_ns"] and row["timestamp_ns"] >= last["timestamp_ns"])),
                "resource affinity/counter regression",
            )
            last = row
    require(last is not None and last["state"] == "Z" and last == exited["final_sample"], "terminal sample mismatch")
    if memory_observer:
        memory = verify_memory(root, pid=last['pid'], start_ticks=last['start_ticks'], cpus=cpus, cycles=cycles, lifetime=(first_resource, last))
        require(exited.get('cycle_memory') == memory, 'memory summary/raw mismatch')
    else:
        require(not (root / 'memory.ndjson').exists() and 'cycle_memory' not in exited, 'unexpected memory observer evidence')
    rows = [
        json.loads(line)
        for line in (root / ("stdout" if role == "source" else "diagnostics.ndjson")).read_text().splitlines()
        if line.strip()
    ]
    if cycles is not None and role == 'source':
        closed = [row for row in rows if str(row.get('phase', '')).startswith('lifecycle_cycle_')]
        require([row.get('phase') for row in closed] == [f'lifecycle_cycle_{i}_closed' for i in range(cycles)],
                'missing/duplicate/out-of-order cycle cleanup observations')
    outcome = validate_result(role, count, rows, read(root, "server-result.json") if role == "destination" else None, streams=streams, channels=channels)
    require(all(result.get(k) == v for k, v in outcome.items()), "summary/raw outcome mismatch")
    return dict(index_sha256=index, environment=env, readiness=ready, outcome=outcome)


def analyze(source, destination, *, source_sha, count, memory_observer=False, bundle_mode='idle-bundles'):
    require(
        re.fullmatch("[0-9a-f]{40}", source_sha) and type(count) is int and count in BUNDLE_COUNTS,
        "invalid expected source/count",
    )
    require(source.resolve() != destination.resolve(), "distinct peer roots required")
    source_peer = check_peer(source, "source", source_sha, count, memory_observer=memory_observer, bundle_mode=bundle_mode)
    destination_peer = check_peer(destination, "destination", source_sha, count, memory_observer=memory_observer, bundle_mode=bundle_mode)
    for field in ("count", "offered_rate", "source_shards", "binary_sha256", "fixture_sha256"):
        require(source_peer["environment"][field] == destination_peer["environment"][field], "paired workload/fixture mismatch: " + field)
    require(source_peer["readiness"] == destination_peer["readiness"], "transferred readiness mismatch")
    return dict(
        status="PASS_FUNCTIONAL_PEER_PAIR",
        source_sha=source_sha,
        successful_connections=count,
        source_index_sha256=source_peer["index_sha256"],
        destination_index_sha256=destination_peer["index_sha256"],
        source_cleanup=source_peer["outcome"]["ownership"],
        destination_cleanup=destination_peer["outcome"]["ownership"],
        paired_active_hold="NOT_VERIFIED_BY_THIS_GATE",
        sustainable_capacity="NOT_ESTABLISHED",
        physical_hardware="NOT_PROVEN",
        **({"private_memory": "MEASURED_DIAGNOSTIC_ONLY_OBSERVER_NOT_QUALIFIED"} if memory_observer else {}),
        **({"bundle_mode": bundle_mode} if bundle_mode == 'live-bundles' else {}),
        scope="Checksummed trusted benchmark artifacts; not signatures or remote attestation",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "destination", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--memory-observer", action="store_true")
    parser.add_argument('--bundle-mode', choices=('idle-bundles', 'live-bundles'), default='idle-bundles')
    args = parser.parse_args()
    require(
        not any(args.output.resolve().is_relative_to(p.resolve()) for p in (args.source, args.destination)),
        "analysis output must not modify peer evidence",
    )
    result = analyze(args.source, args.destination, source_sha=args.source_sha, count=args.count, memory_observer=args.memory_observer, bundle_mode=args.bundle_mode)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
