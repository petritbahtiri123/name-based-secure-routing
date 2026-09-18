"""Strict Linux single-core finite-reference loader; no observer-cost qualification."""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from scripts.performance.b3_linux import environment
from scripts.performance.linux_loopback import ROOT, digest, physical_cpu_sets, repeat_target
from scripts.performance.linux_b5_reference import OBSERVER, SOURCE_PATHS, commands, finish_record, read_binary_record
from scripts.performance.physical_core_analysis import classify_ladder
from scripts.performance.post_close_cleanup import validate_report

NAMES = {"direct": "perf_direct_peer", "nbsr": "perf_rust_source", "server": "wp8_interop_server"}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate_ladder(workload, rows):
    depths = workload["depths"]
    require(
        type(depths) is list
        and depths
        and depths[0] == 1
        and all(type(d) is int and d in (1, 2, 4, 8, 16) for d in depths)
        and depths == sorted(set(depths)),
        "ordered declared ladder must begin at depth one",
    )
    require(
        {(r["path"], r["outstanding_per_stream"]) for r in rows} == {(p, d) for p in ("direct", "nbsr") for d in depths},
        "declared/observed ladder mismatch",
    )
    for depth in depths:
        pair = {
            p: sorted((r for r in rows if r["path"] == p and r["outstanding_per_stream"] == depth), key=lambda r: r["repeat"])
            for p in ("direct", "nbsr")
        }
        require(
            all(
                len(v) in (3, 5) and all(type(r["repeat"]) is int for r in v) and [r["repeat"] for r in v] == list(range(1, len(v) + 1))
                for v in pair.values()
            ),
            "exact three/five distinct contiguous repeat identities required",
        )
        target = max(repeat_target([r["aggregate_application_gbps"] for r in v[:3]]) for v in pair.values())
        require(all(len(v) == target for v in pair.values()), "sticky first-three matched repeat requirement failed")


def validate_execution(checked, raw, row, env):
    workload = env["workload"]
    recorded = json.loads(checked(raw / "commands.json").read_bytes())
    ready = json.loads(checked(raw / "ready.json").read_bytes())
    endpoint = ready["endpoint"]
    require(
        type(endpoint) is str and re.fullmatch(r"127\.0\.0\.1:[0-9]+", endpoint) and 1 <= int(endpoint.rsplit(":", 1)[1]) <= 65535,
        "invalid loopback readiness",
    )
    prefix = [env["linux_environment"]["taskset"], "--cpu-list", str(env["linux_environment"]["selected_cpus"][0])]
    for role in ("server", "client"):
        require(type(recorded[role]) is list and all(type(v) is str for v in recorded[role]), "invalid command vector")
    original_raw = Path(recorded["server"][recorded["server"].index("--ready") + 1]).parent
    require(original_raw.parts[-len(raw.parts) :] == raw.parts, "command/raw directory mismatch")
    authority = Path(recorded["server"][recorded["server"].index("--authority-dir") + 1])
    binaries = Path(env["executable_paths"]["direct"]).parent
    require(env["executable_paths"] == {r: str(binaries / n) for r, n in NAMES.items()}, "binary execution paths mismatch")
    cell = dict(
        path=row["path"],
        cores=1,
        payload_bytes=row["payload_bytes"],
        streams=row["streams_per_group"],
        outstanding=row["outstanding_per_stream"],
    )
    server, client, overrides = commands(
        cell, binaries, authority, original_raw, endpoint, workload["warmup_seconds"], workload["duration_seconds"]
    )
    require(
        recorded
        == dict(
            server=prefix + server,
            client=prefix + client,
            environment_overrides=overrides,
            selected_cpus=env["linux_environment"]["selected_cpus"],
        ),
        "declared/executed command mismatch",
    )
    require(
        checked(raw / "completion.ack").read_bytes() == b"source sample flushed, joined, final and requested cleanup validated\n",
        "missing/invalid source completion ACK",
    )
    cap = 2 * (math.ceil((workload["warmup_seconds"] + workload["duration_seconds"] + 60) / 0.1) + 4)
    previous, final = {}, {}
    count = 0
    last_timestamp = -1
    with checked(raw / "resources.ndjson").open("rb") as stream:
        while line := stream.readline(65537):
            count += 1
            require(count <= cap and len(line) <= 65536 and line.endswith(b"\n"), "resource evidence bound/truncation")
            sample = json.loads(line)
            role = sample.pop("role")
            require(role in ("server", "client") and role not in final, "unknown/terminated resource role")
            require(type(sample.get("pid")) is int and sample["pid"] == row["process_ids"][role], "resource PID mismatch")
            require(
                type(sample.get("affinity")) is list
                and all(type(c) is int for c in sample["affinity"])
                and sample["affinity"] == env["linux_environment"]["selected_cpus"],
                "resource affinity mismatch",
            )
            require(
                all(type(sample.get(k)) is int and sample[k] >= 0 for k in ("start_ticks", "timestamp_ns", "cpu_ns")),
                "invalid resource scalar",
            )
            require(sample["timestamp_ns"] > last_timestamp, "resource timestamp discontinuity")
            last_timestamp = sample["timestamp_ns"]
            old = previous.get(role)
            require(
                old is None or (old["start_ticks"] == sample["start_ticks"] and old["cpu_ns"] <= sample["cpu_ns"]),
                "resource identity/CPU discontinuity",
            )
            require(sample.get("state") in ("R", "S", "D", "T", "t", "Z", "I", "P"), "invalid resource process state")
            previous[role] = sample
            if sample["state"] == "Z":
                final[role] = sample
    require(set(final) == {"server", "client"} and row["final_process_samples"] == final, "terminal resource evidence mismatch")
    require(
        type(row["resource_records"]) is int
        and row["resource_records"] == count
        and type(row["lifetime_cpu_ns"]) is int
        and row["lifetime_cpu_ns"] == sum(s["cpu_ns"] for s in final.values()),
        "resource aggregate mismatch",
    )


def identity(linux, *, selected_count=1):
    require(isinstance(linux, dict), "Linux environment required")
    require(type(selected_count) is int and selected_count in (1, 2), "unsupported selected CPU count")
    keys = ("kernel", "python", "taskset_version", "lscpu_version", "topology", "inherited_cpus", "selected_cpus")
    require(all(key in linux for key in keys), "incomplete Linux identity")
    selected, inherited = linux["selected_cpus"], linux["inherited_cpus"]
    require(
        type(selected) is list and len(selected) == selected_count
        and all(type(cpu) is int and cpu >= 0 for cpu in selected), "exact selected CPU count required"
    )
    require(type(inherited) is list and inherited and all(type(v) is int and v >= 0 for v in inherited), "invalid inherited pool")
    require(physical_cpu_sets(linux["topology"], set(inherited), [selected_count])[selected_count] == selected, "physical core selection mismatch")
    limits = {}
    for name in ("cpu.max", "cpuset.cpus.effective", "memory.max", "pids.max"):
        value = linux.get("cgroup_observed", {}).get("/sys/fs/cgroup/" + name)
        require(type(value) is str and value.strip(), "readable cgroup-v2 limits required")
        limits[name] = value.strip()
    quota = limits["cpu.max"].split()
    require(len(quota) == 2 and quota[1].isdigit() and int(quota[1]) > 0, "invalid CPU quota")
    require(quota[0] == "max" or quota[0].isdigit() and int(quota[0]) >= selected_count * int(quota[1]), "quota below selected CPU allocation")
    return {**{key: linux[key] for key in keys}, "cgroup_limits": limits}


def load_reference(root, *, current_sha, binary_sha256, shape, linux_environment, percent, depth):
    try:
        require(type(percent) is int and 70 <= percent <= 80, "load must be70-80percent")
        require(type(depth) is int and depth in (1, 2, 4, 8, 16), "invalid depth")
        require(type(current_sha) is str and re.fullmatch(r"[0-9a-f]{40}", current_sha), "invalid current SHA")
        require(
            set(shape) == {"physical_cores", "endpoint_groups", "runtime_workers", "payload_bytes", "streams_per_group"}
            and all(type(v) is int for v in shape.values())
            and shape["physical_cores"] == shape["endpoint_groups"] == shape["runtime_workers"] == 1,
            "single core/group/worker only",
        )
        current_identity = identity(linux_environment)
        root = Path(root).resolve()
        manifest = (root / "checksums.sha256").read_bytes()
        verified = {}
        for line in manifest.decode().splitlines():
            expected_digest, relative = line.split("  ", 1)
            path = (root / relative).resolve()
            require(
                path.is_relative_to(root) and path not in verified and re.fullmatch(r"[0-9a-f]{64}", expected_digest),
                "invalid checksum path/digest",
            )
            with path.open("rb") as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == expected_digest, "checksum mismatch")
            verified[path] = expected_digest

        def checked(name):
            path = (root / name).resolve()
            require(path.is_relative_to(root) and path in verified, "required input missing from checksums")
            return path

        env = json.loads(checked("environment.json").read_bytes())
        build = json.loads(checked("build-manifest.json").read_bytes())
        rows = json.loads(checked("records.json").read_bytes())
        require(
            env.get("schema") == "nbsr-linux-b5-reference-v1" and env.get("classification") == "REFERENCE_CANDIDATE",
            "diagnostic/unknown reference cannot qualify",
        )
        require(env["repository_sha"] == current_sha and env["git_status"] == "", "stale/dirty controller source")
        require(env["shape"] == shape and env["observer"] == OBSERVER, "shape/observer mismatch")
        require(set(env.get("source_sha256", {})) == set(SOURCE_PATHS), "missing source provenance")
        for relative in SOURCE_PATHS:
            require(
                verified[checked("source/" + relative)] == env["source_sha256"][relative] == digest(ROOT / relative),
                "controller source mismatch",
            )
        require(identity(env["linux_environment"]) == current_identity, "Linux placement/kernel/cgroup mismatch")
        require(
            build["source_sha"] == current_sha and build["build_profile"] == "release" and build["build_commands"] and build["toolchains"],
            "stale/incomplete release build",
        )
        require(set(binary_sha256) == set(NAMES) and env["binary_sha256"] == binary_sha256, "binary identity mismatch")
        for role, name in NAMES.items():
            require(
                verified[checked("binaries/" + name)] == binary_sha256[role] == build["binary_sha256"][name], "actual binary bytes mismatch"
            )
        require(type(rows) is list and rows and {r["path"] for r in rows} == {"direct", "nbsr"}, "both paths required")
        parsed = []
        raw_directories = set()
        for row in rows:
            require(row["valid"] is True and row["observer"] == OBSERVER, "invalid attempt or observer mismatch")
            require(
                all(
                    row.get(key) == shape[key] and type(row.get(key)) is int
                    for key in ("payload_bytes", "streams_per_group", "endpoint_groups", "runtime_workers")
                ),
                "row shape mismatch",
            )
            raw = Path(row["raw_directory"])
            require(not raw.is_absolute() and ".." not in raw.parts and raw not in raw_directories, "duplicate/invalid raw directory")
            raw_directories.add(raw)
            record = read_binary_record(checked(raw / "client.stdout"))
            derived = finish_record(
                dict(
                    path=row["path"],
                    cores=1,
                    payload_bytes=shape["payload_bytes"],
                    streams=shape["streams_per_group"],
                    outstanding=row["outstanding_per_stream"],
                ),
                row["repeat"],
                record,
                cleanup_pass=row["cleanup_pass"],
            )
            require(all(row.get(key) == value for key, value in derived.items()), "summary/raw mismatch")
            exits, pids = row["process_exit_codes"], row["process_ids"]
            require(
                set(exits) == set(pids) == {"server", "client"}
                and all(type(v) is int and v == 0 for v in exits.values())
                and all(type(v) is int and v > 0 for v in pids.values())
                and len(set(pids.values())) == 2,
                "both owned exits required",
            )
            validate_execution(checked, raw, row, env)
            if row["path"] == "nbsr":
                require(len(row["cleanup_reports"]) == 2, "both cleanup reports required")
                for role, stem in (("source", "client"), ("destination", "server")):
                    report = json.loads(checked(raw / f"{stem}.cleanup.json").read_bytes())
                    require(validate_report(report, role, pids[stem]), "NBSR11field cleanup failed")
            parsed.append(derived)
        validate_ladder(env["workload"], parsed)
        ladders = {path: classify_ladder([r for r in parsed if r["path"] == path]) for path in ("direct", "nbsr")}
        require(
            {r["outstanding_per_stream"] for r in parsed if r["path"] == "direct"}
            == {r["outstanding_per_stream"] for r in parsed if r["path"] == "nbsr"},
            "path depth mismatch",
        )
        selected = [c for c in ladders["nbsr"]["cells"] if c["outstanding_per_stream"] == depth]
        require(len(selected) == 1 and selected[0]["classification"] == "STABLE", "selected finite cell is not strict stable")
        rates = [
            Fraction(r["completed_operations"] * 1_000_000_000, r["measured_ns"])
            for r in parsed
            if r["path"] == "nbsr" and r["outstanding_per_stream"] == depth
        ]
        reference = statistics.median(rates)
        offered = reference * Fraction(percent, 100)
        require(0 < offered.numerator < 2**64 and 0 < offered.denominator < 2**64, "rate overflow")
        return dict(
            schema="nbsr-linux-b5-ceiling-v1",
            reference_sha=current_sha,
            manifest_sha256=hashlib.sha256(manifest).hexdigest(),
            reference_repeats=selected[0]["repeat_count"],
            rate_numerator=offered.numerator,
            rate_denominator=offered.denominator,
            reference_operations_per_second=float(reference),
            load_percent=percent,
            depth=depth,
            shape=dict(shape),
            binary_sha256=dict(binary_sha256),
            reference_linux_identity=current_identity,
            observer=dict(OBSERVER),
            scope="matched-state finite reference only; paced feasibility, observer cost and sustained stability NOT_QUALIFIED",
        )
    except (OSError, KeyError, TypeError, OverflowError, UnicodeError) as error:
        raise ValueError("invalid Linux finite reference") from error


def current_environment():
    return environment(1)
