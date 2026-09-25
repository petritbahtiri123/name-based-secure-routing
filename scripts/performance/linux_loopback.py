"""Linux-only P2A loopback control runner. No builds or remote execution.

CPU totals cover process lifetime including startup/warmup/drain, not the
binary's steady interval. No strict-stable ceiling or physical NIC claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import tempfile
import time

from scripts.performance.p2a_established import validate_repeat
from scripts.performance.process_cancellation import Cancellation, not_cancelled

ROOT = Path(__file__).resolve().parents[2]
BINARIES = ("perf_direct_peer", "perf_rust_source", "wp8_interop_server")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_matrix(matrix):
    if set(matrix) != {"schema", "cores", "workloads", "warmup_seconds", "duration_seconds"}:
        raise ValueError("unknown or missing matrix fields")
    if matrix["schema"] != "nbsr-linux-loopback-v1":
        raise ValueError("unsupported schema")
    cores = matrix["cores"]
    if not isinstance(cores, list) or not cores or len(set(cores)) != len(cores):
        raise ValueError("core counts must be unique and nonempty")
    if any(type(c) is not int or c not in (1, 2, 4, 8, 16, 32) for c in cores):
        raise ValueError("this runner supports only 1/2/4/8/16/32 physical cores")
    for key, minimum in (("warmup_seconds", 3), ("duration_seconds", 20)):
        value = matrix[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= 3600:
            raise ValueError(f"invalid {key}")
    if not isinstance(matrix["workloads"], list) or not matrix["workloads"]:
        raise ValueError("workloads must be nonempty")
    for w in matrix["workloads"]:
        if set(w) != {"payload_bytes", "streams", "outstanding"}:
            raise ValueError("unknown or missing workload fields")
        if any(type(v) is not int for v in w.values()):
            raise ValueError("workload values must be integers")
        if w["payload_bytes"] not in (1024, 16384) or not 1 <= w["streams"] <= 64 or w["outstanding"] not in (1, 2, 4, 8, 16):
            raise ValueError("workload exceeds this runner's existing single-group CLI bounds")
    if len({json.dumps(w, sort_keys=True) for w in matrix["workloads"]}) != len(matrix["workloads"]):
        raise ValueError("duplicate workloads")


def expand_matrix(matrix):
    validate_matrix(matrix)
    return [{**w, "cores": c, "path": p} for c in matrix["cores"]
            for w in matrix["workloads"] for p in ("direct", "nbsr")]


def physical_cpu_sets(topology, allowed, counts):
    nodes = {}
    for row in topology["cpus"]:
        if str(row.get("online", "")).lower() not in ("yes", "true", "1"):
            continue
        cpu = int(row["cpu"])
        if cpu not in allowed:
            continue
        if any(row.get(k) in (None, "", "-") for k in ("core", "socket", "node")):
            raise ValueError("physical/NUMA topology unavailable")
        node = int(row["node"])
        key = (int(row["socket"]), int(row["core"]))
        bucket = nodes.setdefault(node, {})
        bucket[key] = min(cpu, bucket.get(key, cpu))
    eligible = [node for node, cores in nodes.items() if len(cores) >= max(counts)]
    if not eligible:
        raise ValueError("insufficient available physical cores on a single NUMA node")
    selected = sorted(nodes[min(eligible)].values())
    return {count: selected[:count] for count in counts}


def parse_cpu_list(value):
    result = set()
    for part in value.strip().split(","):
        limits = part.split("-")
        first, last = int(limits[0]), int(limits[-1])
        if len(limits) > 2 or first < 0 or last < first:
            raise ValueError("invalid CPU list")
        result.update(range(first, last + 1))
    return result


def parse_proc_stat(text, ticks, page_size):
    fields = text[text.rindex(")") + 2:].split()
    return {"state": fields[0], "flags": int(fields[6]), "cpu_ns": (int(fields[11]) + int(fields[12])) * 1_000_000_000 // ticks,
            "start_ticks": int(fields[19]), "rss_bytes": int(fields[21]) * page_size}


def sample_process(pid, cpus, proc_root=Path("/proc"), ticks=None, page_size=None, *, allow_exiting=False):
    """Opted-in owners must retain exiting observations until a final zombie sample.

    PF_EXITING (0x4) can precede zombie state and FD permission loss. Such a
    snapshot has no measured FD count and is not final CPU or cleanup evidence.
    """
    base = proc_root / str(pid)
    ticks = ticks if ticks is not None else os.sysconf("SC_CLK_TCK")
    page_size = page_size if page_size is not None else os.sysconf("SC_PAGE_SIZE")

    def read_stat():
        text = (base / "stat").read_text()
        if int(text.split(" ", 1)[0]) != pid:
            raise RuntimeError("process identity changed")
        return parse_proc_stat(text, ticks, page_size)

    sample = read_stat()
    tids = []
    for task in (base / "task").iterdir():
        try:
            status = dict(line.split(":", 1) for line in (task / "status").read_text().splitlines() if ":" in line)
            if parse_cpu_list(status["Cpus_allowed_list"]) != set(cpus):
                raise RuntimeError(f"affinity mismatch: PID {pid}, TID {task.name}")
            if (task / "children").read_text().strip():
                raise RuntimeError("unexpected untracked child process")
            tids.append(int(task.name))
        except (FileNotFoundError, ProcessLookupError):
            # A nonleader may exit after enumeration: proc reads can return
            # ENOENT or ESRCH. Missing leaders and access errors remain fatal.
            if task.name == str(pid):
                raise
    if pid not in tids:
        raise RuntimeError("main-thread affinity unavailable")
    fd_count = None
    if sample["state"] != "Z":
        try:
            fd_count = len(list((base / "fd").iterdir()))
        except PermissionError as error:
            # Same-UID FD access can fail before zombie state. Only a verified
            # zombie or an opted-in PF_EXITING observation permits omission.
            final = read_stat()
            if final["start_ticks"] != sample["start_ticks"]:
                raise RuntimeError("process identity changed") from None
            if final["state"] != "Z" and not (allow_exiting is True and final["flags"] & 4):
                error.add_note(json.dumps({"phase": "fd_permission_recheck", "pid": pid,
                                           "initial_stat": sample, "recheck_stat": final}, sort_keys=True))
                raise
            sample = final
    sample.update(pid=pid, timestamp_ns=time.monotonic_ns(), thread_ids=tids,
                  fd_count=fd_count,
                  fd_count_state=("UNAVAILABLE_ZOMBIE" if sample["state"] == "Z" else
                                  "UNAVAILABLE_EXITING" if fd_count is None else "MEASURED"),
                  affinity=list(cpus))
    return sample


def repeat_target(values):
    if len(values) < 3:
        return 3
    cv = statistics.stdev(values) / statistics.fmean(values) if statistics.fmean(values) else math.inf
    return 5 if cv > 0.05 or len(values) > 3 else 3


def build_commands(cell, binaries, authority, raw, endpoint, warmup, duration):
    workers = str(cell["cores"])
    base = ["--authority-dir", str(authority)]
    if cell["path"] == "direct":
        server = [str(binaries / "perf_direct_peer"), "--role", "server", "--ready", str(raw / "ready.json"),
                  *base, "--connections", "1", "--requests-per-connection", "1",
                  "--p2a-streams", str(cell["streams"]), "--completion-ack", str(raw / "completion.ack"),
                  "--p2a-runtime-workers", workers]
        client = [str(binaries / "perf_direct_peer"), "--role", "client", "--samples", "1", "--lifecycle", "warm"]
        env = {}
    else:
        server = [str(binaries / "wp8_interop_server"), "--ready", str(raw / "ready.json"),
                  "--result", str(raw / "server-result.json"), *base,
                  "--completion-ack", str(raw / "completion.ack"), "--p2a-runtime-workers", workers]
        client = [str(binaries / "perf_rust_source"), "--samples", "1"]
        env = {"NBSR_P2A_STREAMS": str(cell["streams"])}
    client += [*base, "--endpoint", endpoint, "--payload-bytes", str(cell["payload_bytes"]),
               "--p2a-streams", str(cell["streams"]), "--p2a-runtime-workers", workers,
               "--p2a-outstanding-per-stream", str(cell["outstanding"]),
               "--p2a-warmup-seconds", str(warmup), "--p2a-duration-seconds", str(duration)]
    return server, client, env


def run_cell(cell, repeat, binaries, authority, raw, cpus, matrix, taskset, *, check_cancelled=not_cancelled):
    raw.mkdir()
    processes, handles, final, starts = {}, [], {}, {}
    prefix = [taskset, "--cpu-list", ",".join(map(str, cpus))]
    # Prevent inherited experimental benchmark modes from changing semantics.
    env = {k: v for k, v in os.environ.items() if not k.startswith("NBSR_")}
    server, _, override = build_commands(cell, binaries, authority, raw, "", matrix["warmup_seconds"], matrix["duration_seconds"])
    commands = {"server": prefix + server, "environment_overrides": override, "affinity": cpus}
    write_json(raw / "commands.json", commands)

    def launch(role, argv, environment):
        out = (raw / f"{role}.stdout").open("w")
        err = (raw / f"{role}.stderr").open("w")
        handles.extend((out, err))
        processes[role] = subprocess.Popen(argv, cwd=ROOT, env=environment, stdout=out, stderr=err)
        check_cancelled()

    def observe(role, sink):
        proc = processes[role]
        sample = sample_process(proc.pid, cpus)
        if role in starts and starts[role] != sample["start_ticks"]:
            raise RuntimeError("process identity changed")
        starts[role] = sample["start_ticks"]
        sink.write(json.dumps({"role": role, **sample}) + "\n")
        sink.flush()
        if sample["state"] == "Z":
            final[role] = sample
            if proc.wait(timeout=5) != 0:
                raise RuntimeError(f"{role} exited unsuccessfully; see raw stderr")
            if role == "client":
                # Release the existing server completion barrier only after
                # the final source sample is flushed and source exit succeeds.
                (raw / "completion.ack").touch(exist_ok=False)
        return sample

    try:
        check_cancelled()
        launch("server", commands["server"], {**env, **override})
        deadline = time.monotonic() + 30
        # taskset exec happens before peer readiness; no measurement begins here.
        while not (raw / "ready.json").exists():
            check_cancelled()
            if time.monotonic() > deadline:
                raise RuntimeError("server readiness timeout")
            state = parse_proc_stat((Path("/proc") / str(processes["server"].pid) / "stat").read_text(), 1, 1)["state"]
            if state == "Z":
                raise RuntimeError("server exited before readiness")
            time.sleep(0.02)
        endpoint = json.loads((raw / "ready.json").read_text())["endpoint"]
        if not endpoint.startswith("127.0.0.1:"):
            raise RuntimeError("unexpected non-loopback endpoint")
        _, client, _ = build_commands(cell, binaries, authority, raw, endpoint, matrix["warmup_seconds"], matrix["duration_seconds"])
        commands["client"] = prefix + client
        write_json(raw / "commands.json", commands)
        with (raw / "resources.ndjson").open("w") as sink:
            observe("server", sink)
            launch("client", commands["client"], env)
            # Allow taskset to exec the target; verify target executable before sampling.
            deadline = time.monotonic() + 5
            expected = Path(client[0]).resolve()
            while (Path("/proc") / str(processes["client"].pid) / "exe").resolve() != expected:
                check_cancelled()
                if time.monotonic() > deadline:
                    raise RuntimeError("client taskset/exec verification timeout")
                time.sleep(0.001)
            deadline = time.monotonic() + matrix["warmup_seconds"] + matrix["duration_seconds"] + 60
            while len(final) < 2:
                check_cancelled()
                for role in processes:
                    if role not in final:
                        observe(role, sink)
                if time.monotonic() > deadline:
                    raise RuntimeError("measurement or peer-drain timeout")
                if len(final) < 2:
                    time.sleep(0.1)
        for handle in handles:
            handle.flush()
        check_cancelled()
        record = json.loads((raw / "client.stdout").read_text().strip().splitlines()[-1])
        if not validate_repeat(record) or int(record.get("measured_ns", 0)) <= 0:
            raise RuntimeError("binary repeat validity contract failed")
        completed = int(record["completed_operations"])
        seconds = int(record["measured_ns"]) / 1e9
        cpu = sum(s["cpu_ns"] for s in final.values())
        return {"cell": cell, "repeat": repeat, "valid": True, "binary_record": record,
                "aggregate_application_gbps": 16 * completed * cell["payload_bytes"] / seconds / 1e9,
                "operations_per_second": completed / seconds, "cleanup": "PASS_PROCESS_EXIT",
                "cpu_accounting_scope": "whole process lifetime, includes taskset/startup/warmup/drain",
                "lifetime_cpu_ns": cpu, "lifetime_cpu_ns_per_completed_operation": cpu / completed,
                "steady_cpu_ns_per_operation": None, "steady_effective_cores": None,
                "affinity_verified": True, "final_process_samples": final,
                "strict_stable": "NOT_ESTABLISHED_NO_OFFERED_RATE_OR_BACKLOG_GATE"}
    finally:
        forced = []
        for role, process in processes.items():
            if process.returncode is None:
                process.kill()
                forced.append(dict(role=role, pid=process.pid, exit_code=process.wait(timeout=5)))
        for handle in handles:
            handle.close()
        if forced:
            write_json(raw / "forced-cleanup.json", dict(valid=False, processes=forced))


def checksums(output):
    entries = [f"{digest(p)}  {p.relative_to(output).as_posix()}" for p in sorted(output.rglob("*"))
               if p.is_file() and p.name != "checksums.sha256"]
    (output / "checksums.sha256").write_text("\n".join(entries) + "\n", encoding="utf-8")


def execute(*, check_cancelled):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=Path(__file__).with_name("linux_loopback_matrix.json"))
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path, required=True,
                        help="JSON with source_sha, binary_sha256, build_commands, toolchains, build_profile")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("Linux required; no Windows fallback")
    matrix = json.loads(args.matrix.read_text())
    validate_matrix(matrix)
    binaries = args.binaries.resolve()
    taskset = shutil.which("taskset")
    if not taskset or not shutil.which("lscpu"):
        parser.error("taskset and lscpu required")
    topology = json.loads(subprocess.check_output(["lscpu", "-J", "-e=CPU,CORE,SOCKET,NODE,ONLINE"], text=True))
    cpu_sets = physical_cpu_sets(topology, os.sched_getaffinity(0), matrix["cores"])
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True)
    if dirty:
        parser.error("clean source checkout required; retain changes and use an accepted clean checkout")
    build = json.loads(args.build_manifest.read_text())
    hashes = {name: digest(binaries / name) for name in BINARIES}
    if build.get("source_sha") != sha or build.get("binary_sha256") != hashes or build.get("build_profile") != "release":
        parser.error("build manifest SHA, binary hashes or release profile mismatch")
    if not build.get("build_commands") or not build.get("toolchains"):
        parser.error("build commands and toolchains required")
    for name in BINARIES:
        if not os.access(binaries / name, os.X_OK):
            parser.error(f"binary not executable: {name}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    write_json(output / "environment.json", {"source_sha": sha, "platform": platform.platform(),
               "topology": topology, "cpu_sets": cpu_sets, "python": platform.python_version(),
               "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "scope": "Linux loopback, shared source/destination physical-core pool"})
    source_paths = [Path(__file__), Path(__file__).with_name("authority.py"),
                    Path(__file__).with_name("p2a_established.py"),
                    Path(__file__).with_name("process_cancellation.py")]
    source_hashes = {str(p.relative_to(ROOT)): digest(p) for p in source_paths}
    write_json(output / "manifest.json", {"matrix": matrix, "build": build, "binary_sha256": hashes,
               "source_sha256": source_hashes,
               "runner_sha256": digest(Path(__file__)), "matrix_sha256": digest(args.matrix),
               "authority_helper_sha256": digest(Path(__file__).with_name("authority.py")),
               "validation_helper_sha256": digest(Path(__file__).with_name("p2a_established.py")),
               "command": [os.sys.executable, *os.sys.argv], "status": "RUNNING"})
    records, summaries = [], []
    status = "FAIL"
    try:
        from scripts.performance.authority import write_loopback_authority
        with tempfile.TemporaryDirectory(prefix="nbsr-linux-authority-") as temporary:
            authority = Path(temporary) / "authority"
            write_loopback_authority(authority)
            cells = expand_matrix(matrix)
            for index in range(0, len(cells), 2):
                pair = cells[index:index + 2]
                by_path = {"direct": [], "nbsr": []}
                target, repeat = 3, 0
                while repeat < target:
                    repeat += 1
                    for cell in pair if repeat % 2 else pair[::-1]:
                        raw = output / "raw" / f"pair-{index // 2:03d}-{cell['path']}-r{repeat}"
                        try:
                            record = run_cell(cell, repeat, binaries, authority, raw, cpu_sets[cell["cores"]], matrix, taskset,
                                              check_cancelled=check_cancelled)
                        except Exception as error:
                            write_json(raw / "rejected.json", {"cell": cell, "repeat": repeat, "valid": False, "reason": str(error)})
                            raise
                        write_json(raw / "record.json", record)
                        records.append(record)
                        by_path[cell["path"]].append(record["aggregate_application_gbps"])
                    if repeat >= 3:
                        target = max(target, *(repeat_target(values) for values in by_path.values()))
                for path, values in by_path.items():
                    cv = statistics.stdev(values) / statistics.fmean(values)
                    summaries.append({"cell": next(c for c in pair if c["path"] == path),
                                      "valid_repeats": len(values), "median_gbps": statistics.median(values),
                                      "cv": cv, "repeatable": cv <= 0.05})
        if hashes != {name: digest(binaries / name) for name in BINARIES}:
            raise RuntimeError("binaries changed during campaign")
        if source_hashes != {str(p.relative_to(ROOT)): digest(p) for p in source_paths}:
            raise RuntimeError("runner or helper source changed during campaign")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != sha:
            raise RuntimeError("source commit changed during campaign")
        check_cancelled()
        status = "PASS_LOOPBACK_CONTROL" if all(s["repeatable"] for s in summaries) else "PARTIAL_DISPERSION"
    finally:
        write_json(output / "analysis.json", {"status": status, "cells": summaries, "valid_runs": len(records),
                   "external_two_host": "NOT_RUN / EXTERNAL_HARDWARE_REQUIRED",
                   "strict_stable_ceiling": "NOT_ESTABLISHED", "steady_cpu_ns_per_operation": None})
        (output / "summary.md").write_text(f"# Linux loopback control\n\nStatus: {status}\n\nNo two-host, physical-NIC, strict-stable ceiling or steady CPU ns/op claim.\n", encoding="utf-8")
        manifest = json.loads((output / "manifest.json").read_text())
        manifest["status"] = status
        write_json(output / "manifest.json", manifest)
        checksums(output)


def main():
    with Cancellation() as cancellation:
        execute(check_cancelled=cancellation.check)


if __name__ == "__main__":
    main()
