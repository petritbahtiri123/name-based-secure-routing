"""Finite Linux 1-core/1-group reference. Never a server or sustained maximum."""

import math
import json
import os
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from scripts.performance.linux_loopback import ROOT, build_commands, sample_process, write_json, repeat_target
from scripts.performance.p2a_established import validate_repeat
from scripts.performance.post_close_cleanup import validate_report
from scripts.performance.b4_linux import failure_details
from scripts.performance.process_cancellation import Cancellation, not_cancelled

ZERO_FIELDS = (
    "errors",
    "missing",
    "duplicates",
    "corrupt",
    "wrong_request",
    "transport_sessions_created_delta",
    "service_channels_created_delta",
    "application_streams_created_delta",
    "replay_entries_delta",
)
OBSERVER = dict(
    resource_mode="proc-stat-fd-thread-affinity",
    cadence_ns=100_000_000,
    nbsr_post_close_reports=True,
    qualification="NOT_QUALIFIED_NO_MATCHED_COMPARISON",
)
SOURCE_PATHS = tuple(
    "scripts/performance/" + name
    for name in (
        "linux_b5_reference.py",
        "process_cancellation.py",
        "linux_b5_ceiling.py",
        "linux_loopback.py",
        "b3_linux.py",
        "b4_linux.py",
        "linux_resources.py",
        "p2a_established.py",
        "physical_core_analysis.py",
        "post_close_cleanup.py",
        "authority.py",
    )
)


def sample_finite_process(pid, cpus):
    return sample_process(pid, cpus, allow_exiting=True)


def validate_cell(cell):
    if (
        set(cell) != {"path", "payload_bytes", "streams", "outstanding", "cores"}
        or cell["path"] not in ("direct", "nbsr")
        or type(cell["cores"]) is not int
        or cell["cores"] != 1
        or type(cell["payload_bytes"]) is not int
        or cell["payload_bytes"] not in (1024, 16384)
        or type(cell["streams"]) is not int
        or not 1 <= cell["streams"] <= 64
        or type(cell["outstanding"]) is not int
        or cell["outstanding"] not in (1, 2, 4, 8, 16)
    ):
        raise ValueError("only explicit single-core/single-group reference shapes supported")


def commands(cell, binaries, authority, raw, endpoint, warmup, duration):
    validate_cell(cell)
    if not all(type(v) in (int, float) and math.isfinite(v) and low <= v <= 3600 for v, low in ((warmup, 3), (duration, 20))):
        raise ValueError("invalid finite duration")
    server, client, env = build_commands(cell, Path(binaries), authority, raw, endpoint, warmup, duration)
    if cell["path"] == "nbsr":
        server += ["--p2a-cleanup-report", str(raw / "server.cleanup.json")]
        client += ["--p2a-cleanup-report", str(raw / "client.cleanup.json")]
    return server, client, env


def finish_record(cell, repeat, record, *, cleanup_pass):
    validate_cell(cell)
    if type(repeat) is not int or repeat < 1 or cleanup_pass is not True:
        raise ValueError("invalid repeat or cleanup")
    expected = dict(
        streams=cell["streams"],
        payload_bytes=cell["payload_bytes"],
        outstanding_per_stream=cell["outstanding"],
        configured_total_outstanding=cell["streams"] * cell["outstanding"],
    )
    if (
        record.get("schema") != "nbsr-p2a-repeat-v2"
        or record.get("path") != cell["path"]
        or any(type(record.get(k)) is not int or record[k] != v for k, v in expected.items())
        or any(type(record.get(k)) is not int or record[k] != 0 for k in ZERO_FIELDS)
        or not validate_repeat(record)
    ):
        raise ValueError("invalid binary workload/error record")
    for key in ("completed_operations", "measured_ns", "p50_latency_ns", "p95_latency_ns", "p99_latency_ns"):
        if type(record.get(key)) is not int or record[key] <= 0:
            raise ValueError("invalid exact operation/time/latency field")
    observed = record.get("max_outstanding_per_stream_observed")
    if type(observed) is not int or not 1 <= observed <= cell["outstanding"]:
        raise ValueError("observed outstanding bound failed")
    if not record["p50_latency_ns"] <= record["p95_latency_ns"] <= record["p99_latency_ns"]:
        raise ValueError("invalid latency order")
    ops = record["completed_operations"] * 1e9 / record["measured_ns"]
    return dict(
        path=cell["path"],
        repeat=repeat,
        valid=True,
        payload_bytes=cell["payload_bytes"],
        streams_per_group=cell["streams"],
        endpoint_groups=1,
        runtime_workers=1,
        outstanding_per_stream=cell["outstanding"],
        configured_total_outstanding=expected["configured_total_outstanding"],
        max_observed_total_outstanding=observed * cell["streams"],
        outstanding_observation_scope="conservative per-stream maximum times streams; not simultaneous global high-water",
        completed_operations=record["completed_operations"],
        measured_ns=record["measured_ns"],
        operations_per_second=ops,
        aggregate_application_gbps=ops * 16 * cell["payload_bytes"] / 1e9,
        p99_latency_ns=record["p99_latency_ns"],
        errors=0,
        timeouts=0,
        cleanup_pass=True,
        binary_record=record,
    )


def wait_exec(process, binary):
    deadline = time.monotonic() + 5
    while (Path("/proc") / str(process.pid) / "exe").resolve() != Path(binary).resolve():
        if time.monotonic() >= deadline:
            raise RuntimeError("taskset executable transition deadline")
        time.sleep(0.001)


def read_binary_record(path):
    found = []
    with Path(path).open("rb") as stream:
        for index in range(1025):
            line = stream.readline(262145)
            if not line:
                break
            if index == 1024 or len(line) > 262144 or not line.endswith(b"\n"):
                raise ValueError("finite stdout bound/truncation")
            value = json.loads(line)
            if value.get("schema") == "nbsr-p2a-repeat-v2":
                found.append(value)
            elif value.get("event") != "diagnostic":
                raise ValueError("unexpected finite stdout record")
    if len(found) != 1:
        raise ValueError("exactly one finite final required")
    return found[0]


def run_cell(
    cell,
    repeat,
    binaries,
    authority,
    raw,
    cpus,
    taskset,
    *,
    warmup,
    duration,
    sample_fn=sample_finite_process,
    popen=subprocess.Popen,
    exec_check=wait_exec,
    check_cancelled=not_cancelled,
):
    validate_cell(cell)
    if len(cpus) != 1 or type(cpus[0]) is not int or cpus[0] < 0:
        raise ValueError("one selected CPU required")
    raw.mkdir(parents=True, exist_ok=False)
    processes, handles, final, previous = {}, [], {}, {}
    row = dict(path=cell["path"], repeat=repeat, valid=False, classification="FAIL")
    prefix = [str(taskset), "--cpu-list", str(cpus[0])]
    environment = {key: value for key, value in os.environ.items() if not key.startswith("NBSR_")}
    server, _, override = commands(cell, binaries, authority, raw, "", warmup, duration)
    recorded = dict(server=prefix + server, environment_overrides=override, selected_cpus=cpus)
    cap = 2 * (math.ceil((warmup + duration + 60) / 0.1) + 4)
    sampled = 0
    exiting_roles = set()

    def launch(role, argv, env):
        stdout, stderr = (raw / f"{role}.stdout").open("xb"), (raw / f"{role}.stderr").open("xb")
        handles.extend((stdout, stderr))
        processes[role] = popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
        check_cancelled()

    def observe(role, sink):
        nonlocal sampled
        check_cancelled()
        if sampled >= cap:
            raise RuntimeError("finite observer cap exceeded")
        process = processes[role]
        value = sample_fn(process.pid, cpus)
        check_cancelled()
        sink.write(json.dumps(dict(role=role, **value)) + "\n")
        sink.flush()
        sampled += 1
        if value.get("pid") != process.pid or value.get("affinity") != cpus:
            raise RuntimeError("process identity/affinity mismatch")
        for key in ("start_ticks", "cpu_ns", "timestamp_ns"):
            if type(value.get(key)) is not int or value[key] < 0:
                raise RuntimeError("invalid resource counter")
        old = previous.get(role)
        flags = value.get("flags", 0)
        is_exiting = type(flags) is int and flags >= 0 and bool(flags & 4)
        if value.get("fd_count_state") == "UNAVAILABLE_EXITING":
            if old is None or not is_exiting or value["state"] == "Z" or value.get("fd_count") is not None:
                raise RuntimeError("unverified exiting FD observation")
            exiting_roles.add(role)
        if role in exiting_roles and value["state"] != "Z" and not is_exiting:
            raise RuntimeError("exiting process returned to live state")
        if old and (
            old["start_ticks"] != value["start_ticks"] or old["cpu_ns"] > value["cpu_ns"] or old["timestamp_ns"] >= value["timestamp_ns"]
        ):
            raise RuntimeError("resource identity/time/CPU discontinuity")
        previous[role] = value
        if value["state"] == "Z":
            final[role] = value
            if process.wait(timeout=5) != 0:
                raise RuntimeError(f"{role} failed; see retained stderr")
            if role == "client":
                finish_record(cell, repeat, read_binary_record(raw / "client.stdout"), cleanup_pass=True)
                if cell["path"] == "nbsr":
                    report = json.loads((raw / "client.cleanup.json").read_text())
                    if not validate_report(report, "source", process.pid):
                        raise RuntimeError("source NBSR11field post-close validation failed before ACK")
                (raw / "completion.ack").write_text("source sample flushed, joined, final and requested cleanup validated\n")

    try:
        write_json(raw / "commands.json", recorded)
        launch("server", recorded["server"], dict(environment, **override))
        deadline = time.monotonic() + 30
        while not (raw / "ready.json").exists():
            check_cancelled()
            if processes["server"].poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("server readiness failed")
            time.sleep(0.02)
        endpoint = json.loads((raw / "ready.json").read_text())["endpoint"]
        if not endpoint.startswith("127.0.0.1:"):
            raise RuntimeError("loopback readiness required")
        exec_check(processes["server"], server[0])
        _, client, _ = commands(cell, binaries, authority, raw, endpoint, warmup, duration)
        recorded["client"] = prefix + client
        write_json(raw / "commands.json", recorded)
        with (raw / "resources.ndjson").open("x") as sink:
            observe("server", sink)
            launch("client", recorded["client"], environment)
            exec_check(processes["client"], client[0])
            deadline = time.monotonic() + warmup + duration + 60
            while len(final) < 2:
                for role in processes:
                    if role not in final:
                        observe(role, sink)
                if time.monotonic() >= deadline:
                    raise RuntimeError("finite workload/drain deadline")
                if len(final) < 2:
                    time.sleep(0.1)
        reports = []
        check_cancelled()
        if cell["path"] == "nbsr":
            for role, process_role in (("source", "client"), ("destination", "server")):
                report = json.loads((raw / f"{process_role}.cleanup.json").read_text())
                if not validate_report(report, role, processes[process_role].pid):
                    raise RuntimeError("NBSR11field post-close validation failed")
                reports.append(dict(role=role, pid=processes[process_role].pid, file=f"{process_role}.cleanup.json", all_11_zero=True))
        row = finish_record(cell, repeat, read_binary_record(raw / "client.stdout"), cleanup_pass=True)
        row.update(
            process_ids={r: p.pid for r, p in processes.items()},
            final_process_samples=final,
            process_exit_codes={r: p.returncode for r, p in processes.items()},
            cleanup_reports=reports,
            cleanup_scope="NBSR11fields+bothprocessjoins" if reports else "Direct bothprocessjoins; runtimeownership NOT_MEASURED",
            observer=dict(OBSERVER),
            resource_records=sampled,
            lifetime_cpu_ns=sum(s["cpu_ns"] for s in final.values()),
            cpu_scope="whole process lifetime including taskset/warmup/drain; no steady CPU estimate",
        )
    except Exception as error:
        row.update(valid=False, classification="FAIL", **failure_details(error))
    finally:
        cleanup_errors = []
        for process in processes.values():
            try:
                if process.returncode is None:
                    process.kill()
                process.wait(timeout=5)
            except Exception as error:
                cleanup_errors.append(str(error))
        for handle in handles:
            handle.close()
        if cleanup_errors:
            row.update(valid=False, cleanup_errors=cleanup_errors)
        write_json(raw / "record.json", row)
    return row


def run_ladder(payload, streams, depths, run, retain):
    if (
        type(depths) is not list
        or not depths
        or depths[0] != 1
        or any(type(d) is not int or d not in (1, 2, 4, 8, 16) for d in depths)
        or depths != sorted(set(depths))
    ):
        raise ValueError("ordered distinct depths with baseline one required")
    validate_cell(dict(path="direct", payload_bytes=payload, streams=streams, outstanding=1, cores=1))
    rows = []
    for depth in depths:
        values = {"direct": [], "nbsr": []}
        target, repeat = 3, 0
        while repeat < target:
            repeat += 1
            for path in ("direct", "nbsr") if repeat % 2 else ("nbsr", "direct"):
                cell = dict(path=path, payload_bytes=payload, streams=streams, outstanding=depth, cores=1)
                row = run(cell, repeat)
                retain(row)
                rows.append(row)
                if row.get("valid") is not True:
                    raise RuntimeError("invalid retained reference attempt")
                values[path].append(row["aggregate_application_gbps"])
            if repeat >= 3:
                target = max(target, *(repeat_target(v) for v in values.values()))
    return rows


def git_state():
    return (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True),
    )


def execute(args, *, linux_environment=None, git_state_fn=git_state, run_fn=run_cell, authority_fn=None, executable_fn=None,
            check_cancelled=not_cancelled):
    from scripts.performance.authority import write_loopback_authority
    from scripts.performance.b3_linux import environment
    from scripts.performance.linux_b5_ceiling import NAMES, identity, require
    from scripts.performance.linux_loopback import checksums, digest
    from scripts.performance.physical_core_analysis import classify_ladder

    authority_fn = authority_fn or write_loopback_authority
    executable_fn = executable_fn or (lambda p: os.access(p, os.X_OK))
    # Validate the complete input ladder without launching any workload.
    run_ladder(args.payload_bytes, args.streams, args.depths, lambda c, r: dict(valid=True, aggregate_application_gbps=1), lambda r: None)
    binaries, output = args.binaries.resolve(), args.output.resolve()
    require(not output.is_relative_to(ROOT), "evidence output must be outside source checkout")
    sha, dirty = git_state_fn()
    require(not dirty, "clean checkout required")
    build = json.loads(args.build_manifest.read_bytes())
    hashes = {role: digest(binaries / name) for role, name in NAMES.items()}
    require(
        build.get("source_sha") == sha
        and build.get("build_profile") == "release"
        and build.get("build_commands")
        and build.get("toolchains"),
        "current release build manifest required",
    )
    require(build.get("binary_sha256") == {NAMES[r]: h for r, h in hashes.items()}, "build binary hashes mismatch")
    require(all(executable_fn(binaries / name) for name in NAMES.values()), "executable binaries required")
    linux = linux_environment if linux_environment is not None else environment(1)
    initial_identity = identity(linux)
    sources = {relative: digest(ROOT / relative) for relative in SOURCE_PATHS}
    shape = dict(physical_cores=1, endpoint_groups=1, runtime_workers=1, payload_bytes=args.payload_bytes, streams_per_group=args.streams)
    commands(
        dict(path="direct", cores=1, streams=args.streams, payload_bytes=args.payload_bytes, outstanding=1),
        binaries,
        output / "authority",
        output / "raw",
        "",
        args.warmup,
        args.duration,
    )
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    env = dict(
        schema="nbsr-linux-b5-reference-v1",
        repository_sha=sha,
        git_status=dirty,
        classification="FAIL",
        shape=shape,
        binary_sha256=hashes,
        source_sha256=sources,
        linux_environment=linux,
        observer=dict(OBSERVER),
        workload=dict(depths=args.depths, warmup_seconds=args.warmup, duration_seconds=args.duration),
        executable_paths={r: str(binaries / n) for r, n in NAMES.items()},
        command=[os.sys.executable, *os.sys.argv],
        scope="single-host Linux loopback shared physical-core pool; dedicated/server hardware NOT_PROVEN",
    )

    def unchanged():
        check_cancelled()
        require(git_state_fn() == (sha, ""), "source checkout changed during campaign")
        require(all(digest(ROOT / p) == h for p, h in sources.items()), "source bytes changed")
        require(
            all(digest(binaries / NAMES[r]) == h and digest(output / "binaries" / NAMES[r]) == h for r, h in hashes.items()),
            "binary bytes changed",
        )
        current = linux_environment if linux_environment is not None else environment(1)
        require(identity(current) == initial_identity, "Linux placement/cgroup environment changed")

    def retain(row):
        rows.append(row)
        write_json(output / "records.json", rows)

    try:
        write_json(output / "environment.json", env)
        write_json(output / "build-manifest.json", build)
        (output / "binaries").mkdir()
        for name in NAMES.values():
            shutil.copyfile(binaries / name, output / "binaries" / name)
        for relative in SOURCE_PATHS:
            retained = output / "source" / relative
            retained.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, retained)
        with tempfile.TemporaryDirectory(prefix="nbsr-linux-b5-authority-") as temporary:
            authority = Path(temporary) / "authority"
            authority_fn(authority)

            def run(cell, repeat):
                unchanged()
                relative = f"raw/{cell['path']}-d{cell['outstanding']}-r{repeat}"
                row = run_fn(
                    cell,
                    repeat,
                    binaries,
                    authority,
                    output / relative,
                    linux["selected_cpus"],
                    linux["taskset"],
                    warmup=args.warmup,
                    duration=args.duration,
                    check_cancelled=check_cancelled,
                )
                row["raw_directory"] = relative
                return row

            run_ladder(args.payload_bytes, args.streams, args.depths, run, retain)
        unchanged()
        ladders = {path: classify_ladder([r for r in rows if r["path"] == path]) for path in ("direct", "nbsr")}
        write_json(
            output / "analysis.json", dict(ladders=ladders, observer=OBSERVER, sustained_capacity="NOT_RUN", external_hardware="NOT_PROVEN")
        )
        env["classification"] = "REFERENCE_CANDIDATE"
    except Exception as error:
        env["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        write_json(output / "records.json", rows)
        write_json(output / "environment.json", env)
        checksums(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--payload-bytes", type=int, choices=(1024, 16384), required=True)
    parser.add_argument("--streams", type=int, required=True)
    parser.add_argument("--depths", type=int, nargs="+", default=[1, 2, 4, 8, 16])
    parser.add_argument("--warmup", type=float, default=3)
    parser.add_argument("--duration", type=float, default=30)
    with Cancellation() as cancellation:
        execute(parser.parse_args(), check_cancelled=cancellation.check)


if __name__ == "__main__":
    main()
