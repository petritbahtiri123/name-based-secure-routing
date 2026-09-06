"""Bounded Windows grouped paced B5 controller; no hardware-general claims."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_max_throughput_v2_stage4 as stage4
from scripts import run_p2a_established as p2a
from scripts.run_physical_core_v2 import placement
from scripts.performance.authority import write_loopback_authority
from scripts.performance.b5_ceiling import load_ceiling, placement_identity, topology_identity
from scripts.performance.b5_stream import B5Stream
from scripts.performance.post_close_cleanup import validate_report
from scripts.performance.resources import ProcessResourceSampler
from scripts.performance.sustained_capacity import live_drift_failure, private_growth
from scripts.profile_b2_v2 import set_and_verify_exact_affinity, windows_processor_topology
from scripts.run_performance_validation import wait_ready

ROOT = Path(__file__).resolve().parents[1]
CADENCE = 0.5
ALLOWANCE = 92


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class BoundedReader:
    """Reader queue is bounded; controller must drain it before joining."""
    def __init__(self, source):
        self.source = source
        self.queue = queue.Queue(maxsize=16)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._read, name="b5-stdout", daemon=True)

    def start(self):
        self.thread.start()

    def _put(self, value):
        while not self.stop.is_set():
            try:
                self.queue.put(value, timeout=0.1)
                return
            except queue.Full:
                pass

    def _read(self):
        try:
            read = getattr(self.source, "read1", self.source.read)
            while not self.stop.is_set():
                value = read(65_536)
                self._put(value if value else None)
                if not value:
                    return
        except Exception as error:
            self._put(error)

    def join(self):
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            self.stop.set()
            raise RuntimeError("stdout reader did not join; evidence incomplete")


def consume(source, reader, stream):
    eof = False
    while True:
        active = source.poll() is None
        stream.check(source_active=active)
        if eof:
            if not active:
                return stream.finish(source.returncode)
            time.sleep(0.1)
            continue
        try:
            value = reader.queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if isinstance(value, Exception):
            raise value
        if value is None:
            eof = True
        else:
            stream.feed(value, source_active=source.poll() is None)


def preserve_tail(reader, raw):
    """After kill, drain observed bytes without calling the failed parser."""
    until = time.monotonic() + 5
    while reader.thread.is_alive() or not reader.queue.empty():
        if time.monotonic() >= until:
            reader.stop.set()
            raise RuntimeError("stdout tail drain failed; evidence incomplete")
        try:
            value = reader.queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if isinstance(value, bytes):
            raw.write(value)
            raw.flush()
        elif isinstance(value, Exception):
            raise RuntimeError("stdout reader failed; partial evidence retained") from value
    reader.join()


class LiveGuards:
    def __init__(self, *, groups, max_progress, max_resources):
        self.roles = {"source", *(f"destination_{i}" for i in range(groups))}
        self.max_progress, self.max_resources = max_progress, max_resources
        self.steady = []
        self.resources = []
        self.count = 0
        self.origin_ns = None
        self.lock = threading.Lock()

    def resource(self, value):
        with self.lock:
            if len(self.resources) >= self.max_resources:
                raise RuntimeError("live resource bound exceeded")
            if value["role"] not in self.roles or type(value.get("monotonic_timestamp_ns")) is not int:
                raise RuntimeError("invalid resource role/clock")
            self.resources.append(value)

    def progress(self, value, *, received_ns=None):
        received_ns = time.monotonic_ns() if received_ns is None else received_ns
        self.count += 1
        if self.count > self.max_progress:
            raise RuntimeError("live progress bound exceeded")
        if self.origin_ns is None:
            self.origin_ns = received_ns - value["elapsed_ns"]
        if value["phase"] != "steady":
            return
        self.steady.append(value)
        reason = live_drift_failure(self.steady)
        if reason:
            raise RuntimeError(f"live {reason} drift")
        with self.lock:
            for role in sorted(self.roles):
                points = [((r["monotonic_timestamp_ns"] - self.origin_ns) / 1e9, float(r["private_bytes"]))
                          for r in self.resources if r["role"] == role
                          and self.origin_ns <= r["monotonic_timestamp_ns"] <= received_ns]
                if private_growth(points):
                    raise RuntimeError(f"live private growth: {role} (receive-clock diagnostic)")

    def qualification(self):
        with self.lock:
            complete = self.origin_ns is not None and all(sum(
                r["role"] == role and r["monotonic_timestamp_ns"] >= self.origin_ns
                for r in self.resources) >= 4 for role in self.roles)
        return {"steady_windows": len(self.steady), "latency_comparison_available":
                len(self.steady) >= 3 and all(r["p99_latency_ns"] is not None for r in self.steady),
                "resource_series_available": complete,
                "resource_phase_clock": "first-progress receive time minus elapsed; approximate, excludes earlier samples",
                "thermal_and_power": "NOT_MEASURED"}


def required_repeats(rows):
    if any(row.get("valid") is not True for row in rows):
        raise ValueError("invalid repeat cannot count toward acceptance")
    values = [row["gbps"] for row in rows]
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("invalid repeat goodput")
    return 5 if len(values) >= 3 and statistics.stdev(values) / statistics.mean(values) > 0.05 else 3


def validate_mode(*, diagnostic, reference, rate):
    if diagnostic:
        if reference is not None or rate is None or any(type(v) is not int or not 0 < v < 2**64 for v in rate):
            raise ValueError("diagnostic requires explicit rational rate and no ceiling")
        return "DIAGNOSTIC"
    if reference is None or rate is not None:
        raise ValueError("soak requires ceiling and forbids manual rate")
    return "CEILING_BOUND_SOAK"


def require_reference_placement(load, plan, topology):
    if load["reference_placement"] != placement_identity(plan) or load["reference_topology_identity"] != topology_identity(topology):
        raise ValueError("reference placement/topology identity mismatch")


def assert_clean_source(expected_sha):
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if current != expected_sha or status:
        raise RuntimeError("source changed during preparation or measurement")


def source_command(cell, binaries, authority, endpoints, *, warmup, duration, progress, rate, report):
    common = ["--authority-dir", str(authority), "--endpoint", endpoints[0], "--p2a-endpoints", ",".join(endpoints),
              "--payload-bytes", str(cell["payload_bytes"]), "--p2a-streams", str(cell["streams_per_group"]),
              "--p2a-groups", str(cell["endpoint_groups"]), "--p2a-runtime-workers", "1",
              "--p2a-outstanding-per-stream", str(cell["outstanding_per_stream"]),
              "--p2a-warmup-seconds", str(warmup), "--p2a-duration-seconds", str(duration),
              "--p2a-progress-seconds", str(progress), "--b5-rate-numerator", str(rate[0]),
              "--b5-rate-denominator", str(rate[1])]
    if cell["path"] == "direct":
        return [str(binaries["direct"]), "--role", "client", "--samples", "1", "--lifecycle", "warm", *common]
    return [str(binaries["nbsr"]), "--samples", "1", *common, "--p2a-cleanup-report", str(report)]


def run_one(cell, binaries, authority, plan, directory, *, warmup, duration, progress, rate, diagnostic):
    directory.mkdir(parents=True, exist_ok=False)
    groups = cell["endpoint_groups"]
    allowance = warmup + duration + ALLOWANCE
    resource_bound = math.ceil(allowance / CADENCE + 2) * (groups + 1)
    progress_bound = math.ceil((duration + ALLOWANCE) / progress) + 2
    guards = LiveGuards(groups=groups, max_progress=progress_bound, max_resources=resource_bound)
    source = sampler = reader = None
    servers, reports, commands, affinities = [], [], [], []
    sampler_running = False
    result = {"path": cell["path"], "valid": False, "classification": "FAIL", "scope": "Windows loopback"}
    cleanup_errors = []
    with ExitStack() as files:
        raw = files.enter_context((directory / "source.stdout.ndjson").open("xb"))
        resource_file = files.enter_context((directory / "resources.ndjson").open("x", encoding="utf-8"))
        ack = directory / "completion.ack"
        try:
            endpoints = []
            for ordinal, mask in enumerate(plan["endpoint_masks"]):
                ready, report = directory / f"d{ordinal}.ready.json", directory / f"d{ordinal}.cleanup.json"
                argv, env = stage4._server_command(cell, binaries, authority, ready, directory / f"d{ordinal}.result.json", ack)
                if cell["path"] == "nbsr":
                    argv += ["--p2a-cleanup-report", str(report)]
                commands.append({"role": f"destination_{ordinal}", "argv": argv,
                                 "environment_overrides": {"NBSR_P2A_STREAMS": env.get("NBSR_P2A_STREAMS")}})
                write_json(directory / "commands.json", commands)
                server = subprocess.Popen(argv, cwd=ROOT, env=env,
                    stdout=files.enter_context((directory / f"d{ordinal}.stdout").open("xb")),
                    stderr=files.enter_context((directory / f"d{ordinal}.stderr").open("xb")))
                servers.append(server)
                if cell["path"] == "nbsr":
                    reports.append(("destination", server.pid, report))
                verified = set_and_verify_exact_affinity(server.pid, mask)
                affinities.append(verified)
                if not verified["verified"]:
                    raise RuntimeError("destination affinity unverified")
                endpoints.append(wait_ready(ready, server)["endpoint"])
            report = directory / "source.cleanup.json"
            argv = source_command(cell, binaries, authority, endpoints, warmup=warmup, duration=duration,
                                  progress=progress, rate=rate, report=report)
            commands.append({"role": "source", "argv": argv, "environment_overrides": {}})
            write_json(directory / "commands.json", commands)
            launched = time.monotonic_ns()
            deadline = launched + math.ceil(allowance * 1e9)
            source = subprocess.Popen(argv, cwd=ROOT, env=os.environ.copy(), stdout=subprocess.PIPE,
                stderr=files.enter_context((directory / "source.stderr").open("xb")))
            verified = set_and_verify_exact_affinity(source.pid, plan["source_mask"])
            affinities.append(verified)
            if not verified["verified"]:
                raise RuntimeError("source affinity unverified")
            if cell["path"] == "nbsr":
                reports.append(("source", source.pid, report))
            processes = {"source": source.pid, **{f"destination_{i}": p.pid for i, p in enumerate(servers)}}
            def resource_sink(sample):
                value = asdict(sample)
                resource_file.write(json.dumps(value) + "\n")
                resource_file.flush()
                guards.resource(value)
            sampler = ProcessResourceSampler(processes, interval_seconds=CADENCE,
                assigned_logical_processors=plan["logical_processors_available"],
                record_sink=resource_sink, max_records=resource_bound)
            sampler.start()
            sampler_running = True
            stream = B5Stream(raw_sink=raw, groups=groups, payload_bytes=cell["payload_bytes"], sampler=sampler,
                deadline_ns=deadline, max_line_bytes=262_144, max_lines=progress_bound + resource_bound + 1024,
                on_progress=guards.progress)
            reader = BoundedReader(source.stdout)
            reader.start()
            final = consume(source, reader, stream)
            reader.join()
            source.wait(timeout=0)
            sampler.stop()
            sampler_running = False
            ack.write_text("source exited and resource sampling complete\n", encoding="ascii")
            for server in servers:
                server.wait(timeout=max(0, (deadline - time.monotonic_ns()) / 1e9))
                if server.returncode != 0:
                    raise RuntimeError("destination failed")
            ownership = []
            for role, pid, path in reports:
                value = json.loads(path.read_text(encoding="utf-8"))
                valid = validate_report(value, role, pid)
                ownership.append({"role": role, "pid": pid, "file": path.name, "all_11_zero": valid})
                if not valid:
                    raise RuntimeError("owned-resource cleanup failed")
            ratio = final["completed"] / final["offered"] if final["offered"] else 0
            elapsed = final["measurement_duration_ns"] + final["drain_duration_ns"]
            result.update(valid=True, classification="DIAGNOSTIC" if diagnostic else "ACCOUNTING_PASS",
                          final=final, achieved_offered_ratio=ratio,
                          gbps=final["completed"] * cell["payload_bytes"] * 16 / elapsed,
                          qualification=guards.qualification(), ownership_reports=ownership,
                          cleanup_scope="11-counter reports and all process joins" if reports else "process joins only; runtime ownership NOT_MEASURED",
                          internal_failure_thread_join="NOT_MEASURED")
            if not diagnostic and ratio < 0.95:
                raise RuntimeError("paced achievable/offered gate below 95%; target unchanged")
        except Exception as error:
            result.update(valid=False, classification="FAIL", error=str(error))
        finally:
            # Stop authoritative sampling while owned processes still exist.
            if sampler_running:
                try:
                    sampler.stop()
                except Exception as error:
                    cleanup_errors.append(f"sampler: {error}")
            if source is not None:
                try:
                    if source.poll() is None:
                        source.kill()
                    source.wait(timeout=5)
                    if reader is None:
                        reader = BoundedReader(source.stdout)
                        reader.start()
                    preserve_tail(reader, raw)
                except Exception as error:
                    cleanup_errors.append(f"source/reader cleanup: {error}")
            for server in servers:
                try:
                    if server.poll() is None:
                        server.kill()
                    server.wait(timeout=5)
                except Exception as error:
                    cleanup_errors.append(f"destination cleanup: {error}")
            if cleanup_errors:
                result.update(valid=False, classification="FAIL", cleanup_errors=cleanup_errors)
            result["affinity"] = affinities
            write_json(directory / "result.json", result)
    return result


def execute(args):
    mode = validate_mode(diagnostic=args.diagnostic, reference=args.reference, rate=args.rate)
    if not (math.isfinite(args.duration) and 0 < args.duration <= 7200 and math.isfinite(args.warmup)
            and 0 <= args.warmup <= 60 and 1 <= args.progress <= 60):
        raise ValueError("invalid phase duration")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True):
        raise ValueError("clean source SHA required")
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    try:
        topology = windows_processor_topology()
        plan = placement(topology, args.cores, args.groups)
        binaries = p2a.build(args.target)
        retained = args.output / "binaries"
        retained.mkdir()
        for role, original in list(binaries.items()):
            shutil.copy2(original, retained / original.name)
            binaries[role] = retained / original.name
        hashes = {role: sha256(path) for role, path in binaries.items()}
        shape = dict(physical_cores=args.cores, endpoint_groups=args.groups, streams_per_group=args.streams,
                     payload_bytes=args.payload, runtime_workers=1)
        load = {"mode": mode, "rate_numerator": args.rate[0], "rate_denominator": args.rate[1]} if args.diagnostic else load_ceiling(
            args.reference, current_sha=sha, binary_sha256=hashes, shape=shape, percent=args.percent, depth=args.depth)
        if not args.diagnostic:
            require_reference_placement(load, plan, topology)
        rate = (load["rate_numerator"], load["rate_denominator"])
        assert_clean_source(sha)
        write_json(args.output / "environment.json", {"repository_sha": sha, "git_status": "", "binary_sha256": hashes,
            "topology": topology, "placement": plan, "shape": shape, "mode": mode, "load": load,
            "controller_args": vars(args) | {"output": str(args.output), "target": str(args.target), "reference": str(args.reference) if args.reference else None},
            "platform": sys.platform, "python": sys.version, "source_sha256": sha256(__file__),
            "scope": "Windows loopback, shared physical pool; no external-server or thermal qualification"})
        with tempfile.TemporaryDirectory(prefix="nbsr-b5-v2-") as temporary:
            authority = Path(temporary) / "authority"
            write_loopback_authority(authority)
            by_path = {"direct": [], "nbsr": []}
            required = 1 if args.diagnostic else 3
            for repeat in range(1, 6):
                if repeat > required:
                    break
                for path in (("direct", "nbsr") if repeat % 2 else ("nbsr", "direct")):
                    cell = dict(path=path, endpoint_groups=args.groups, streams_per_group=args.streams,
                                outstanding_per_stream=args.depth, payload_bytes=args.payload)
                    row = run_one(cell, binaries, authority, plan, args.output / f"{path}-r{repeat}", warmup=args.warmup,
                                  duration=args.duration, progress=args.progress, rate=rate, diagnostic=args.diagnostic)
                    rows.append(row)
                    by_path[path].append(row)
                    write_json(args.output / "records.json", rows)
                    if not row["valid"]:
                        raise RuntimeError("invalid partial run retained; no replacement repeats")
                if repeat == 3:
                    required = max(required_repeats(values) for values in by_path.values())
        assert_clean_source(sha)
        write_json(args.output / "summary.json", {"classification": "DIAGNOSTIC" if args.diagnostic else "ACCOUNTING_PASS_QUALIFICATION_PENDING",
                   "repeats_per_path": required, "thermal_and_power": "NOT_MEASURED",
                   "note": "No STABLE claim; inspect qualified steady drift/resource windows and owned cleanup separately."})
    except Exception as error:
        write_json(args.output / "failure.json", {"classification": "FAIL", "error": str(error), "partial_records_retained": len(rows)})
        raise
    finally:
        with (args.output / "checksums.sha256").open("w", encoding="ascii") as manifest:
            for path in sorted(args.output.rglob("*")):
                if path.is_file() and path.name != "checksums.sha256":
                    manifest.write(f"{sha256(path)}  {path.relative_to(args.output).as_posix()}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=Path("C:/NBSR-build/b4b-task4k"))
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--rate", type=int, nargs=2, metavar=("NUMERATOR", "DENOMINATOR"))
    parser.add_argument("--percent", type=int, choices=range(70, 81), default=70)
    parser.add_argument("--cores", type=int, choices=(1, 2, 4), default=4)
    parser.add_argument("--groups", type=int, choices=(1, 2, 4), default=4)
    parser.add_argument("--streams", type=int, choices=range(1, 65), default=1)
    parser.add_argument("--depth", type=int, choices=range(1, 65), default=1)
    parser.add_argument("--payload", type=int, choices=(1024, 16384), default=16384)
    parser.add_argument("--warmup", type=float, default=2)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--progress", type=float, default=1)
    execute(parser.parse_args())


if __name__ == "__main__":
    main()
