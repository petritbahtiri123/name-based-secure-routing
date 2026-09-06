"""External-only historical-load PDH observer qualification; never a capacity reference."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from pathlib import Path
import statistics
import subprocess
import sys
import time

COUNTERS = [r"\Processor(0)\% Processor Time", r"\Processor(0)\% User Time",
            r"\Processor(0)\% Privileged Time", r"\Processor(0)\% Interrupt Time",
            r"\Processor(0)\% DPC Time", r"\Processor(1)\% Processor Time"]
LABELS = ["logical0_busy", "logical0_user", "logical0_privileged", "logical0_interrupt",
          "logical0_dpc", "logical1_busy"]


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def anchor():
    return {"monotonic_ns": time.monotonic_ns(), "utc": datetime.now(timezone.utc).isoformat(),
            "local_utc_offset_seconds": datetime.now().astimezone().utcoffset().total_seconds()}


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def controller_args(output, target):
    return argparse.Namespace(output=output, target=target, reference=None, paths=["nbsr"],
        diagnostic=True, ownership_sampling=False, rate=[421624000000, 150013467],
        percent=70, cores=1, groups=1, streams=8, depth=1, payload=16384,
        warmup=3, duration=120, progress=30)


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    if len(rows[0]) != 7 or any(not value.lower().endswith(counter.lower())
        for value, counter in zip(rows[0][1:], COUNTERS)):
        raise ValueError("PDH counter schema differs")
    result = []
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != 7:
            raise ValueError("Incomplete PDH row")
        values = [float(value) for value in row[1:]]
        if not all(math.isfinite(v) and 0 <= v <= 100.01 for v in values):
            raise ValueError("Unavailable or invalid PDH percentage")
        result.append({"typeperf_local_timestamp": row[0], **dict(zip(LABELS, values))})
    return result


def comparison(rows):
    grouped = {a: [r for r in rows if r["arm"] == a] for a in ("off", "on")}
    if any(len(v) < 3 for v in grouped.values()):
        raise ValueError("Three complete matched pairs required")
    cvs = {}
    medians = {}
    for arm, values in grouped.items():
        medians[arm] = {}
        for key in ("gbps", "p99_ns"):
            series = [r[key] for r in values]
            if not all(math.isfinite(v) and v > 0 for v in series):
                raise ValueError("Invalid comparison value")
            cvs[arm + "_" + key] = statistics.stdev(series) / statistics.mean(series)
            medians[arm][key] = statistics.median(series)
    impact = {key: abs(medians["on"][key] / medians["off"][key] - 1)
              for key in ("gbps", "p99_ns")}
    return {"required_pairs": 5 if max(cvs.values()) > .05 else 3,
            "cv": cvs, "medians": medians, "absolute_median_impact": impact,
            "observer_accepted": max(impact.values()) <= .05,
            "p99_definition": "per-repeat median of steady-window p99; not pooled-operation p99"}


def validate_coverage(rows, meta):
    """Reject stale/duplicated/gapped coverage; retain 3s boundary uncertainty."""
    if len(rows) < 100:
        raise ValueError("PDH coverage unavailable")
    anchors = [meta[name] for name in
               ("before_launch", "after_launch", "ready", "before_stop", "after_join")]
    offsets = {a["local_utc_offset_seconds"] for a in anchors}
    if len(offsets) != 1:
        raise ValueError("Local UTC offset changed during observation")
    tz = timezone(timedelta(seconds=offsets.pop()))
    wall = [datetime.fromisoformat(a["utc"]).timestamp() for a in anchors]
    monotonic = [a["monotonic_ns"] / 1e9 for a in anchors]
    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            if wall[j] < wall[i] or monotonic[j] < monotonic[i]:
                raise ValueError("Observer anchor clock reversed")
            if abs((wall[j] - wall[i]) - (monotonic[j] - monotonic[i])) > 3:
                raise ValueError("Wall/monotonic interval mismatch")
    times = []
    for row in rows:
        stamp = row["typeperf_local_timestamp"]
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\.\d{3}", stamp):
            raise ValueError("Unknown typeperf timestamp locale/format")
        times.append(datetime.strptime(stamp, "%m/%d/%Y %H:%M:%S.%f").replace(tzinfo=tz).timestamp())
    gaps = [b - a for a, b in zip(times, times[1:])]
    if any(gap <= 0 or gap > 3 for gap in gaps):
        raise ValueError("PDH timestamps duplicated, reversed or gapped")
    if times[0] > wall[2] or times[0] < wall[0] - 3:
        raise ValueError("PDH first sample does not cover ready boundary")
    if times[-1] < wall[3] - 3 or times[-1] > wall[4] + 3:
        raise ValueError("PDH last sample does not cover stop boundary")
    return {"coverage_valid": True, "samples": len(times), "max_gap_seconds": max(gaps),
            "timestamp_format": "MM/dd/yyyy HH:mm:ss.fff", "boundary_uncertainty_seconds": 3,
            "first_sample_utc": datetime.fromtimestamp(times[0], timezone.utc).isoformat(),
            "last_sample_utc": datetime.fromtimestamp(times[-1], timezone.utc).isoformat(),
            "correlation": "bounded approximate phase alignment, not causal attribution"}


class Observer:
    def __init__(self, directory):
        self.directory = directory
        self.process = None
        self.handles = []
        self.meta = {"counter_labels": LABELS, "sample_seconds": 1, "max_samples": 300}

    def start(self):
        self.directory.mkdir(exist_ok=False)
        command = ["typeperf", *COUNTERS, "-si", "1", "-sc", "300", "-f", "CSV",
                   "-o", str(self.directory / "raw.csv")]
        self.meta.update(command=command, before_launch=anchor())
        try:
            self.handles = [(self.directory / name).open("xb") for name in ("stdout", "stderr")]
            self.process = subprocess.Popen(command, stdout=self.handles[0], stderr=self.handles[1])
            self.meta.update(pid=self.process.pid, after_launch=anchor())
            deadline = time.monotonic() + 10
            while True:
                if self.process.poll() is not None:
                    raise RuntimeError("PDH exited during readiness")
                try:
                    if len(read_csv(self.directory / "raw.csv")) >= 2:
                        break
                except (FileNotFoundError, PermissionError, ValueError):
                    pass  # Partial file is tolerated only during bounded readiness.
                if time.monotonic() > deadline:
                    raise RuntimeError("PDH readiness unavailable")
                time.sleep(.1)
            self.meta["ready"] = anchor()
        finally:
            write(self.directory / "metadata.json", self.meta)

    def stop(self):
        self.meta["before_stop"] = anchor()
        if self.process is not None:
            self.meta["unexpected_exit_before_stop"] = self.process.poll() is not None
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.meta["exit_code"] = self.process.returncode
        for f in self.handles:
            f.close()
        self.meta["after_join"] = anchor()
        if self.directory.exists():
            write(self.directory / "metadata.json", self.meta)


def clean_sha(repo, expected):
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if sha != expected or subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True):
        raise RuntimeError("Clean frozen SHA required")


def seal(directory):
    index = directory / "checksums.sha256"
    index.write_text("".join(f"{digest(p)}  {p.relative_to(directory).as_posix()}\n"
        for p in sorted(directory.rglob("*")) if p.is_file() and p != index), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "run"])
    parser.add_argument("--sha", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    clean_sha(args.repo, args.sha)
    sys.path.insert(0, str(args.repo))
    from scripts import run_b5_v2 as controller
    if args.mode == "prepare":
        if args.prepared.exists():
            raise ValueError("Fresh prepared manifest required")
        binaries = controller.p2a.build(args.target)
        clean_sha(args.repo, args.sha)
        write(args.prepared, {"sha": args.sha, "driver_sha256": digest(Path(__file__)),
            "binary_sha256": {k: digest(p) for k, p in binaries.items()}})
        return
    prepared = json.loads(args.prepared.read_text())
    if prepared["sha"] != args.sha or prepared["driver_sha256"] != digest(Path(__file__)):
        raise ValueError("Prepared source/driver binding differs")
    if args.output is None:
        raise ValueError("Fresh output required")
    args.output.mkdir(exist_ok=False)
    write(args.output / "definition.json", {"classification": "HISTORICAL_FIXED_LOAD_DIAGNOSTIC",
        "prepared": prepared, "fixed_rate": [421624000000, 150013467], "ownership_sampling": False,
        "not_current_capacity_percent": True, "counter_labels": LABELS,
        "pdh_scope": "OS counters; IRQ/DPC/OS activity can explain busy minus tracked CPU; no unrelated-app or thermal attribution",
        "order": "off/on odd pairs, on/off even pairs; three, sticky five if either metric CV exceeds5%",
        "observer_gate": "absolute median goodput and median-window-p99 impact <=5%",
        "timing": "requires externally coordinated quiet slot; wall and monotonic anchors bracket operations, not exact counter sampling instants"})
    original_build, original_placement = controller.p2a.build, controller.placement
    rows = []
    try:
        required = 3
        for repeat in range(1, 6):
            if repeat > required:
                break
            for arm in (("off", "on") if repeat % 2 else ("on", "off")):
                clean_sha(args.repo, args.sha)
                name = f"{arm}-r{repeat}"
                observer = Observer(args.output / (name + "-pdh")) if arm == "on" else None
                def build(target):
                    binaries = original_build(target)
                    if {k: digest(p) for k, p in binaries.items()} != prepared["binary_sha256"]:
                        raise RuntimeError("Binary identity changed")
                    if observer:
                        observer.start()  # Only after the controller's build is complete.
                    return binaries
                def placement(topology, cores, groups):
                    plan = original_placement(topology, cores, groups)
                    if plan["source_mask"] != 1 or plan["endpoint_masks"] != [1]:
                        raise RuntimeError("Expected logical0 pool")
                    if not any(c["logical_mask"] == 3 and c["smt"] for c in topology["cores"]):
                        raise RuntimeError("Logical1 is not verified SMT sibling of logical0")
                    return plan
                controller.p2a.build, controller.placement = build, placement
                write(args.output / (name + "-start.json"), anchor())
                try:
                    controller.execute(controller_args(args.output / name, args.target))
                finally:
                    if observer:
                        observer.stop()
                    write(args.output / (name + "-end.json"), anchor())
                if observer:
                    data = read_csv(observer.directory / "raw.csv")
                    if observer.meta["unexpected_exit_before_stop"]:
                        raise RuntimeError("PDH coverage unavailable")
                    coverage = validate_coverage(data, observer.meta)
                    write(observer.directory / "coverage.json", coverage)
                    write(observer.directory / "hostname-free-samples.json", data)
                cell = args.output / name
                env = json.loads((cell / "environment.json").read_text())
                if env["repository_sha"] != args.sha or env["binary_sha256"] != prepared["binary_sha256"]:
                    raise RuntimeError("Controller binding differs")
                records = json.loads((cell / "records.json").read_text())
                if len(records) != 1 or not records[0]["valid"]:
                    raise RuntimeError("Invalid diagnostic retained without replacement")
                progress = [json.loads(line) for line in (cell / "nbsr-r1/source.stdout.ndjson").read_text().splitlines()]
                steady = [r["p99_latency_ns"] for r in progress if r.get("phase") == "steady"]
                if len(steady) < 3 or any(v is None for v in steady):
                    raise RuntimeError("Steady p99 comparison unavailable")
                rows.append({"arm": arm, "repeat": repeat, "gbps": records[0]["gbps"],
                             "p99_ns": statistics.median(steady)})
                write(args.output / "records.json", rows)
            if repeat >= 3:
                summary = comparison(rows)
                required = max(required, summary["required_pairs"])
                write(args.output / "comparison.json", {**summary, "cohort_complete": False})
        clean_sha(args.repo, args.sha)
        write(args.output / "comparison.json", {**summary, "cohort_complete": True,
            "dispersion_unresolved": max(summary["cv"].values()) > .05,
            "classification": "DIAGNOSTIC_OBSERVER_COMPARISON_ONLY"})
    except BaseException as error:
        write(args.output / "failure.json", {"error_type": type(error).__name__, "valid_cells": len(rows),
            "classification": "INVALID_PARTIAL_DIAGNOSTIC", "no_replacement": True})
        write(args.output / "comparison.json", {"cohort_complete": False,
            "observer_accepted": False, "classification": "INVALID_PARTIAL_DIAGNOSTIC",
            "prefix_causal_qualification": "INVALID", "valid_cells_retained": len(rows)})
        raise
    finally:
        controller.p2a.build, controller.placement = original_build, original_placement
        seal(args.output)


if __name__ == "__main__":
    main()
