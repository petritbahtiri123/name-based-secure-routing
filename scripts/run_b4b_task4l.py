"""Matched Task 4k boundary profiling; diagnostic only, no optimization."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import run_b4b_v2 as v2
from scripts.performance.external_packet_capture import ExternalCapture
from scripts.run_b4b_task4h import observer_gate
from scripts.run_b4b_task4k import checksums


def run_one(output, binaries, rate, repeat, observer):
    if observer not in ("none", "packet", "etw"):
        raise ValueError("unknown observer")
    directory = output / "raw" / observer / f"rate-{rate}"
    directory.mkdir(parents=True, exist_ok=True)
    capture = ExternalCapture(
        Path(r"C:\Program Files\Wireshark\dumpcap.exe"),
        Path(r"C:\Program Files\Wireshark\tshark.exe"),
    ) if observer == "packet" else None
    started = time.time_ns()
    print(f"rate={rate} repeat={repeat} observer={observer}", flush=True)
    try:
        record = v2.run_measured_cell(
            512, 1, repeat, binaries, directory, duration=30, warmup=2,
            planned_clients=[512], release_rate=rate, source_shards=2,
            timeline=False, packet_capture=capture,
            counter_path=directory / f"r{repeat}-host.csv",
        )
    except Exception as error:
        record = {"valid": False, "failure": f"{type(error).__name__}: {error}",
                  "offered_admission_rate": rate, "repeat": repeat,
                  "cleanup": {"all_zero": False, "status": "UNCONFIRMED"}}
    record.update(started_unix_ns=started, ended_unix_ns=time.time_ns(),
                  observer=observer, claim_class="DIAGNOSTIC")
    v2.write_json(directory / f"r{repeat}.json", record)
    return record


def execute(output: Path, target: Path, mode: str):
    if output.exists():
        raise FileExistsError(output)
    if mode not in ("paired", "none", "etw"):
        raise ValueError("unknown mode")
    output.mkdir(parents=True)
    binaries = v2.build(target)
    sources = [
        "crates/nbsr-transport/Cargo.toml", "crates/nbsr-transport/Cargo.lock",
        "crates/nbsr-transport/src/lib.rs", "crates/nbsr-transport/src/quinn_adapter.rs",
        "crates/nbsr-transport/src/udp_socket.rs", "crates/nbsr-transport/src/bin/perf_direct_peer.rs",
        "scripts/run_b4b_task4l.py", "scripts/run_b4b_v2.py",
        "scripts/run_b4b_mixed_connections.py", "scripts/run_b4b_task4h.py",
        "scripts/performance/external_packet_capture.py",
        "crates/nbsr-transport/src/bin/perf_rust_source.rs",
        "crates/nbsr-transport/src/bin/wp8_interop_server.rs",
        "crates/nbsr-transport/src/bin/benchmark_support/lifecycle_shards.rs",
        "crates/nbsr-transport/src/bin/benchmark_support/batch_release.rs",
    ]
    for source in sources:
        destination = output / "capture-source" / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v2.ROOT / source, destination)
    environment = v2.host_environment()
    environment.update(
        build="release", command=[sys.executable, *sys.argv],
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        rates=[200, 250], source_shards=2, clients=512,
        duration_seconds=30, warmup_seconds=2, timeline=False,
        binary_sha256={k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in binaries.items()},
        source_sha256={p: hashlib.sha256((v2.ROOT / p).read_bytes()).hexdigest() for p in sources},
        claim_class="DIAGNOSTIC", mode=mode,
    )
    v2.write_json(output / "environment.json", environment)
    records = {}
    try:
        for rate in (200, 250):
            selected = {name: [] for name in (("none", "packet") if mode == "paired" else (mode,))}
            records[str(rate)] = selected
            repeat, count = 1, (3 if mode == "paired" else 5)
            while repeat <= count:
                order = list(selected) if repeat % 2 else list(reversed(selected))
                for observer in order:
                    record = run_one(output, binaries, rate, repeat, observer)
                    selected[observer].append(record)
                    if not record["valid"] or not record["cleanup"]["all_zero"]:
                        v2.write_json(output / "analysis.json", {
                            "classification": "FAIL / UNRESOLVED", "records": records,
                            "reason": "invalid evidence or ownership cleanup",
                        })
                        raise RuntimeError("invalid evidence or ownership cleanup; preserve and diagnose")
                if repeat == 3 and mode == "paired":
                    count = max(v2.required_repeats(rows) for rows in selected.values())
                repeat += 1
        analysis = {"classification": "UNRESOLVED:transport-handshake-progress",
                    "claim_class": "DIAGNOSTIC", "records": records}
        if mode == "paired":
            analysis["observer_gates"] = {
                rate: observer_gate(rows["none"], rows["packet"])
                for rate, rows in records.items()
            }
        v2.write_json(output / "analysis.json", analysis)
    finally:
        checksums(output)


def compare_etw(root: Path):
    environments = {mode: json.loads((root / mode / "environment.json").read_text())
                    for mode in ("none", "etw")}
    if environments["none"]["binary_sha256"] != environments["etw"]["binary_sha256"]:
        raise ValueError("unmatched binary hashes")
    for field in ("repository_sha", "source_sha256", "rates", "source_shards",
                  "clients", "duration_seconds", "warmup_seconds", "timeline"):
        if environments["none"].get(field) != environments["etw"].get(field):
            raise ValueError(f"unmatched workload/source: {field}")
    analyses = {mode: json.loads((root / mode / "analysis.json").read_text())
                for mode in ("none", "etw")}
    gates = {rate: observer_gate(analyses["none"]["records"][rate]["none"],
                                 analyses["etw"]["records"][rate]["etw"])
             for rate in ("200", "250")}
    result = {"observer_gates": gates, "claim_class": "DIAGNOSTIC",
              "capture_order": "five controls per rate followed by five ETW repeats per rate",
              "order_limitation": "block order can confound temporal host drift",
              "attribution": "UNRESOLVED; trace integrity and event correlation require separate verification",
              "timing_comparable": all(gate["pass"] for gate in gates.values())}
    path = root / "observer-comparison.json"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare-etw", type=Path)
    parser.add_argument("--target", type=Path, default=Path(r"C:\NBSR-build\b4b-task4k"))
    parser.add_argument("--mode", choices=("paired", "none", "etw"), default="paired")
    args = parser.parse_args()
    if args.compare_etw:
        compare_etw(args.compare_etw)
    elif args.output:
        execute(args.output, args.target, args.mode)
    else:
        parser.error("--output or --compare-etw is required")
